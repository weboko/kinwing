"""The user's learning state, kept apart from the knowledge base.

    learning/state.json        per concept/source: observed behaviour, self-reports, interest,
                               revisit schedule; per topic: last visit
    learning/events.jsonl      append-only log of what the user did (views, marks, answers…)
    learning/highlights/*.md   highlights and annotations (the user's own words)
    learning/answers/*.md      the user's written explanations/answers to prompts
    learning/sessions/*.json   planned learning sessions

Three kinds of knowledge about the user are kept distinct and labelled:
  observed       what the user did (opened, read to the end, answered a prompt)
  self-reported  what the user said ("I know this", "I'm confused")
  inferred       kinwing's transparent rule-based reading of the two, with its basis
Nothing is ever "mastered" because a page was opened or an agent researched it.
"""

from __future__ import annotations

import datetime as dt
import re
import secrets

from . import ingest, store
from .kb import KB, parse_prompts, parse_sections
from .store import KwError, now, parse_ts, split_list, uniq

SELF_REPORT = ("new", "heard", "familiar", "known", "confused")
INTEREST = ("high", "normal", "low")
DEPTHS = ("glance", "read", "deep")
REVISIT_DAYS = [1, 3, 7, 21, 60, 150]
ASK_KINDS = {
    "question": ("A question from reading", "medium"),
    "challenge": ("The user is not convinced", "high"),
    "deeper": ("The user wants to go deeper", "high"),
    "explain-differently": ("The user asks for another explanation", "medium"),
    "gap": ("The user found a gap", "medium"),
}


def _id(prefix: str) -> str:
    return f"{prefix}-{dt.datetime.now(dt.timezone.utc):%Y%m%d}-" + "".join(
        secrets.choice(store.ID_ALPHABET) for _ in range(5))


class Learning:
    def __init__(self, kb: KB):
        self.kb = kb
        self.p = kb.p
        self.dir = kb.p.learning

    # ------------------------------------------------------------------ state

    def _state_path(self):
        return self.dir / "state.json"

    def state(self) -> dict:
        st = store.read_json(self._state_path(), {})
        st.setdefault("version", 1)
        for k in ("concepts", "sources", "topics"):
            st.setdefault(k, {})
        st.setdefault("last_position", None)
        return st

    def _mutate(self, fn):
        with store.locked(self.p):
            st = self.state()
            res = fn(st)
            store.write_json(self._state_path(), st)
            return res

    def _event(self, typ: str, target: str, **data) -> None:
        store.append_line(self.dir / "events.jsonl", {"at": now(), "type": typ, "target": target, **data})

    def _entry(self, st: dict, kind: str, eid: str) -> dict:
        bucket = st["concepts" if kind == "concept" else "sources"]
        e = bucket.setdefault(eid, {})
        e.setdefault("observed", {})
        return e

    # ------------------------------------------------------------------ observed behaviour

    def record_progress(self, kind: str, eid: str, fraction: float | None = None, para: int | None = None,
                        depth: str | None = None, seconds: float = 0, completed: bool = False,
                        view: bool = False) -> dict:
        if kind not in ("concept", "source"):
            raise KwError("kind must be concept or source", 2)
        if not self.kb.exists(kind, eid):
            raise KwError(f"no {kind} '{eid}'", 2)
        if depth and depth not in DEPTHS:
            raise KwError(f"depth must be one of {', '.join(DEPTHS)}", 2)

        def fn(st):
            e = self._entry(st, kind, eid)
            o = e["observed"]
            o.setdefault("first_seen", now())
            o["last_seen"] = now()
            if view:
                o["views"] = int(o.get("views") or 0) + 1
            if seconds:
                o["seconds"] = round(float(o.get("seconds") or 0) + min(float(seconds), 1800), 1)
            if fraction is not None:
                f = max(0.0, min(1.0, float(fraction)))
                o["progress"] = round(max(float(o.get("progress") or 0), f), 3)
                o["position"] = round(f, 3)
            if para is not None:
                o["para"] = int(para)
            if depth:
                order = {d: i for i, d in enumerate(DEPTHS)}
                if order[depth] >= order.get(o.get("depth_max") or "glance", 0):
                    o["depth_max"] = depth
            if completed and not o.get("completed_at"):
                o["completed_at"] = now()
                if kind == "concept":
                    self._schedule_revisit(e, reset=False)
            st["last_position"] = {"kind": kind, "id": eid, "at": now()}
            return e

        e = self._mutate(fn)
        if view or completed:
            self._event("complete" if completed else "view", f"{kind}:{eid}", depth=depth)
        return e

    def _schedule_revisit(self, e: dict, reset: bool) -> None:
        r = e.setdefault("revisit", {"step": -1})
        step = 0 if reset else min(int(r.get("step", -1)) + 1, len(REVISIT_DAYS) - 1)
        r["step"] = step
        r["due"] = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=REVISIT_DAYS[step])).strftime("%Y-%m-%d")
        r["last"] = now()

    def mark_revisited(self, concept: str) -> dict:
        def fn(st):
            e = self._entry(st, "concept", concept)
            self._schedule_revisit(e, reset=False)
            return e
        e = self._mutate(fn)
        self._event("revisit", f"concept:{concept}", due=e["revisit"]["due"])
        return e

    # ------------------------------------------------------------------ self-reports

    def self_report(self, concept: str, value: str, note: str | None = None) -> dict:
        if value not in SELF_REPORT:
            raise KwError(f"value must be one of {', '.join(SELF_REPORT)}", 2)
        if not self.kb.exists("concept", concept):
            raise KwError(f"no concept '{concept}'", 2)

        def fn(st):
            e = self._entry(st, "concept", concept)
            e["self_report"] = {"value": value, "at": now(), **({"note": note} if note else {})}
            if value == "confused":
                self._schedule_revisit(e, reset=True)
            if value == "known":
                e.pop("revisit", None)
            return e

        e = self._mutate(fn)
        self._event("self_report", f"concept:{concept}", value=value, note=note or "")
        return e

    def set_interest(self, concept: str, value: str) -> dict:
        if value not in INTEREST:
            raise KwError(f"value must be one of {', '.join(INTEREST)}", 2)
        if not self.kb.exists("concept", concept):
            raise KwError(f"no concept '{concept}'", 2)

        def fn(st):
            e = self._entry(st, "concept", concept)
            e["interest"] = {"value": value, "at": now()}
            return e

        e = self._mutate(fn)
        self._event("interest", f"concept:{concept}", value=value)
        return e

    def visit_topic(self, topic: str) -> dict:
        self.kb.topic(topic)

        def fn(st):
            t = st["topics"].setdefault(topic, {})
            t["previous_visit"] = t.get("last_visit")
            t["last_visit"] = store.now_ms()
            return t
        return self._mutate(fn)

    def changes_since_visit(self, topic: str) -> tuple[str | None, list[dict]]:
        t = self.state()["topics"].get(topic) or {}
        since = t.get("last_visit")
        ch = self.kb.changes(topic)
        if since:
            ch = [c for c in ch if c.get("at", "") > since]
        return since, ch

    # ------------------------------------------------------------------ highlights

    def _hl_path(self, hid: str):
        return self.dir / "highlights" / f"{hid}.md"

    def add_highlight(self, kind: str, target: str, quote: str, note: str = "", tags=None, prefix: str = "",
                      suffix: str = "", section: str = "", topic: str | None = None) -> dict:
        quote = (quote or "").strip()
        if len(quote) < 3:
            raise KwError("highlight text is empty", 2)
        if kind not in ("source", "concept", "overview"):
            raise KwError("target kind must be source, concept or overview", 2)
        if kind == "overview":
            self.kb.topic(target)
            topics = [target]
            is_source_quote, locator, source = False, "", ""
        else:
            meta, _ = self.kb.load(kind, target)
            topics = meta.get("topics") or []
            is_source_quote, locator, source = False, "", ""
            if kind == "source":
                text = self.kb.source_text(target) or ""
                hit = ingest.find_quote(text, quote) if text else None
                is_source_quote = hit is not None
                locator = f"¶{hit['para']}" if hit else ""
                source = target
        hid = _id("h")
        meta = {
            "id": hid,
            "type": "highlight",
            "target_kind": kind,
            "target_id": target,
            "topics": [topic] if topic else topics,
            "quote": quote,
            "quote_origin": "source text (exact)" if is_source_quote else
                            ("source text (not matched exactly)" if kind == "source" else "AI-written synthesis"),
            "source": source,
            "locator": locator,
            "section": section or "",
            "prefix": prefix[-60:],
            "suffix": suffix[:60],
            "tags": split_list(tags),
            "created": now(),
            "updated": now(),
        }
        with store.locked(self.p):
            store.write_entity(self._hl_path(hid), meta, note.strip())
        self._event("highlight", f"{kind}:{target}", id=hid)
        return {**meta, "note": note.strip()}

    def update_highlight(self, hid: str, note: str | None = None, tags=None) -> dict:
        path = self._hl_path(hid)
        if not path.exists():
            raise KwError(f"no highlight '{hid}'", 2)
        with store.locked(self.p):
            meta, body = store.read_entity(path)
            if note is not None:
                body = note.strip()
            if tags is not None:
                meta["tags"] = split_list(tags)
            meta["updated"] = now()
            store.write_entity(path, meta, body)
        self._event("annotate", f"{meta['target_kind']}:{meta['target_id']}", id=hid)
        return {**meta, "note": body.strip()}

    def delete_highlight(self, hid: str) -> None:
        path = self._hl_path(hid)
        if not path.exists():
            raise KwError(f"no highlight '{hid}'", 2)
        with store.locked(self.p):
            trash = self.dir / "highlights" / ".deleted"
            trash.mkdir(exist_ok=True)
            path.replace(trash / path.name)
        self._event("unhighlight", hid)

    def highlights(self, topic: str | None = None, target: str | None = None) -> list[dict]:
        out = []
        d = self.dir / "highlights"
        for f in sorted(d.glob("h-*.md")) if d.exists() else []:
            meta, body = store.read_entity(f)
            if topic and topic not in (meta.get("topics") or []):
                continue
            if target and f"{meta['target_kind']}:{meta['target_id']}" != target:
                continue
            out.append({**meta, "note": body.strip()})
        out.sort(key=lambda h: h.get("created", ""))
        return out

    # ------------------------------------------------------------------ answers (evidence of understanding)

    def add_answer(self, concept: str, prompt: str, text: str, kind: str = "explain") -> dict:
        if not self.kb.exists("concept", concept):
            raise KwError(f"no concept '{concept}'", 2)
        text = (text or "").strip()
        if not text:
            raise KwError("the answer is empty", 2)
        aid = _id("a")
        meta = {"id": aid, "type": "answer", "concept": concept, "prompt": prompt, "prompt_kind": kind,
                "created": now(), "review": {}}
        with store.locked(self.p):
            store.write_entity(self.dir / "answers" / f"{aid}.md", meta, text)

            def fn(st):
                e = self._entry(st, "concept", concept)
                e["observed"]["answers"] = int(e["observed"].get("answers") or 0) + 1
                self._schedule_revisit(e, reset=False)
            self._mutate(fn)
        self._event("answer", f"concept:{concept}", id=aid)
        return {**meta, "text": text}

    def answers(self, pending: bool = False, concept: str | None = None) -> list[dict]:
        out = []
        d = self.dir / "answers"
        for f in sorted(d.glob("a-*.md")) if d.exists() else []:
            meta, body = store.read_entity(f)
            if pending and (meta.get("review") or {}).get("assessment"):
                continue
            if concept and meta.get("concept") != concept:
                continue
            out.append({**meta, "text": body.strip()})
        return out

    def review_answer(self, aid: str, assessment: str, note: str = "") -> dict:
        if assessment not in ("sound", "partial", "misconception"):
            raise KwError("assessment must be sound, partial or misconception", 2)
        path = self.dir / "answers" / f"{aid}.md"
        if not path.exists():
            raise KwError(f"no answer '{aid}'", 2)
        with store.locked(self.p):
            meta, body = store.read_entity(path)
            meta["review"] = {"assessment": assessment, "note": note, "by": "agent", "at": now()}
            store.write_entity(path, meta, body)
        self._event("answer_review", f"concept:{meta['concept']}", id=aid, assessment=assessment)
        return meta

    # ------------------------------------------------------------------ feedback into research

    def ask(self, kind: str, text: str, topic: str | None = None, concept: str | None = None,
            target: str | None = None, quote: str | None = None) -> dict:
        if kind not in ASK_KINDS:
            raise KwError(f"kind must be one of {', '.join(ASK_KINDS)}", 2)
        text = " ".join((text or "").split())
        cmeta = self.kb.load("concept", concept)[0] if concept else None
        topic = topic or ((cmeta.get("topics") or [None])[0] if cmeta else None)
        if not topic:
            raise KwError("a topic (or a concept that belongs to one) is required", 2)
        label, priority = ASK_KINDS[kind]
        subject = f"“{cmeta['title']}”" if cmeta else "this topic"
        if kind == "explain-differently":
            qtext = f"Find another way to explain {subject}" + (f": {text}" if text else "")
        elif kind == "deeper":
            qtext = f"Go deeper on {subject}" + (f": {text}" if text else "")
        elif kind == "challenge":
            qtext = f"Check {subject} — the user is not convinced" + (f": {text}" if text else "")
        else:
            if not text:
                raise KwError("the question is empty", 2)
            qtext = text
        ctx = f"{label} (from the reader)"
        if quote:
            ctx += f"; about the passage: “{quote[:300]}”"
        if target:
            ctx += f"; on {target}"
        ref = _id("lq")
        q = self.kb.add_question(topic, qtext, origin="learning", priority=priority,
                                 value="high" if kind in ("challenge", "deeper") else "medium", cost="medium",
                                 concepts=[concept] if concept else None, asked_by="user", learning_ref=ref,
                                 context=ctx)
        self._event("ask", target or (f"concept:{concept}" if concept else f"topic:{topic}"), kind=kind,
                    question=q["id"], text=text, ref=ref)
        return q

    def my_questions(self) -> list[dict]:
        return [q for q in self.kb.metas("question") if q.get("asked_by") in ("user", "reader")
                or q.get("origin") == "learning"]

    # ------------------------------------------------------------------ inference & recommendation

    def infer(self, concept: str, st: dict | None = None, answers: list[dict] | None = None) -> dict:
        st = st or self.state()
        e = st["concepts"].get(concept) or {}
        o = e.get("observed") or {}
        sr = (e.get("self_report") or {}).get("value")
        ans = answers if answers is not None else self.answers(concept=concept)
        sound = [a for a in ans if (a.get("review") or {}).get("assessment") == "sound"]
        mis = [a for a in ans if (a.get("review") or {}).get("assessment") == "misconception"]
        basis = []
        if o.get("views"):
            basis.append(f"opened {o['views']}×")
        if o.get("completed_at"):
            basis.append(f"read to the end ({o.get('depth_max') or 'read'})")
        elif o.get("progress"):
            basis.append(f"read {int(100 * float(o['progress']))}%")
        if ans:
            basis.append(f"{len(ans)} written answer(s)" + (f", {len(sound)} reviewed sound" if sound else ""))
        if sr:
            basis.append(f"you said “{sr}”")
        if sr == "confused" or mis:
            status = "needs another look"
        elif sr == "known":
            status = "self-reported known"
        elif sound:
            status = "shows understanding"
        elif ans:
            status = "practised"
        elif o.get("completed_at"):
            status = "read"
        elif o.get("views") or o.get("progress"):
            status = "started"
        else:
            status = "not encountered"
        return {"status": status, "basis": "; ".join(basis) or "no activity yet",
                "note": "inferred by rule from observed behaviour and self-reports; not a measure of mastery"}

    def overview(self, topic: str | None = None) -> dict:
        st = self.state()
        all_ans = self.answers()
        rows = []
        for c in self.kb.metas("concept", topic):
            ans = [a for a in all_ans if a.get("concept") == c["id"]]
            e = st["concepts"].get(c["id"]) or {}
            rows.append({"concept": c["id"], "title": c.get("title"), "observed": e.get("observed") or {},
                         "self_report": e.get("self_report"), "interest": e.get("interest"),
                         "revisit": e.get("revisit"), "inferred": self.infer(c["id"], st, ans)})
        return {"concepts": rows}

    def _satisfied(self, cid: str, st: dict, ans_by: dict) -> bool:
        inf = self.infer(cid, st, ans_by.get(cid, []))["status"]
        sr = ((st["concepts"].get(cid) or {}).get("self_report") or {}).get("value")
        return inf in ("self-reported known", "shows understanding", "practised", "read") or sr == "familiar"

    def recommend(self, topic: str | None = None, limit: int = 5) -> list[dict]:
        st = self.state()
        all_ans = self.answers()
        ans_by: dict[str, list] = {}
        for a in all_ans:
            ans_by.setdefault(a["concept"], []).append(a)
        topics = {t["id"]: t for t in self.kb.topics()}
        today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        out = []
        for c in self.kb.metas("concept", topic):
            if topic is None and not any(topics.get(t, {}).get("status") != "archived" for t in c.get("topics") or []):
                continue
            e = st["concepts"].get(c["id"]) or {}
            o = e.get("observed") or {}
            sr = (e.get("self_report") or {}).get("value")
            if sr == "known":
                continue  # the user said they know it: don't push it
            inf = self.infer(c["id"], st, ans_by.get(c["id"], []))
            score, reasons = 1.0, []
            interest = (e.get("interest") or {}).get("value")
            if interest == "high":
                score += 2
                reasons.append("you marked it interesting")
            elif interest == "low":
                score -= 1.5
                reasons.append("you marked it low interest")
            if any(c["id"] in (topics.get(t, {}).get("learning_priorities") or []) for t in c.get("topics") or []):
                score += 2
                reasons.append("a learning priority of the topic")
            if any(c["id"] in (topics.get(t, {}).get("known_concepts") or []) for t in c.get("topics") or []):
                continue
            if inf["status"] == "needs another look":
                score += 1.5
                alt = "Alternative explanation" in parse_sections(self.kb.load("concept", c["id"])[1])
                reasons.append("you found it confusing" + (" — there is now an alternative explanation" if alt else ""))
            if o.get("progress") and float(o["progress"]) < 0.9 and not o.get("completed_at"):
                score += 1.2
                reasons.append(f"unfinished ({int(100 * float(o['progress']))}% read)")
            if inf["status"] == "not encountered":
                score += 0.8
                reasons.append("new to you")
            due = (e.get("revisit") or {}).get("due")
            if due and due <= today:
                score += 1.5
                reasons.append(f"due for revisiting (since {due})")
            elif inf["status"] in ("read", "practised", "shows understanding") and not due:
                score -= 1
            if o.get("last_seen") and c.get("updated", "") > o["last_seen"]:
                score += 1
                reasons.append("updated by research since you last read it")
            unmet = [p for p in c.get("prerequisites") or [] if not self._satisfied(p, st, ans_by)
                     and self.kb.exists("concept", p)]
            if unmet:
                score -= 1.5
                reasons.append("builds on " + ", ".join(unmet) + " (start there)")
            if not c.get("prerequisites"):
                score += 0.3
            if inf["status"] in ("shows understanding",) and not (due and due <= today):
                continue
            out.append({"concept": c["id"], "title": c.get("title"), "summary": c.get("summary"),
                        "score": round(score, 2), "reasons": reasons or ["part of the topic"],
                        "inferred": inf, "topics": c.get("topics")})
        out.sort(key=lambda r: -r["score"])
        return out[:limit]

    # ------------------------------------------------------------------ sessions

    def _minutes(self, cid: str, depth: str) -> int:
        meta, body = self.kb.load("concept", cid)
        secs = parse_sections(body)
        words = len((meta.get("summary") or "").split())
        if depth in ("read", "deep"):
            words += len(secs.get("Explanation", "").split())
        if depth == "deep":
            words += len(secs.get("Details", "").split()) + 150 * len(meta.get("claims") or [])
        return max(1, round(words / 200 + (2 if parse_prompts(secs.get("Prompts", "")) else 0)))

    def create_session(self, minutes: int = 15, topic: str | None = None) -> dict:
        minutes = max(3, min(int(minutes), 180))
        recs = self.recommend(topic=topic, limit=20)
        items, used = [], 0
        depth = "glance" if minutes <= 5 else ("read" if minutes <= 30 else "deep")
        for r in recs:
            m = self._minutes(r["concept"], depth)
            if used + m > minutes and items:
                continue
            items.append({"concept": r["concept"], "title": r["title"], "depth": depth, "minutes": m,
                          "reason": "; ".join(r["reasons"]), "done": False})
            used += m
            if used >= minutes:
                break
        sid = _id("s")
        s = {"id": sid, "created": now(), "topic": topic or "", "minutes": minutes, "planned_minutes": used,
             "items": items, "note": "Not a lesson: skip, reorder or stop whenever you like."}
        store.write_json(self.dir / "sessions" / f"{sid}.json", s)
        self._event("session", f"topic:{topic or '*'}", id=sid, minutes=minutes)
        return s

    def session(self, sid: str) -> dict:
        s = store.read_json(self.dir / "sessions" / f"{sid}.json", None)
        if not s:
            raise KwError(f"no session '{sid}'", 2)
        return s

    def session_step(self, sid: str, index: int, done: bool = True) -> dict:
        with store.locked(self.p):
            s = self.session(sid)
            if not 0 <= index < len(s["items"]):
                raise KwError("no such step", 2)
            s["items"][index]["done"] = done
            store.write_json(self.dir / "sessions" / f"{sid}.json", s)
        return s

    def sessions(self) -> list[dict]:
        d = self.dir / "sessions"
        return sorted((store.read_json(f, {}) for f in d.glob("s-*.json")), key=lambda s: s.get("created", ""),
                      reverse=True) if d.exists() else []

    def due(self, limit: int = 5) -> list[dict]:
        st = self.state()
        today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        out = []
        for cid, e in st["concepts"].items():
            due = (e.get("revisit") or {}).get("due")
            if due and due <= today and self.kb.exists("concept", cid) and \
                    (e.get("self_report") or {}).get("value") != "known":
                out.append({"concept": cid, "title": self.kb.load("concept", cid)[0].get("title"), "due": due})
        return sorted(out, key=lambda x: x["due"])[:limit]
