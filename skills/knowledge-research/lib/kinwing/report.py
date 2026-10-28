"""create-report integration: dossier → brief.md, and a privacy guard for site/.

kinwing does not render or publish reports. `brief()` turns a topic's records into a draft
of create-report's private `brief.md` (TL;DR L0/L1, findings with {S:src-id} tags,
sections, disagreements, next steps, sources), using the same `src-…` ids, so the agent
can follow the create-report workflow from step 5 onwards. It reads only the kb: never
learning/ (progress, highlights, annotations, answers) and, by default, never sources
the user marked private or provided as their own copies.

`guard()` scans a report's site/ for kinwing's private material before publish.sh.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import store
from .ingest import normalize_for_match
from .kb import KB, parse_sections
from .learning import Learning
from .store import KwError, today

PRIVATE_RIGHTS = ("private", "user-copy")


def _public_source(s: dict) -> bool:
    return s.get("rights") not in PRIVATE_RIGHTS and bool(s.get("canonical_url")) and not s.get("local_path") \
        and s.get("access") != "wanted"


def _plain_links(text: str) -> str:
    """[[concept-id|label]] (reader-only links) -> label or id."""
    return re.sub(r"\[\[([^\]|]+)\|?([^\]]*)\]\]", lambda m: m.group(2) or m.group(1), text)


def _first_sentence(text: str) -> tuple[str, str]:
    text = " ".join(text.split())
    m = re.match(r"(.+?[.!?])(\s|$)(.*)", text)
    return (m.group(1), m.group(3)) if m else (text, "")


def _overview_paragraphs(kb: KB, topic: str) -> list[str]:
    path = kb.p.topic_dir(topic) / "overview.md"
    if not path.exists():
        return []
    paras = []
    for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8")):
        b = block.strip()
        if not b or b.startswith("#") or b.startswith("<!--") or b.startswith("_No research"):
            continue
        paras.append(b)
    return paras


def brief(kb: KB, topic: str, include_private_sources: bool = False) -> tuple[str, dict]:
    t = kb.topic(topic)
    src = {s["id"]: s for s in kb.metas("source")}
    ev = {e["id"]: e for e in kb.metas("evidence")}
    allowed = {sid for sid, s in src.items() if include_private_sources or _public_source(s)}
    excluded = {sid for sid, s in src.items() if topic in (s.get("topics") or []) and sid not in allowed}
    claims = [c for c in kb.metas("claim", topic) if c.get("state") == "current"]
    used: list[str] = []

    def tags(c: dict) -> str:
        out = []
        for e in c.get("support") or []:
            sid = ev.get(e, {}).get("source")
            if sid in allowed:
                out.append(f"{{S:{sid}}}")
                if sid not in used:
                    used.append(sid)
        kind = c.get("kind")
        if kind == "interpretation":
            out.append("{I}")
        elif kind == "hypothesis":
            out.append("{A}")
        return " ".join(dict.fromkeys(out))

    def publishable(c: dict) -> bool:
        sup = [ev.get(e, {}).get("source") for e in c.get("support") or []]
        return not sup or any(s in allowed for s in sup)

    gaps = []
    paras = [_plain_links(" ".join(re.sub(r"(?m)^\s*[-*]\s+", "", p).split())) for p in _overview_paragraphs(kb, topic)]
    l0, rest = _first_sentence(paras[0]) if paras else ("GAP: write the one-sentence answer", "")
    if not rest and len(paras) > 1:
        rest = " ".join(paras[1:3])[:900]
    if not paras:
        gaps.append("the topic has no overview yet (topics/%s/overview.md)" % topic)
    out = [
        f"<!-- create-report brief drafted by kinwing from the {topic} dossier on {today()}. Private, never "
        "published. It contains no personal learning data. Edit freely before rendering. -->",
        f"# {t['title']}",
        f"Subtitle / dek: What the evidence currently says about {t['title'].lower()}: conclusions, disagreements "
        "and open questions.",
        "Kicker: Research dossier",
        f"As of: {today()}",
        "",
        "## TL;DR",
        f"L0: {l0}",
        f"L1: {rest or 'GAP: the 2–4 supporting points'}",
        "",
        "## Findings",
    ]
    order = {"strong": 0, "moderate": 1, "weak": 2, "contested": 3, "unsupported": 4}
    pub_claims = [c for c in claims if publishable(c)]
    dropped = len(claims) - len(pub_claims)
    for i, c in enumerate(sorted([c for c in pub_claims if c.get("strength") in ("strong", "moderate")],
                                 key=lambda c: order.get(c.get("strength"), 9)), 1):
        out.append(f"{i}. **{c['text']}** Strength: {c.get('strength')} ({c.get('kind')}). {tags(c)}"
                   + (f" Uncertainty: {c['uncertainty']}" if c.get("uncertainty") else ""))
    out.append("")
    concepts = sorted(kb.metas("concept", topic), key=lambda c: c.get("title", ""))
    by_persp: dict[str, list] = {}
    for c in concepts:
        by_persp.setdefault(c.get("perspective") or "", []).append(c)
    pnames = {p["id"]: p["name"] for p in t.get("perspectives") or []}
    order = [p["id"] for p in t.get("perspectives") or []]
    placed: set[str] = set()  # each claim once, under the first concept that cites it
    for pid, cs in sorted(by_persp.items(), key=lambda kv: order.index(kv[0]) if kv[0] in order else 99):
        out.append(f"## {pnames.get(pid) or (pid.capitalize() if pid else 'Main concepts')}")
        for c in cs:
            secs = parse_sections(kb.load("concept", c["id"])[1])
            out.append(f"### {c['title']}")
            out.append(f"L0: {c.get('summary') or 'GAP'}")
            if secs.get("Explanation"):
                out.append("L1: " + _plain_links(" ".join(secs["Explanation"].split())))
            if secs.get("Details"):
                out.append("L2: " + _plain_links(" ".join(secs["Details"].split())))
            rel = [cl for cl in pub_claims if c["id"] in (cl.get("concepts") or []) and cl["id"] not in placed]
            for cl in rel:
                placed.add(cl["id"])
                out.append(f"L3: {cl['text']} {tags(cl)}")
        out.append("")
    contested = [c for c in pub_claims if c.get("strength") == "contested" or c.get("contradicts")]
    if contested:
        out.append("## Disagreements")
        seen = set()
        idx = {c["id"]: c for c in pub_claims}
        n = 0
        for c in contested:
            if c["id"] in seen:
                continue
            seen.add(c["id"])
            n += 1
            head = c["text"] if len(c["text"]) <= 80 else c["text"][:80].rsplit(" ", 1)[0] + "…"
            out.append(f"### {chr(64 + min(n, 26))}. {head}")
            side2 = [idx[o] for o in c.get("contradicts") or [] if o in idx]
            seen.update(o["id"] for o in side2)
            out.append(f"Side 1: {c['text']} {tags(c)}" + ("   Side 2: " + " / ".join(f"{o['text']} {tags(o)}" for o in side2)
                                                         if side2 else ""))
            out.append("Conclusion: GAP: state the best-supported reading and why {I}")
        out.append("")
    unc = [c for c in pub_claims if c.get("strength") in ("weak", "unsupported") or c.get("kind") == "hypothesis"]
    # Questions the user raised while reading are personal learning data: never in a brief.
    qs = [q for s, w, q in kb.ranked_questions(topic)
          if q.get("origin") != "learning" and q.get("asked_by") not in ("user", "reader")][:6]
    if unc or qs:
        out.append("## Risks / Next steps")
        for c in unc:
            out.append(f"- Uncertain: {c['text']} {tags(c)}")
        for q in qs:
            out.append(f"- Open question: {q['text']}")
        out.append("")
    out.append("## Sources")
    for sid in used:
        s = src[sid]
        title = s.get("title") + (f" ({s['published'][:10]})" if s.get("published") else "")
        who = ", ".join(s.get("authors") or []) or s.get("organization") or ""
        out.append(f"- {sid}: {who + ' — ' if who else ''}{title}, {s.get('canonical_url')}, accessed {(s.get('retrieved') or today())[:10]}")
    if excluded:
        out.append(f"<!-- {len(excluded)} private or user-provided source(s) left out; claims resting only on them were dropped. -->")
    if gaps:
        out.append("")
        out += [f"GAP: {g}" for g in gaps]
    info = {"claims": len(pub_claims), "dropped_claims": dropped, "sources": len(used), "excluded_sources": len(excluded)}
    return "\n".join(out).rstrip() + "\n", info


def write_brief(kb: KB, path: str, text: str) -> None:
    p = Path(path).expanduser().resolve()
    www = kb.p.www
    if p == www or www in p.parents:
        raise KwError(f"refusing to write a private brief into the public web root {www}")
    if p.name != "brief.md" and p.suffix != ".md":
        raise KwError("the brief should be a .md file (create-report expects ~/reports/<slug>/brief.md)", 2)
    store.atomic_write(p, text)


def _needles(kb: KB) -> list[tuple[str, str]]:
    """(label, normalized text) pairs that must never appear in a public site."""
    L = Learning(kb)
    out: list[tuple[str, str]] = []
    for h in L.highlights():
        if len(h.get("note") or "") >= 20:
            out.append((f"annotation {h['id']}", h["note"]))
    for a in L.answers():
        if len(a.get("text") or "") >= 20:
            out.append((f"your answer {a['id']}", a["text"]))
    for q in L.my_questions():
        if len(q.get("text") or "") >= 20:
            out.append((f"your question {q['id']}", q["text"]))
        ctx = q.get("context") or ""
        m = re.search(r"“(.{20,})”", ctx)
        if m:
            out.append((f"passage you asked about in {q['id']}", m.group(1)))
    for t in kb.topics():
        for f in ("familiarity", "objective"):
            if len(t.get(f) or "") >= 25:
                out.append((f"topic {t['id']} {f} (your private context)", t[f]))
    for s in kb.metas("source"):
        if s.get("rights") in PRIVATE_RIGHTS or s.get("local_path"):
            if len(s.get("title") or "") >= 12:
                out.append((f"private source title {s['id']}", s["title"]))
            if s.get("local_path"):
                out.append((f"local path of {s['id']}", s["local_path"]))
    out.append(("the knowledge base path", str(kb.p.kb)))
    out.append(("the library path", str(kb.p.library)))
    return [(label, normalize_for_match(text).lower()) for label, text in out if text]


def guard(kb: KB, site_dir: str) -> list[str]:
    root = Path(site_dir).expanduser().resolve()
    if not root.is_dir():
        raise KwError(f"no directory {root}", 2)
    needles = _needles(kb)
    probs = []
    for f in sorted(root.rglob("*")):
        if not f.is_file() or f.suffix.lower() not in (".html", ".htm", ".json", ".js", ".md", ".txt", ".css", ".svg", ".xml"):
            continue
        rel = f.relative_to(root)
        if re.search(r"(^|/)(state\.json|events\.jsonl)$|learning/|highlights/|answers/", str(rel)):
            probs.append(f"{rel}: a kinwing learning-state file")
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        hay = normalize_for_match(re.sub(r"<[^>]+>", " ", text)).lower()
        raw = text
        for label, needle in needles:
            n = needle if len(needle) <= 160 else needle[:160]
            if n and (n in hay or n in raw.lower()):
                probs.append(f"{rel}: contains {label}")
    return probs
