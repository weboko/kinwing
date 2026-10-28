"""Consolidation: keep the knowledge base from becoming a pile.

Finds likely duplicate claims and evidence, unflagged conflicts, unsupported findings,
stale claims, orphan evidence and questions whose answers rest on superseded claims.
It writes `topics/<id>/consolidation.md` with the suggested commands. With `apply_safe`
it applies only reversible, information-preserving changes (marking explicit
contradictions as contested, flagging stale claims for verification). Merging and
superseding stay explicit commands, so nothing is deleted or overwritten silently.
"""

from __future__ import annotations

import datetime as dt
import re

from . import store
from .kb import KB
from .store import now, parse_ts

STOP = set("""a an the of to in on for and or is are was were be been being it its this that these those
with by as at from into than then so such can may might will would should could do does did not no
more most less least very also which who whom whose what when where why how all any each both""".split())
NEGATIONS = re.compile(r"\b(not|no|never|fails?|failed|cannot|can't|doesn't|don't|isn't|aren't|without|worse|lower|less)\b", re.I)


def _tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if w not in STOP and len(w) > 2}


def similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def analyze(kb: KB, topic: str, dup_threshold: float = 0.6) -> dict:
    t = kb.topic(topic)
    # Better-supported, older claims first, so a suggested merge keeps the stronger one.
    claims = sorted([c for c in kb.metas("claim", topic) if c.get("state") == "current"],
                    key=lambda c: (-len(c.get("support") or []), c.get("created") or "", c["id"]))
    all_claims = {c["id"]: c for c in kb.metas("claim")}
    evidence = [e for e in kb.metas("evidence", topic)]
    cited = {e for c in kb.metas("claim") for e in (c.get("support") or []) + (c.get("counter") or [])}
    res = {"duplicates": [], "conflicts": [], "unflagged_contradictions": [], "counter_evidence": [],
           "unsupported": [], "stale": [], "orphan_evidence": [], "duplicate_evidence": [], "reopen_questions": []}
    for i, a in enumerate(claims):
        for b in claims[i + 1:]:
            sim = similarity(a["text"], b["text"])
            neg_a, neg_b = bool(NEGATIONS.search(a["text"])), bool(NEGATIONS.search(b["text"]))
            linked = b["id"] in (a.get("contradicts") or []) or a["id"] in (b.get("contradicts") or [])
            if sim >= dup_threshold and neg_a == neg_b and not linked:
                res["duplicates"].append({"a": a, "b": b, "similarity": round(sim, 2)})
            elif sim >= 0.35 and neg_a != neg_b and not linked:
                res["conflicts"].append({"a": a, "b": b, "similarity": round(sim, 2)})
    for c in claims:
        if c.get("strength") == "contested":
            pass
        elif c.get("contradicts"):
            # An explicit conflict between claims: marking both contested is safe to automate.
            res["unflagged_contradictions"].append(c)
        elif c.get("counter"):
            # Counter-evidence may be a caveat rather than a refutation: a judgement call.
            res["counter_evidence"].append(c)
        if c.get("kind") == "finding" and not c.get("support"):
            res["unsupported"].append(c)
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=int(t.get("stale_after_days") or 180))
    for c in claims:
        lv = parse_ts(c.get("last_verified"))
        if lv and lv < cutoff:
            res["stale"].append(c)
    for e in evidence:
        if e["id"] not in cited:
            res["orphan_evidence"].append(e)
    for i, a in enumerate(evidence):
        for b in evidence[i + 1:]:
            if a.get("source") == b.get("source") and a.get("quote") and b.get("quote"):
                qa, qb = " ".join(a["quote"].split()), " ".join(b["quote"].split())
                if qa in qb or qb in qa:
                    res["duplicate_evidence"].append({"a": a, "b": b})
    for q in kb.metas("question", topic):
        if q.get("status") == "answered":
            sup = [all_claims[c] for c in q.get("claims") or [] if c in all_claims]
            if sup and all(c.get("state") != "current" for c in sup):
                res["reopen_questions"].append(q)
    return res


def run(kb: KB, topic: str, apply_safe: bool = False, run_id: str | None = None) -> tuple[dict, str, list[str]]:
    res = analyze(kb, topic)
    applied: list[str] = []
    if apply_safe:
        with store.locked(kb.p):
            for c in res["unflagged_contradictions"]:
                kb.update_claim(c["id"], reason="consolidation: has contradicting claims or counter-evidence",
                                strength="contested", run=run_id)
                applied.append(f"{c['id']} marked contested")
            for c in res["stale"]:
                m, body = kb.load("claim", c["id"])
                if not m.get("needs_verification"):
                    m["needs_verification"] = True
                    kb.save("claim", m, body)
                    kb.log_change(topic, "claim", c["id"], f"claim flagged for re-verification (last verified "
                                  f"{c.get('last_verified')}): {c['text']}", run_id)
                    applied.append(f"{c['id']} flagged for verification")
    report = render(kb, topic, res, applied)
    store.atomic_write(kb.p.topic_dir(topic) / "consolidation.md", report)
    return res, report, applied


def render(kb: KB, topic: str, res: dict, applied: list[str]) -> str:
    out = [f"# Consolidation — {kb.topic(topic)['title']}", "", f"_Generated {now()}. Suggestions, not changes; "
           "run the commands you agree with. Nothing here deletes evidence._", ""]
    if applied:
        out += ["## Applied (safe)", ""] + [f"- {a}" for a in applied] + [""]

    def sec(title, items, fmt):
        out.append(f"## {title} ({len(items)})")
        out.append("")
        out.extend(fmt(x) for x in items) if items else out.append("_None._")
        out.append("")

    sec("Likely duplicate claims", res["duplicates"], lambda d: (
        f"- `{d['a']['id']}` ≈ `{d['b']['id']}` (similarity {d['similarity']}):\n"
        f"  - {d['a']['text']}\n  - {d['b']['text']}\n"
        f"  - if they say the same: `kw claim merge {d['a']['id']} {d['b']['id']} --reason \"…\"`"))
    sec("Possible conflicts not yet linked", res["conflicts"], lambda d: (
        f"- `{d['a']['id']}` vs `{d['b']['id']}` (similar wording, opposite polarity):\n"
        f"  - {d['a']['text']}\n  - {d['b']['text']}\n"
        f"  - if they conflict: `kw claim update {d['b']['id']} --contradicts {d['a']['id']} --reason \"…\"` "
        "and add a question to resolve it (`--origin contradiction`)"))
    sec("Claims in an explicit conflict but not marked contested", res["unflagged_contradictions"],
        lambda c: f"- `{c['id']}` {c['text']} (`kw consolidate {topic} --apply-safe` marks it)")
    sec("Claims with counter-evidence (is the strength still right?)", res["counter_evidence"],
        lambda c: f"- `{c['id']}` [{c.get('strength')}] {c['text']} — counter: {', '.join(c.get('counter') or [])}. "
                  f"If it is a real refutation: `kw claim update {c['id']} --strength contested --reason \"…\"`; "
                  "if it is a caveat, leave it")
    sec("Findings without supporting evidence", res["unsupported"],
        lambda c: f"- `{c['id']}` {c['text']} — add evidence or change its kind to hypothesis")
    sec("Stale claims (re-verify)", res["stale"],
        lambda c: f"- `{c['id']}` last verified {c.get('last_verified')}: {c['text']}")
    sec("Evidence no claim uses", res["orphan_evidence"],
        lambda e: f"- `{e['id']}` from `{e.get('source')}`: “{(e.get('quote') or e.get('note') or '')[:120]}”")
    sec("Overlapping evidence from the same source", res["duplicate_evidence"],
        lambda d: f"- `{d['a']['id']}` and `{d['b']['id']}` quote overlapping text")
    sec("Answered questions resting on superseded claims", res["reopen_questions"],
        lambda q: f"- `{q['id']}` {q['text']} → `kw q update {q['id']} --status open --note \"answer superseded\"`")
    return "\n".join(out)
