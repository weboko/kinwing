"""Obsidian / Zettelkasten export (one-way).

Two note styles:
  Sources/<title>.md   source-oriented: the user's highlights from one source as exact
                       quotations with block ids, the user's annotations, the AI summary
                       clearly marked as AI-written.
  Concepts/<title>.md  concept-oriented atomic note, only for concepts the user asks for:
                       the user's own thoughts first, then the AI synthesis (marked), key
                       evidence quotes with links to source notes, related concepts.
  Topics/<title>.md    a small map-of-content note linking what has been exported.

Exports never touch a real vault unless pointed at one. A manifest remembers what was
written; a note the user edited after export is not overwritten (unless --force): the new
version goes to .kinwing/pending/ instead.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from . import store, yamlio
from .kb import KB, parse_sections
from .learning import Learning
from .store import KwError, now, uniq

_BAD = re.compile(r'[\\/:*?"<>|#^\[\]]+')


def _fname(title: str) -> str:
    s = _BAD.sub(" ", title or "Untitled")
    s = re.sub(r"\s+", " ", s).strip().strip(".")
    return s[:120] or "Untitled"


def _yaml_list(items) -> list:
    return [x for x in items if x]


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _bq(text: str) -> str:
    return "\n".join("> " + line if line.strip() else ">" for line in (text or "").strip().splitlines())


class _Exporter:
    def __init__(self, kb: KB, out: Path, force: bool):
        self.kb, self.out, self.force = kb, out, force
        self.manifest_path = out / ".kinwing" / "manifest.json"
        self.manifest = store.read_json(self.manifest_path, {"notes": {}})
        self.files: list[dict] = []
        self.names: dict[str, str] = {k: v["name"] for k, v in self.manifest["notes"].items()}
        self.taken = {v["path"] for v in self.manifest["notes"].values()}

    def name_for(self, kw_id: str, folder: str, title: str) -> str:
        if kw_id in self.names:
            return self.names[kw_id]
        base = _fname(title)
        name, n = base, 2
        while f"{folder}/{name}.md" in self.taken:
            name = f"{base} ({n})"
            n += 1
        self.names[kw_id] = name
        self.taken.add(f"{folder}/{name}.md")
        return name

    def link(self, kw_id: str, label: str | None = None) -> str | None:
        name = self.names.get(kw_id)
        if not name:
            return None
        return f"[[{name}|{label}]]" if label and label != name else f"[[{name}]]"

    def write(self, kw_id: str, folder: str, name: str, meta: dict, body: str) -> None:
        rel = f"{folder}/{name}.md"
        path = self.out / rel
        prev = self.manifest["notes"].get(kw_id)
        meta = {**meta, "created": (prev or {}).get("first_exported") or now()[:10]}
        text = yamlio.join_frontmatter(meta, body)
        action = "created"
        if path.exists():
            current = path.read_text(encoding="utf-8")
            if current == text:
                action = "unchanged"
            elif prev and _sha(current) != prev.get("sha256") and not self.force:
                pending = self.out / ".kinwing" / "pending" / f"{name}.md"
                store.atomic_write(pending, text)
                self.files.append({"id": kw_id, "path": str(path), "action": "kept",
                                   "note": f"you edited it after export; new version in {pending}"})
                return
            else:
                action = "updated"
        if action != "unchanged":
            store.atomic_write(path, text)
        self.manifest["notes"][kw_id] = {"path": rel, "name": name, "sha256": _sha(text), "exported": now(),
                                         "first_exported": meta["created"]}
        self.files.append({"id": kw_id, "path": str(path), "action": action})

    def save_manifest(self):
        store.write_json(self.manifest_path, self.manifest)


def obsidian(kb: KB, highlights=None, concepts=None, topic: str | None = None, out: str | None = None,
             force: bool = False) -> dict:
    target = Path(out).expanduser().resolve() if out else kb.p.exports
    www = kb.p.www
    if target == www or www in target.parents:
        raise KwError(f"refusing to export personal notes into the public web root {www}")
    L = Learning(kb)
    all_hl = {h["id"]: h for h in L.highlights()}
    if highlights and highlights != ["all"]:
        missing = [h for h in highlights if h not in all_hl]
        if missing:
            raise KwError(f"no highlight(s): {', '.join(missing)}", 2)
        hls = [all_hl[h] for h in highlights]
    elif highlights == ["all"]:
        hls = [h for h in all_hl.values() if not topic or topic in (h.get("topics") or [])]
    else:
        hls = []
    concepts = list(concepts or [])
    for c in concepts:
        if not kb.exists("concept", c):
            raise KwError(f"no concept '{c}'", 2)
    if not hls and not concepts:
        raise KwError("nothing to export: pass --highlights ID,…|all and/or --concepts ID,…", 2)

    with store.locked(kb.p):
        ex = _Exporter(kb, target, force)
        by_source: dict[str, list] = {}
        loose: dict[str, list] = {}
        for h in hls:
            if h["target_kind"] == "source":
                by_source.setdefault(h["target_id"], []).append(h)
            elif h["target_kind"] == "concept" and h["target_id"] in concepts:
                continue  # goes into the concept note
            else:
                for t in (h.get("topics") or ["misc"])[:1]:
                    loose.setdefault(t, []).append(h)
        # Sources cited by exported concepts get notes too, so their links resolve.
        ev = {e["id"]: e for e in kb.metas("evidence")}
        concept_sources: dict[str, list[str]] = {}
        for cid in concepts:
            cmeta = kb.load("concept", cid)[0]
            sids = list(cmeta.get("sources") or [])
            for cl in kb.metas("claim"):
                if cl.get("state") == "current" and (cid in (cl.get("concepts") or []) or cl["id"] in (cmeta.get("claims") or [])):
                    sids += [ev[e]["source"] for e in cl.get("support") or [] if e in ev]
            concept_sources[cid] = uniq(s for s in sids if kb.exists("source", s))
        source_ids = uniq(list(by_source) + [s for v in concept_sources.values() for s in v])
        topics_touched = set()
        # Reserve names first so notes can link to each other.
        for sid in source_ids:
            ex.name_for(f"source:{sid}", "Sources", kb.load("source", sid)[0].get("title"))
        for cid in concepts:
            ex.name_for(f"concept:{cid}", "Concepts", kb.load("concept", cid)[0].get("title"))
        for t in kb.topics():
            ex.name_for(f"topic:{t['id']}", "Topics", t["title"])

        chosen = {h["id"] for h in hls}
        for sid in source_ids:
            # Keep highlights exported earlier, so a later export never drops them from the note.
            keep = [h for h in all_hl.values() if h["target_kind"] == "source" and h["target_id"] == sid
                    and (h["id"] in chosen or h.get("exported"))]
            topics_touched.update(_source_note(ex, kb, sid, keep, concepts))
        for cid in concepts:
            topics_touched.update(_concept_note(ex, kb, L, cid, [h for h in hls if h["target_kind"] == "concept"
                                                                  and h["target_id"] == cid] or
                                                [h for h in all_hl.values() if h["target_kind"] == "concept"
                                                 and h["target_id"] == cid], concept_sources.get(cid, [])))
        for tid, items in loose.items():
            if kb.exists("topic", tid):
                topics_touched.add(tid)
                _loose_note(ex, kb, tid, items)
        for tid in topics_touched:
            if kb.exists("topic", tid):
                _topic_note(ex, kb, tid)
        ex.save_manifest()
        for h in hls:
            path = kb.p.learning / "highlights" / f"{h['id']}.md"
            meta, body = store.read_entity(path)
            meta["exported"] = now()
            store.write_entity(path, meta, body)
    return {"dir": str(target), "files": ex.files}


def _common_tags(topics) -> list[str]:
    return ["kinwing"] + [f"topic/{t}" for t in topics or []]


def _source_note(ex: _Exporter, kb: KB, sid: str, hls: list[dict], concepts: list[str]) -> list[str]:
    meta, body = kb.load("source", sid)
    name = ex.names[f"source:{sid}"]
    topics = meta.get("topics") or []
    fm = {
        "kw_id": f"source:{sid}",
        "kw_type": "source-note",
        "title": meta.get("title"),
        "authors": _yaml_list(meta.get("authors") or []),
        "url": meta.get("canonical_url") or meta.get("url") or "",
        "published": meta.get("published") or "",
        "retrieved": (meta.get("retrieved") or "")[:10],
        "source_category": meta.get("category"),
        "topics": [ex.link(f"topic:{t}") or t for t in topics],
        "tags": _common_tags(topics) + ["kinwing/source"],
    }
    who = ", ".join(meta.get("authors") or []) or meta.get("organization") or "unknown author"
    lines = [f"# {meta.get('title')}", "",
             "> [!info] Source",
             f"> {who}" + (f" · published {meta['published']}" if meta.get("published") else ""),
             f"> {fm['url'] or 'local file (kept in the kinwing library)'}",
             f"> Retrieved {fm['retrieved'] or '—'} · kinwing `{sid}`", ""]
    if hls:
        lines += ["## Highlights", ""]
        for h in hls:
            lines.append(_bq(h["quote"]))
            loc = " · ".join(x for x in [h.get("locator"), h.get("section")] if x)
            lines.append(f"> — {loc or 'passage'} ^{h['id']}")
            if h.get("quote_origin") != "source text (exact)":
                lines.append(f"> _({h.get('quote_origin')})_")
            lines.append("")
            if h.get("note"):
                lines += [f"**My note:** {h['note']}", ""]
    summary = parse_sections(body).get("Summary (AI-written)") or meta.get("assessment")
    if summary:
        lines += ["## AI summary", "", "> [!abstract]- Written by an AI research agent (kinwing), not by me",
                  _bq(summary), ""]
    rel = [ex.link(f"concept:{c}") for c in concepts if sid in _sources_of(kb, c)]
    rel = [r for r in rel if r]
    lines += ["## Links", "", "- Topics: " + (", ".join(ex.link(f"topic:{t}") or t for t in topics) or "—")]
    if rel:
        lines.append("- Concepts: " + ", ".join(rel))
    ex.write(f"source:{sid}", "Sources", name, fm, "\n".join(lines))
    return topics


def _sources_of(kb: KB, cid: str) -> set[str]:
    cmeta = kb.load("concept", cid)[0]
    ev = {e["id"]: e for e in kb.metas("evidence")}
    s = set(cmeta.get("sources") or [])
    for cl in kb.metas("claim"):
        if cid in (cl.get("concepts") or []) or cl["id"] in (cmeta.get("claims") or []):
            s.update(ev[e]["source"] for e in cl.get("support") or [] if e in ev)
    return s


def _concept_note(ex: _Exporter, kb: KB, L: Learning, cid: str, hls: list[dict], sids: list[str]) -> list[str]:
    meta, body = kb.load("concept", cid)
    secs = parse_sections(body)
    name = ex.names[f"concept:{cid}"]
    topics = meta.get("topics") or []
    related = []
    for r in meta.get("related") or []:
        related.append((r["id"], r.get("rel", "related")))
    for p in meta.get("prerequisites") or []:
        related.append((p, "builds on"))
    fm = {
        "kw_id": f"concept:{cid}",
        "kw_type": "concept-note",
        "aliases": _yaml_list(meta.get("aliases") or []),
        "topics": [ex.link(f"topic:{t}") or t for t in topics],
        "sources": [ex.link(f"source:{s}") for s in sids if ex.link(f"source:{s}")],
        "related": [ex.link(f"concept:{c}") for c, _ in related if ex.link(f"concept:{c}")],
        "tags": _common_tags(topics) + ["kinwing/concept"],
    }
    lines = [f"# {meta.get('title')}", "", "## My thoughts", ""]
    mine = []
    for h in hls:
        if h.get("note"):
            mine.append(f"- On “{h['quote'][:160]}”: {h['note']}")
    for a in L.answers(concept=cid):
        mine.append(f"- My explanation ({a['created'][:10]}, prompt: _{a['prompt']}_):")
        mine.append(_indent_bq(a["text"]))
    lines += mine or ["_Nothing written yet — this is the place for my own words._"]
    lines += ["", "## AI synthesis", "",
              f"> [!note]- AI-written by kinwing's research agent ({(meta.get('updated') or '')[:10]}) — check the evidence before relying on it",
              _bq(f"**In one line:** {meta.get('summary') or ''}"), ">",
              _bq(_relink(ex, kb, secs.get("Explanation") or "_No explanation yet._")), ""]
    claims = [c for c in kb.metas("claim") if c.get("state") == "current"
              and (cid in (c.get("concepts") or []) or c["id"] in (meta.get("claims") or []))]
    ev = {e["id"]: e for e in kb.metas("evidence")}
    if claims:
        lines += ["## Key evidence", ""]
        for c in claims[:8]:
            lines.append(f"- **Claim ({c.get('strength')} {c.get('kind')}, AI-synthesized):** {c['text']}")
            for e in (c.get("support") or [])[:3]:
                if e in ev and ev[e].get("quote"):
                    src = ex.link(f"source:{ev[e]['source']}") or ev[e]["source"]
                    lines.append(f"    - “{' '.join(ev[e]['quote'].split())}” — {src} {ev[e].get('locator') or ''}".rstrip())
        lines.append("")
    if hls:
        quoted = [h for h in hls if not h.get("note")]
        if quoted:
            lines += ["## Highlighted passages (from the AI synthesis)", ""]
            lines += [_bq(h["quote"]) + f"\n> ^{h['id']}\n" for h in quoted]
    if related:
        lines += ["## Related", ""]
        for c, rel in related:
            title = kb.load("concept", c)[0].get("title") if kb.exists("concept", c) else c
            lines.append(f"- {ex.link(f'concept:{c}', title) or title} — {rel}")
        lines.append("")
    lines += ["## Links", "", "- Topics: " + (", ".join(ex.link(f"topic:{t}") or t for t in topics) or "—")]
    ex.write(f"concept:{cid}", "Concepts", name, fm, "\n".join(lines))
    return topics


def _relink(ex: _Exporter, kb: KB, text: str) -> str:
    """kinwing [[concept-id|label]] links -> links to exported notes, else plain text."""
    def sub(m):
        target, _, label = m.group(1).partition("|")
        cid = target.strip()
        if kb.exists("concept", cid):
            title = kb.load("concept", cid)[0].get("title") or cid
            return ex.link(f"concept:{cid}", label or title) or (label or title)
        return label or target
    return re.sub(r"\[\[([^\]]{1,200})\]\]", sub, text or "")


def _indent_bq(text: str) -> str:
    return "\n".join("    > " + l if l.strip() else "    >" for l in text.strip().splitlines())


def _loose_note(ex: _Exporter, kb: KB, tid: str, hls: list[dict]) -> None:
    t = kb.topic(tid)
    kw_id = f"highlights:{tid}"
    name = ex.name_for(kw_id, "Highlights", f"{t['title']} — highlights")
    fm = {"kw_id": kw_id, "kw_type": "highlights-note", "topics": [ex.link(f"topic:{tid}") or tid],
          "tags": _common_tags([tid]) + ["kinwing/highlights"]}
    lines = [f"# {t['title']} — highlights", "",
             "Passages highlighted in kinwing's AI-written material (not source quotations).", ""]
    for h in hls:
        where = h["target_id"]
        if h["target_kind"] == "concept" and kb.exists("concept", where):
            where = ex.link(f"concept:{where}") or kb.load("concept", where)[0]["title"]
        lines += [_bq(h["quote"]), f"> — {h['target_kind']}: {where} ^{h['id']}", ""]
        if h.get("note"):
            lines += [f"**My note:** {h['note']}", ""]
    ex.write(kw_id, "Highlights", name, fm, "\n".join(lines))


def _topic_note(ex: _Exporter, kb: KB, tid: str) -> None:
    t = kb.topic(tid)
    name = ex.names[f"topic:{tid}"]
    exported = ex.manifest["notes"]
    srcs = sorted(v["name"] for k, v in exported.items() if k.startswith("source:")
                  and tid in (kb.load("source", k[7:])[0].get("topics") or []) if kb.exists("source", k[7:]))
    cons = sorted(v["name"] for k, v in exported.items() if k.startswith("concept:")
                  and kb.exists("concept", k[8:]) and tid in (kb.load("concept", k[8:])[0].get("topics") or []))
    fm = {"kw_id": f"topic:{tid}", "kw_type": "topic-note", "tags": _common_tags([tid]) + ["kinwing/topic"]}
    lines = [f"# {t['title']}", "", "> [!info] Exported from kinwing — a map of the notes taken so far.", ""]
    if cons:
        lines += ["## Concepts", ""] + [f"- [[{n}]]" for n in cons] + [""]
    if srcs:
        lines += ["## Sources", ""] + [f"- [[{n}]]" for n in srcs] + [""]
    if f"highlights:{tid}" in exported:
        lines += ["## Highlights", "", f"- [[{exported[f'highlights:{tid}']['name']}]]", ""]
    ex.write(f"topic:{tid}", "Topics", name, fm, "\n".join(lines))


def dump(res: dict) -> str:
    return json.dumps(res, indent=2)
