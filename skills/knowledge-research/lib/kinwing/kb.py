"""The knowledge base: topics, questions, sources, evidence, claims, concepts.

Every entity is one Markdown file with YAML frontmatter under kb/<kind>/<id>.md (topics
are kb/topics/<id>/topic.yaml). The files are the source of truth; nothing else is needed
to read them. All mutating functions expect the caller to hold `store.locked()`; the
public helpers below take the lock themselves.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import store
from .store import KwError, Paths, now, split_list, uniq

DEPTHS = ("orientation", "deep", "monitor", "targeted")
TOPIC_STATUS = ("active", "paused", "archived")
Q_STATUS = ("open", "in_progress", "answered", "partial", "blocked", "dropped")
Q_ORIGIN = ("user", "plan", "gap", "contradiction", "learning", "development", "related")
LEVELS = ("high", "medium", "low")
CLAIM_KIND = ("finding", "interpretation", "hypothesis")
STRENGTH = ("strong", "moderate", "weak", "unsupported", "contested")
CLAIM_STATE = ("current", "superseded", "retracted")
EV_STANCE = ("supports", "contradicts", "context")
SOURCE_CATEGORY = ("docs", "paper", "code", "discussion", "book", "article", "dataset", "video", "other")
RIGHTS = ("open", "copyrighted", "user-copy", "private", "unknown")
RELATIONS = ("related", "part-of", "contrasts", "example-of", "leads-to", "depends-on")
PROMPT_KINDS = ("explain", "predict", "compare", "apply", "critique", "reflect")

DEFAULT_BUDGET = {
    "max_questions_per_run": 3,
    "max_sources_per_run": 8,
    "max_minutes": 40,
    "max_runs_per_week": 3,
}


def _enum(value, allowed, field):
    if value is None:
        return None
    if value not in allowed:
        raise KwError(f"{field} must be one of {', '.join(allowed)} (got '{value}')", 2)
    return value


class KB:
    def __init__(self, paths: Paths | None = None):
        self.p = paths or Paths()

    # ------------------------------------------------------------------ generic

    def exists(self, kind: str, eid: str) -> bool:
        if kind == "topic":
            return (self.p.topic_dir(eid) / "topic.yaml").exists()
        return self.p.entity_path(kind, eid).exists()

    def load(self, kind: str, eid: str) -> tuple[dict, str]:
        path = self.p.entity_path(kind, eid)
        if not path.exists():
            raise KwError(f"no {kind} '{eid}'")
        return store.read_entity(path)

    def save(self, kind: str, meta: dict, body: str = "") -> None:
        store.write_entity(self.p.entity_path(kind, meta["id"]), meta, body)

    def all(self, kind: str) -> list[tuple[dict, str]]:
        d = self.p.entity_dir(kind)
        if not d.exists():
            return []
        out = []
        for f in sorted(d.glob("*.md")):
            if f.name.startswith("."):
                continue
            out.append(store.read_entity(f))
        return out

    def metas(self, kind: str, topic: str | None = None) -> list[dict]:
        out = []
        for meta, _ in self.all(kind):
            if topic and not self._in_topic(meta, topic):
                continue
            out.append(meta)
        return out

    @staticmethod
    def _in_topic(meta: dict, topic: str) -> bool:
        if meta.get("topic") == topic:
            return True
        return topic in (meta.get("topics") or [])

    # ------------------------------------------------------------------ change log

    def log_change(self, topic: str, kind: str, eid: str, summary: str, run: str | None = None,
                   detail: str | None = None) -> None:
        if not topic or not self.exists("topic", topic):
            return
        entry = {"at": store.now_ms(), "kind": kind, "id": eid, "summary": summary}
        if run:
            entry["run"] = run
        if detail:
            entry["detail"] = detail
        store.append_line(self.p.topic_dir(topic) / "changes.jsonl", entry)

    def changes(self, topic: str) -> list[dict]:
        return store.read_jsonl(self.p.topic_dir(topic) / "changes.jsonl")

    # ------------------------------------------------------------------ topics

    def topic(self, tid: str) -> dict:
        f = self.p.topic_dir(tid) / "topic.yaml"
        if not f.exists():
            raise KwError(f"no topic '{tid}' (see: kw topic list)")
        t = store.read_yaml(f)
        t.setdefault("budget", {})
        for k, v in DEFAULT_BUDGET.items():
            t["budget"].setdefault(k, v)
        t.setdefault("perspectives", [])
        t.setdefault("status", "active")
        return t

    def topics(self) -> list[dict]:
        d = self.p.kb / "topics"
        if not d.exists():
            return []
        return [self.topic(x.name) for x in sorted(d.iterdir()) if (x / "topic.yaml").exists()]

    def save_topic(self, t: dict) -> None:
        t["updated"] = now()
        store.write_yaml(
            self.p.topic_dir(t["id"]) / "topic.yaml", t,
            header="# kinwing topic configuration. Edit freely; `kw check` validates it.",
        )

    def create_topic(self, title: str, tid: str | None = None, **fields) -> dict:
        tid = tid or store.slugify(title, 40)
        if not store.valid_slug(tid):
            raise KwError(f"invalid topic id '{tid}': use lowercase letters, digits and hyphens", 2)
        with store.locked(self.p):
            if self.exists("topic", tid):
                raise KwError(f"topic '{tid}' already exists (kw topic show {tid})")
            budget = dict(DEFAULT_BUDGET)
            budget.update({k: v for k, v in (fields.pop("budget", None) or {}).items() if v is not None})
            t = {
                "id": tid,
                "title": title,
                "description": fields.get("description") or "",
                "objective": fields.get("objective") or "",
                "familiarity": fields.get("familiarity") or "",
                "known_concepts": split_list(fields.get("known_concepts")),
                "depth": _enum(fields.get("depth") or "orientation", DEPTHS, "depth"),
                "boundaries": {
                    "include": split_list(fields.get("include")),
                    "exclude": split_list(fields.get("exclude")),
                },
                "preferred_sources": split_list(fields.get("preferred_sources")),
                "perspectives": fields.get("perspectives") or [],
                "research_priorities": split_list(fields.get("research_priorities")),
                "learning_priorities": split_list(fields.get("learning_priorities")),
                "frequency": fields.get("frequency") or "manual",
                "budget": budget,
                "schedule": {"enabled": False, "cron": "", "agent": "", "ao_slug": ""},
                "status": "active",
                "stale_after_days": int(fields.get("stale_after_days") or 180),
                "created": now(),
                "last_investigated": None,
                "materials": split_list(fields.get("materials")),
            }
            d = self.p.topic_dir(tid)
            d.mkdir(parents=True, exist_ok=True)
            self.save_topic(t)
            ov = d / "overview.md"
            if not ov.exists():
                store.atomic_write(
                    ov,
                    f"# {title}\n\n<!-- kinwing: the agent's narrative orientation for this topic. "
                    "Rewrite it as understanding improves; the dossier embeds it. -->\n\n"
                    "_No research yet._\n",
                )
            self.log_change(tid, "topic", tid, f"topic created: {title}")
        return t

    def set_topic_fields(self, tid: str, changes: dict, note: str | None = None) -> dict:
        """Update top-level or dotted (budget.max_minutes) topic fields."""
        with store.locked(self.p):
            t = self.topic(tid)
            for key, val in changes.items():
                target, parts = t, key.split(".")
                for part in parts[:-1]:
                    target = target.setdefault(part, {})
                leaf = parts[-1]
                if key == "depth":
                    _enum(val, DEPTHS, "depth")
                if key == "status":
                    _enum(val, TOPIC_STATUS, "status")
                if isinstance(target.get(leaf), list) and isinstance(val, str):
                    val = split_list(val)
                elif isinstance(target.get(leaf), int) and not isinstance(target.get(leaf), bool):
                    try:
                        val = int(val)
                    except (TypeError, ValueError):
                        raise KwError(f"{key} must be a number", 2) from None
                target[leaf] = val
            self.save_topic(t)
            self.log_change(tid, "topic", tid, note or "topic settings changed: " + ", ".join(changes))
        return t

    def add_perspective(self, tid: str, pid: str, name: str, why: str = "") -> dict:
        with store.locked(self.p):
            t = self.topic(tid)
            if any(x.get("id") == pid for x in t["perspectives"]):
                raise KwError(f"perspective '{pid}' already exists in {tid}")
            t["perspectives"].append({"id": pid, "name": name, "why": why})
            self.save_topic(t)
            self.log_change(tid, "topic", tid, f"perspective added: {name}")
        return t

    # ------------------------------------------------------------------ questions

    def add_question(self, topic: str, text: str, origin: str = "plan", priority: str = "medium",
                     value: str = "medium", cost: str = "medium", perspective: str | None = None,
                     depends_on=None, concepts=None, claims=None, run: str | None = None,
                     asked_by: str = "agent", learning_ref: str | None = None,
                     context: str | None = None) -> dict:
        self.topic(topic)
        _enum(origin, Q_ORIGIN, "origin")
        _enum(priority, LEVELS, "priority")
        _enum(value, LEVELS, "value")
        _enum(cost, LEVELS, "cost")
        text = " ".join(str(text).split())
        if not text:
            raise KwError("question text is empty", 2)
        with store.locked(self.p):
            norm = _norm_text(text)
            for m in self.metas("question", topic):
                if _norm_text(m.get("text", "")) == norm and m.get("status") not in ("dropped",):
                    return {**m, "_duplicate": True}
            qid = store.new_id(self.p, "question")
            meta = {
                "id": qid,
                "type": "question",
                "topic": topic,
                "text": text,
                "origin": origin,
                "asked_by": asked_by,
                "perspective": perspective or "",
                "priority": priority,
                "value": value,
                "cost": cost,
                "status": "open",
                "depends_on": split_list(depends_on),
                "concepts": split_list(concepts),
                "claims": split_list(claims),
                "context": context or "",
                "result": "",
                "created": now(),
                "created_in_run": run or "",
                "last_evaluated": None,
                "runs": [],
            }
            if learning_ref:
                meta["learning_ref"] = learning_ref
            self.save("question", meta, "## History\n")
            self.log_change(topic, "question", qid, f"question added ({origin}): {text}", run)
        return meta

    def update_question(self, qid: str, status: str | None = None, result: str | None = None,
                        note: str | None = None, run: str | None = None, **fields) -> dict:
        _enum(status, Q_STATUS, "status")
        with store.locked(self.p):
            meta, body = self.load("question", qid)
            hist = []
            if status and status != meta.get("status"):
                hist.append(f"status {meta.get('status')} → {status}")
                meta["status"] = status
            if result is not None:
                meta["result"] = result.strip()
                hist.append("result updated")
            for k in ("priority", "value", "cost"):
                if fields.get(k):
                    _enum(fields[k], LEVELS, k)
                    if fields[k] != meta.get(k):
                        hist.append(f"{k} {meta.get(k)} → {fields[k]}")
                        meta[k] = fields[k]
            for k in ("concepts", "claims", "depends_on"):
                if fields.get(k):
                    meta[k] = uniq((meta.get(k) or []) + split_list(fields[k]))
            if fields.get("perspective"):
                meta["perspective"] = fields["perspective"]
            if run:
                meta["runs"] = uniq((meta.get("runs") or []) + [run])
            meta["last_evaluated"] = now()
            line = f"- {now()}" + (f" [{run}]" if run else "") + ": " + "; ".join(hist + ([note] if note else []))
            body = (body.rstrip() if body.strip() else "## History") + "\n" + line + "\n"
            self.save("question", meta, body)
            if hist or note:
                self.log_change(meta["topic"], "question", qid,
                                f"question {meta.get('status')}: {meta['text']}" + (f" — {note}" if note else ""),
                                run, detail=meta.get("result") or None)
        return meta

    def question_score(self, q: dict, all_q: dict[str, dict] | None = None) -> tuple[float, str]:
        """A deliberately simple, explainable priority. Higher first."""
        w = {"high": 3, "medium": 2, "low": 1}
        score = w.get(q.get("priority"), 2) + w.get(q.get("value"), 2)
        why = [f"priority {q.get('priority')}", f"value {q.get('value')}"]
        bonus = {"user": 1.5, "learning": 1.5, "contradiction": 1.0, "gap": 0.5}.get(q.get("origin"), 0)
        if bonus:
            score += bonus
            why.append(f"origin {q.get('origin')} +{bonus:g}")
        pen = {"high": 1.0, "medium": 0.5}.get(q.get("cost"), 0)
        if pen:
            score -= pen
            why.append(f"cost {q.get('cost')} −{pen:g}")
        if not q.get("last_evaluated"):
            score += 0.5
            why.append("never investigated +0.5")
        if all_q is not None:
            blockers = [d for d in q.get("depends_on") or []
                        if d in all_q and all_q[d].get("status") not in ("answered", "dropped")]
            if blockers:
                return -1.0, "blocked by " + ", ".join(blockers)
        return round(score, 2), ", ".join(why)

    def ranked_questions(self, topic: str, statuses=("open",)) -> list[tuple[float, str, dict]]:
        qs = self.metas("question", topic)
        idx = {q["id"]: q for q in qs}
        out = []
        for q in qs:
            if q.get("status") not in statuses:
                continue
            s, why = self.question_score(q, idx)
            out.append((s, why, q))
        out.sort(key=lambda x: (-x[0], x[2].get("created", "")))
        return out

    # ------------------------------------------------------------------ sources (metadata)

    def sources_by_url(self) -> dict[str, dict]:
        out = {}
        for m in self.metas("source"):
            for u in [m.get("canonical_url")] + list(m.get("aliases") or []):
                if u:
                    out[u] = m
        return out

    def source_content_path(self, sid: str) -> Path:
        return self.p.library / sid / "content.txt"

    def source_text(self, sid: str) -> str | None:
        f = self.source_content_path(sid)
        return f.read_text(encoding="utf-8") if f.exists() else None

    # ------------------------------------------------------------------ evidence

    def add_evidence(self, source: str, quote: str | None, topic: str, locator: str | None = None,
                     note: str | None = None, kind: str = "quote", questions=None, concepts=None,
                     run: str | None = None, allow_unverified: bool = False) -> dict:
        from . import ingest

        self.topic(topic)
        smeta, _ = self.load("source", source)
        if kind not in ("quote", "observation", "data"):
            raise KwError("kind must be quote, observation or data", 2)
        if kind == "quote" and not quote:
            raise KwError("a quote is required (or use --kind observation with --note)", 2)
        verified, auto_loc = None, None
        if quote:
            text = self.source_text(source)
            if text is None:
                verified = False
            else:
                hit = ingest.find_quote(text, quote)
                verified = hit is not None
                if hit:
                    auto_loc = f"¶{hit['para']}"
            if kind == "quote" and not verified and not allow_unverified:
                raise KwError(
                    f"quote not found verbatim in {source}'s stored text. Quote it exactly "
                    "(whitespace and quote marks are normalized), or pass --allow-unverified "
                    "when the stored text is incomplete (it is then flagged unverified).", 3)
        with store.locked(self.p):
            norm = _norm_text(quote or note or "")
            for m, _ in self.all("evidence"):
                if m.get("source") == source and _norm_text(m.get("quote") or m.get("note") or "") == norm:
                    if topic not in (m.get("topics") or []):
                        m["topics"] = uniq((m.get("topics") or []) + [topic])
                        self.save("evidence", m, _)
                    return {**m, "_duplicate": True}
            eid = store.new_id(self.p, "evidence")
            meta = {
                "id": eid,
                "type": "evidence",
                "source": source,
                "kind": kind,
                "quote": quote or "",
                "quote_verified": verified,
                "locator": locator or auto_loc or "",
                "note": note or "",
                "topics": [topic],
                "questions": split_list(questions),
                "concepts": split_list(concepts),
                "created": now(),
                "run": run or "",
            }
            self.save("evidence", meta, "")
            if topic not in (smeta.get("topics") or []):
                smeta["topics"] = uniq((smeta.get("topics") or []) + [topic])
                self.save("source", smeta, store.read_entity(self.p.entity_path("source", source))[1])
            short = (quote or note or "")[:90]
            self.log_change(topic, "evidence", eid, f"evidence from {source}: “{short}”", run)
        return meta

    # ------------------------------------------------------------------ claims

    def add_claim(self, topic: str, text: str, support=None, counter=None, kind: str = "finding",
                  strength: str = "moderate", uncertainty: str = "", concepts=None,
                  contradicts=None, questions=None, run: str | None = None, reasoning: str = "") -> dict:
        self.topic(topic)
        _enum(kind, CLAIM_KIND, "kind")
        _enum(strength, STRENGTH, "strength")
        support, counter = split_list(support), split_list(counter)
        for e in support + counter:
            if not self.exists("evidence", e):
                raise KwError(f"no evidence '{e}'", 2)
        for c in split_list(contradicts):
            if not self.exists("claim", c):
                raise KwError(f"no claim '{c}'", 2)
        if kind == "finding" and not support:
            raise KwError("a finding needs supporting evidence (--support ev-…); "
                          "otherwise record it as --kind hypothesis or interpretation", 2)
        if not support and strength not in ("unsupported", "weak"):
            strength = "unsupported"
        text = " ".join(str(text).split())
        with store.locked(self.p):
            norm = _norm_text(text)
            for m in self.metas("claim", topic):
                if _norm_text(m.get("text", "")) == norm and m.get("state") == "current":
                    return {**m, "_duplicate": True}
            cid = store.new_id(self.p, "claim")
            meta = {
                "id": cid,
                "type": "claim",
                "text": text,
                "topics": [topic],
                "concepts": split_list(concepts),
                "kind": kind,
                "strength": strength,
                "state": "current",
                "support": support,
                "counter": counter,
                "contradicts": split_list(contradicts),
                "questions": split_list(questions),
                "uncertainty": uncertainty or "",
                "supersedes": [],
                "superseded_by": "",
                "created": now(),
                "updated": now(),
                "last_verified": store.today(),
                "run": run or "",
            }
            body = "## Reasoning\n" + (reasoning.strip() + "\n" if reasoning else "") + "\n## Revisions\n"
            self.save("claim", meta, body)
            self.log_change(topic, "claim", cid, f"claim added [{strength} {kind}]: {text}", run)
            # Contradiction is symmetric and never resolved by overwriting.
            for other in meta["contradicts"]:
                om, ob = self.load("claim", other)
                om["contradicts"] = uniq((om.get("contradicts") or []) + [cid])
                if om.get("strength") != "contested":
                    ob = _add_revision(ob, f"strength {om.get('strength')} → contested: contradicted by {cid}", run)
                    om["strength"] = "contested"
                om["updated"] = now()
                self.save("claim", om, ob)
                self.log_change(topic, "claim", other, f"claim contested by {cid}: {om['text']}", run)
            if meta["contradicts"] and strength != "contested":
                meta["strength"] = "contested"
                self.save("claim", meta, _add_revision(body, f"strength {strength} → contested: contradicts "
                                                       + ", ".join(meta["contradicts"]), run))
        return meta

    def update_claim(self, cid: str, reason: str, run: str | None = None, strength: str | None = None,
                     kind: str | None = None, add_support=None, add_counter=None, uncertainty=None,
                     text: str | None = None, verified: bool = False, concepts=None,
                     contradicts=None) -> dict:
        if not reason:
            raise KwError("--reason is required: every revision says why", 2)
        _enum(strength, STRENGTH, "strength")
        _enum(kind, CLAIM_KIND, "kind")
        with store.locked(self.p):
            meta, body = self.load("claim", cid)
            if meta.get("state") != "current":
                raise KwError(f"{cid} is {meta.get('state')}; revise its replacement "
                              f"{meta.get('superseded_by') or ''} instead")
            changes = []
            for e in split_list(add_support) + split_list(add_counter):
                if not self.exists("evidence", e):
                    raise KwError(f"no evidence '{e}'", 2)
            if add_support:
                meta["support"] = uniq((meta.get("support") or []) + split_list(add_support))
                changes.append("support + " + ", ".join(split_list(add_support)))
            if add_counter:
                meta["counter"] = uniq((meta.get("counter") or []) + split_list(add_counter))
                changes.append("counter-evidence + " + ", ".join(split_list(add_counter)))
            if strength and strength != meta.get("strength"):
                changes.append(f"strength {meta.get('strength')} → {strength}")
                meta["strength"] = strength
            if kind and kind != meta.get("kind"):
                changes.append(f"kind {meta.get('kind')} → {kind}")
                meta["kind"] = kind
            if uncertainty is not None:
                meta["uncertainty"] = uncertainty
                changes.append("uncertainty updated")
            if text and " ".join(text.split()) != meta["text"]:
                changes.append(f"text revised (was: “{meta['text']}”)")
                meta["text"] = " ".join(text.split())
            if concepts:
                meta["concepts"] = uniq((meta.get("concepts") or []) + split_list(concepts))
            new_contra = [c for c in split_list(contradicts) if c not in (meta.get("contradicts") or [])]
            for other in new_contra:
                if other == cid or not self.exists("claim", other):
                    raise KwError(f"no claim '{other}' to contradict", 2)
            if new_contra:
                meta["contradicts"] = uniq((meta.get("contradicts") or []) + new_contra)
                changes.append("contradicts " + ", ".join(new_contra))
                if meta.get("strength") != "contested":
                    changes.append(f"strength {meta.get('strength')} → contested")
                    meta["strength"] = "contested"
                for other in new_contra:
                    om, ob = self.load("claim", other)
                    om["contradicts"] = uniq((om.get("contradicts") or []) + [cid])
                    if om.get("strength") != "contested":
                        ob = _add_revision(ob, f"strength {om.get('strength')} → contested: contradicted by {cid} — {reason}", run)
                        om["strength"] = "contested"
                    om["updated"] = now()
                    self.save("claim", om, ob)
            if verified:
                meta["last_verified"] = store.today()
                meta.pop("needs_verification", None)
                changes.append("re-verified")
            if not changes:
                return meta
            meta["updated"] = now()
            body = _add_revision(body, "; ".join(changes) + f" — {reason}", run)
            self.save("claim", meta, body)
            for t in meta.get("topics") or []:
                self.log_change(t, "claim", cid, f"claim revised: {meta['text']}", run,
                                detail="; ".join(changes) + f" — {reason}")
        return meta

    def supersede_claim(self, old: str, new: str, reason: str, run: str | None = None) -> dict:
        if not reason:
            raise KwError("--reason is required", 2)
        if old == new:
            raise KwError("a claim cannot supersede itself", 2)
        with store.locked(self.p):
            om, ob = self.load("claim", old)
            nm, nb = self.load("claim", new)
            if om.get("state") != "current":
                raise KwError(f"{old} is already {om.get('state')}")
            om["state"] = "superseded"
            om["superseded_by"] = new
            om["updated"] = now()
            self.save("claim", om, _add_revision(ob, f"superseded by {new} — {reason}", run))
            nm["supersedes"] = uniq((nm.get("supersedes") or []) + [old])
            nm["updated"] = now()
            self.save("claim", nm, _add_revision(nb, f"supersedes {old} — {reason}", run))
            for t in om.get("topics") or []:
                self.log_change(t, "claim", old, f"claim superseded by {new}: {om['text']}", run, detail=reason)
        return nm

    def merge_claims(self, keep: str, dup: str, reason: str, run: str | None = None) -> dict:
        """Duplicate → superseded by `keep`, which inherits its evidence and links."""
        with store.locked(self.p):
            km, kb_ = self.load("claim", keep)
            dm, _ = self.load("claim", dup)
            for k in ("support", "counter", "concepts", "questions", "contradicts"):
                km[k] = uniq((km.get(k) or []) + (dm.get(k) or []))
            km["topics"] = uniq((km.get("topics") or []) + (dm.get("topics") or []))
            self.save("claim", km, _add_revision(kb_, f"merged duplicate {dup}: evidence and links combined", run))
            return self.supersede_claim(dup, keep, f"duplicate of {keep}: {reason}", run)

    # ------------------------------------------------------------------ concepts

    def add_concept(self, topic: str, title: str, cid: str | None = None, summary: str = "",
                    explanation: str = "", details: str = "", prompts=None, prerequisites=None,
                    related=None, claims=None, sources=None, perspective: str = "", aliases=None,
                    run: str | None = None) -> dict:
        self.topic(topic)
        cid = cid or store.slugify(title, 48)
        if not store.valid_slug(cid):
            raise KwError(f"invalid concept id '{cid}'", 2)
        with store.locked(self.p):
            if self.exists("concept", cid):
                meta, body = self.load("concept", cid)
                if topic not in (meta.get("topics") or []):
                    meta["topics"] = uniq((meta.get("topics") or []) + [topic])
                    self.save("concept", meta, body)
                    self.log_change(topic, "concept", cid, f"existing concept linked: {meta['title']}", run)
                return {**meta, "_duplicate": True}
            meta = {
                "id": cid,
                "type": "concept",
                "title": title,
                "aliases": split_list(aliases),
                "topics": [topic],
                "perspective": perspective or "",
                "summary": " ".join(summary.split()),
                "prerequisites": split_list(prerequisites),
                "related": _parse_related(related),
                "claims": split_list(claims),
                "sources": split_list(sources),
                "created": now(),
                "updated": now(),
                "run": run or "",
            }
            sections = {"Explanation": explanation, "Details": details,
                        "Prompts": _prompts_md(prompts)}
            self.save("concept", meta, render_sections(sections))
            self.log_change(topic, "concept", cid, f"concept added: {title}", run)
        return meta

    def update_concept(self, cid: str, run: str | None = None, reason: str = "", **fields) -> dict:
        with store.locked(self.p):
            meta, body = self.load("concept", cid)
            sections = parse_sections(body)
            changed = []
            for k in ("title", "summary", "perspective"):
                if fields.get(k):
                    meta[k] = " ".join(str(fields[k]).split())
                    changed.append(k)
            for k in ("prerequisites", "claims", "sources", "aliases"):
                if fields.get(k):
                    meta[k] = uniq((meta.get(k) or []) + split_list(fields[k]))
                    changed.append(k)
            if fields.get("related"):
                have = {(r["id"], r.get("rel")) for r in meta.get("related") or []}
                for r in _parse_related(fields["related"]):
                    if (r["id"], r["rel"]) not in have:
                        meta.setdefault("related", []).append(r)
                changed.append("related")
            if fields.get("topic"):
                meta["topics"] = uniq((meta.get("topics") or []) + [fields["topic"]])
            for sec, key in (("Explanation", "explanation"), ("Details", "details"),
                             ("Alternative explanation", "alternative")):
                if fields.get(key):
                    if sections.get(sec, "").strip() and key != "alternative":
                        sections.setdefault("Previous versions", "")
                        sections["Previous versions"] = (
                            sections["Previous versions"].rstrip()
                            + f"\n\n### {sec} before {now()}\n\n"
                            + sections[sec].strip() + "\n"
                        ).strip()
                    sections[sec] = fields[key]
                    changed.append(key)
            if fields.get("prompts"):
                existing = sections.get("Prompts", "").rstrip()
                sections["Prompts"] = (existing + "\n" + _prompts_md(fields["prompts"])).strip()
                changed.append("prompts")
            if not changed:
                return meta
            meta["updated"] = now()
            self.save("concept", meta, render_sections(sections))
            for t in meta.get("topics") or []:
                self.log_change(t, "concept", cid, f"concept updated ({', '.join(changed)}): {meta['title']}",
                                run, detail=reason or None)
        return meta

    def concept_sections(self, cid: str) -> tuple[dict, dict]:
        meta, body = self.load("concept", cid)
        return meta, parse_sections(body)

    # ------------------------------------------------------------------ validation

    def check(self) -> list[tuple[str, str]]:
        """(level, message) problems: 'error' breaks references, 'warn' is advice."""
        probs: list[tuple[str, str]] = []
        topics = {}
        for t in self.topics():
            topics[t["id"]] = t
            if t.get("depth") not in DEPTHS:
                probs.append(("error", f"topic {t['id']}: depth '{t.get('depth')}' invalid"))
            if t.get("status") not in TOPIC_STATUS:
                probs.append(("error", f"topic {t['id']}: status '{t.get('status')}' invalid"))
        ids = {k: {m["id"]: m for m in self.metas(k)} for k in store.KIND_DIRS}

        def ref(kind, eid, where):
            if eid and eid not in ids[kind]:
                probs.append(("error", f"{where}: unknown {kind} '{eid}'"))

        for q in ids["question"].values():
            if q.get("topic") not in topics:
                probs.append(("error", f"{q['id']}: unknown topic '{q.get('topic')}'"))
            if q.get("status") not in Q_STATUS:
                probs.append(("error", f"{q['id']}: status '{q.get('status')}' invalid"))
            for d in q.get("depends_on") or []:
                ref("question", d, q["id"])
            if q.get("status") == "answered" and not q.get("result"):
                probs.append(("warn", f"{q['id']}: answered but has no result"))
        for e in ids["evidence"].values():
            ref("source", e.get("source"), e["id"])
            if e.get("kind") == "quote" and e.get("quote_verified") is False:
                probs.append(("warn", f"{e['id']}: quote not verified against the stored source text"))
        for c in ids["claim"].values():
            for k in ("support", "counter"):
                for e in c.get(k) or []:
                    ref("evidence", e, c["id"])
            for o in (c.get("contradicts") or []) + (c.get("supersedes") or []):
                ref("claim", o, c["id"])
            if c.get("superseded_by"):
                ref("claim", c["superseded_by"], c["id"])
            if c.get("strength") not in STRENGTH:
                probs.append(("error", f"{c['id']}: strength '{c.get('strength')}' invalid"))
            if c.get("kind") == "finding" and not c.get("support") and c.get("state") == "current":
                probs.append(("warn", f"{c['id']}: a finding without supporting evidence"))
            for cc in c.get("concepts") or []:
                ref("concept", cc, c["id"])
        for c in ids["concept"].values():
            for pr in c.get("prerequisites") or []:
                ref("concept", pr, c["id"])
            for r in c.get("related") or []:
                ref("concept", r.get("id"), c["id"])
            for cl in c.get("claims") or []:
                ref("claim", cl, c["id"])
            for s in c.get("sources") or []:
                ref("source", s, c["id"])
            if not c.get("summary"):
                probs.append(("warn", f"concept {c['id']}: no summary"))
        for s in ids["source"].values():
            if s.get("extraction") == "ok" and not self.source_content_path(s["id"]).exists():
                probs.append(("warn", f"{s['id']}: extracted text missing from library/ "
                                      "(restore a backup or `kw source refetch`)"))
        return probs


# ---------------------------------------------------------------------- helpers


def _norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "").lower()).strip(" .?!;:")


def _add_revision(body: str, text: str, run: str | None) -> str:
    line = f"- {now()}" + (f" [{run}]" if run else "") + f": {text}"
    if "## Revisions" not in body:
        body = body.rstrip() + "\n\n## Revisions\n"
    return body.rstrip() + "\n" + line + "\n"


def _parse_related(related) -> list[dict]:
    """'other-concept:contrasts,third' (or a list of {id, rel}) -> [{id, rel}]."""
    if not related:
        return []
    if isinstance(related, list) and all(isinstance(r, dict) for r in related):
        return [{"id": r["id"], "rel": _enum(r.get("rel", "related"), RELATIONS, "relation")} for r in related]
    out = []
    for item in split_list(related):
        cid, _, rel = item.partition(":")
        out.append({"id": cid.strip(), "rel": _enum(rel.strip() or "related", RELATIONS, "relation")})
    return out


def _prompts_md(prompts) -> str:
    lines = []
    for p in prompts or []:
        kind, sep, text = str(p).partition(":")
        if not sep or kind.strip() not in PROMPT_KINDS:
            kind, text = "reflect", str(p)
        lines.append(f"- **{kind.strip()}**: {text.strip()}")
    return "\n".join(lines)


def parse_prompts(md: str) -> list[dict]:
    out = []
    for line in (md or "").splitlines():
        m = re.match(r"^\s*-\s+\*\*(\w+)\*\*:\s*(.+)$", line)
        if m:
            out.append({"kind": m.group(1), "text": m.group(2).strip()})
        elif re.match(r"^\s*-\s+\S", line):
            out.append({"kind": "reflect", "text": line.strip()[2:].strip()})
    return out


SECTION_ORDER = ["Explanation", "Details", "Alternative explanation", "Prompts", "Previous versions"]


def parse_sections(body: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    cur, buf = None, []
    for line in (body or "").splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            if cur is not None:
                sections[cur] = "\n".join(buf).strip()
            cur, buf = m.group(1), []
        else:
            buf.append(line)
    if cur is not None:
        sections[cur] = "\n".join(buf).strip()
    elif "".join(buf).strip():
        sections["Explanation"] = "\n".join(buf).strip()
    return sections


def render_sections(sections: dict[str, str]) -> str:
    keys = [k for k in SECTION_ORDER if k in sections] + [k for k in sections if k not in SECTION_ORDER]
    out = []
    for k in keys:
        v = (sections.get(k) or "").strip()
        if not v and k not in ("Explanation", "Prompts"):
            continue
        out.append(f"## {k}\n\n{v}\n" if v else f"## {k}\n")
    return "\n".join(out)
