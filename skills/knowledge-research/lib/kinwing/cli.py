"""kw — the kinwing command line. Agents (Claude Code, Codex) drive the system through it.

Every command is non-interactive, prints short human-readable output (or JSON with
--json), and exits non-zero with a one-line reason when it refuses. Run `kw <cmd> -h`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__, store
from .kb import KB
from .store import KwError


def _kb(args) -> KB:
    p = store.Paths(args.home)
    p.check_private_location()
    if not (p.kb / "topics").exists() and args.cmd != "init":
        store.ensure_layout(p)
    return KB(p)


def _out(args, obj, human: str | None = None) -> None:
    if getattr(args, "json", False):
        print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))
    elif human is not None:
        print(human)


def _run_id(args, kb: KB, topic: str | None) -> str | None:
    from . import runs

    rid = getattr(args, "run", None) or os.environ.get("KW_RUN") or None
    if rid:
        return rid
    return runs.current_run(kb, topic) if topic else None


def _text_arg(value: str | None, file: str | None) -> str:
    if file:
        if file == "-":
            return sys.stdin.read()
        with open(os.path.expanduser(file), encoding="utf-8") as f:
            return f.read()
    return value or ""


def _status(meta: dict, noun: str) -> str:
    if meta.get("_duplicate"):
        return f"known {meta['id']} (duplicate {noun}, not added again)"
    return f"added {meta['id']}"


# =========================================================================== commands


def cmd_init(args):
    p = store.Paths(args.home)
    store.ensure_layout(p)
    from . import dossier

    dossier.build_index(KB(p))
    print(f"knowledge home ready: {p.home}\n  kb (git): {p.kb}\n  library:  {p.library}\n"
          f"  learning: {p.learning}\n  exports:  {p.exports}")


def cmd_status(args):
    from . import notify, runs

    kb = _kb(args)
    rows = []
    for t in kb.topics():
        tid = t["id"]
        rows.append({
            "id": tid, "title": t["title"], "status": t.get("status"), "depth": t.get("depth"),
            "open_questions": sum(1 for q in kb.metas("question", tid) if q.get("status") == "open"),
            "claims": sum(1 for c in kb.metas("claim", tid) if c.get("state") == "current"),
            "concepts": len(kb.metas("concept", tid)), "sources": len(kb.metas("source", tid)),
            "last_investigated": t.get("last_investigated"), "schedule": t.get("schedule"),
            "active_run": runs.current_run(kb, tid),
        })
    notes = notify.items(kb.p)
    if args.json:
        return _out(args, {"home": str(kb.p.home), "topics": rows, "notifications": notes})
    print(f"knowledge home: {kb.p.home}")
    if not rows:
        print("no topics yet — create one with: kw topic new --title …")
    for r in rows:
        sched = r["schedule"] or {}
        s = f"  {r['id']:<28} {r['status']:<8} {r['depth']:<11} {r['concepts']:>3} concepts {r['claims']:>3} claims " \
            f"{r['open_questions']:>3} open q  last: {(r['last_investigated'] or 'never')[:16]}"
        if sched.get("enabled"):
            s += f"  ⏱ {sched.get('cron')}"
        if r["active_run"]:
            s += f"  ▶ {r['active_run']}"
        print(s)
    if notes:
        print(f"\n{len(notes)} unread notification(s): kw notify list")


# --------------------------------------------------------------------------- topic


def cmd_topic_new(args):
    kb = _kb(args)
    persp = []
    for raw in args.perspective or []:
        pid, _, rest = raw.partition(":")
        name, _, why = rest.partition(":")
        persp.append({"id": store.slugify(pid, 24), "name": name or pid, "why": why})
    budget = {"max_questions_per_run": args.max_questions, "max_sources_per_run": args.max_sources,
              "max_minutes": args.max_minutes, "max_runs_per_week": args.runs_per_week}
    t = kb.create_topic(
        args.title, tid=args.id, description=args.description, objective=args.objective,
        familiarity=args.familiarity, known_concepts=args.known, depth=args.depth,
        include=args.include, exclude=args.exclude, preferred_sources=args.sources,
        perspectives=persp, research_priorities=args.research_priorities,
        learning_priorities=args.learning_priorities, frequency=args.frequency, budget=budget,
    )
    _out(args, t, f"created topic {t['id']}: {t['title']} (depth {t['depth']})\n"
                  f"  config: {kb.p.topic_dir(t['id']) / 'topic.yaml'}")


def cmd_topic_list(args):
    kb = _kb(args)
    ts = kb.topics()
    _out(args, ts, "\n".join(f"{t['id']:<28} {t.get('status'):<8} {t.get('depth'):<11} {t['title']}" for t in ts)
         or "no topics")


def cmd_topic_show(args):
    kb = _kb(args)
    t = kb.topic(args.topic)
    if args.json:
        return _out(args, t)
    from . import yamlio

    print(yamlio.dump(t), end="")


def cmd_topic_set(args):
    kb = _kb(args)
    changes = {}
    for kv in args.pairs:
        k, sep, v = kv.partition("=")
        if not sep:
            raise KwError(f"expected key=value, got '{kv}'", 2)
        changes[k.strip()] = v.strip()
    t = kb.set_topic_fields(args.topic, changes, note=args.note)
    _out(args, t, f"updated {args.topic}: {', '.join(changes)}")


def cmd_topic_pause(args, status="paused"):
    from . import schedule

    kb = _kb(args)
    t = kb.set_topic_fields(args.topic, {"status": status}, note=f"topic {status}" + (f": {args.note}" if args.note else ""))
    msg = f"{args.topic} is now {status}"
    sched = t.get("schedule") or {}
    if sched.get("ao_slug"):
        msg += "\n" + schedule.set_enabled(kb, args.topic, status == "active")
    print(msg)


def cmd_topic_resume(args):
    cmd_topic_pause(args, status="active")


def cmd_topic_perspective(args):
    kb = _kb(args)
    t = kb.add_perspective(args.topic, store.slugify(args.id, 24), args.name, args.why or "")
    _out(args, t["perspectives"], f"perspective {args.id} added to {args.topic}")


# --------------------------------------------------------------------------- questions


def cmd_q_add(args):
    kb = _kb(args)
    rid = _run_id(args, kb, args.topic)
    m = kb.add_question(args.topic, args.text, origin=args.origin, priority=args.priority, value=args.value,
                        cost=args.cost, perspective=args.perspective, depends_on=args.depends,
                        concepts=args.concept, claims=args.claim, run=rid, asked_by=args.asked_by,
                        context=args.context)
    _out(args, m, f"{_status(m, 'question')}  [{m['status']}] {m['text']}")


def cmd_q_list(args):
    kb = _kb(args)
    statuses = store.split_list(args.status) or None
    rows = []
    if args.topic:
        ranked = {q["id"]: (s, w) for s, w, q in kb.ranked_questions(args.topic, tuple(statuses or ["open", "in_progress", "partial", "blocked", "answered", "dropped"]))}
    else:
        ranked = {}
    for q in kb.metas("question", args.topic):
        if statuses and q.get("status") not in statuses:
            continue
        s = ranked.get(q["id"], (None, ""))
        rows.append({**q, "score": s[0], "score_why": s[1]})
    rows.sort(key=lambda q: (q.get("status") != "in_progress", q.get("status") != "open", -(q["score"] or 0)))
    _out(args, rows, "\n".join(
        f"{q['id']}  {q['status']:<11} {('%5.1f' % q['score']) if q['score'] is not None else '     '}  "
        f"{q['topic']}: {q['text']}" for q in rows) or "no questions")


def cmd_q_show(args):
    kb = _kb(args)
    meta, body = kb.load("question", args.id)
    if args.json:
        return _out(args, {**meta, "body": body})
    from . import yamlio

    print(yamlio.dump(meta) + "\n" + body)


def cmd_q_update(args):
    kb = _kb(args)
    meta = kb.load("question", args.id)[0]
    rid = _run_id(args, kb, meta["topic"])
    result = _text_arg(args.result, args.result_file) if (args.result or args.result_file) else None
    m = kb.update_question(args.id, status=args.status, result=result, note=args.note, run=rid,
                           priority=args.priority, value=args.value, cost=args.cost, concepts=args.concept,
                           claims=args.claim, depends_on=args.depends, perspective=args.perspective)
    _out(args, m, f"updated {m['id']} [{m['status']}]")


def cmd_q_next(args):
    kb = _kb(args)
    rows = [(s, w, q) for s, w, q in kb.ranked_questions(args.topic) if s >= 0][: args.limit]
    _out(args, [{**q, "score": s, "score_why": w} for s, w, q in rows],
         "\n".join(f"{q['id']}  {s:5.1f}  {q['text']}\n           ({w})" for s, w, q in rows) or "no open questions")


# --------------------------------------------------------------------------- sources


def cmd_source_add(args):
    from . import ingest, runs

    kb = _kb(args)
    rid = _run_id(args, kb, args.topic)
    m = ingest.add_source(
        kb, args.topic, url=args.url, file=args.file, content_file=args.content_file,
        metadata_only=args.metadata_only, title=args.title, authors=args.author, organization=args.org,
        category=args.category, rights=args.rights, published=args.published,
        summary=_text_arg(args.summary, args.summary_file), assessment=args.assessment,
        question=args.question, run=rid, why=args.why, isbn=args.isbn,
    )
    status = m.pop("_status")
    label = {"added": "added", "known-url": "known (same URL)", "known-content": "known (identical content)"}[status]
    msg = f"{label} {m['id']}  [{m.get('category')}, extraction {m.get('extraction')}, {m.get('chars', 0)} chars] {m.get('title')}"
    note = runs.deadline_note(kb, rid)
    _out(args, {**m, "status": status}, msg + (f"\n{note}" if note else ""))


def cmd_source_list(args):
    kb = _kb(args)
    rows = [s for s in kb.metas("source", args.topic) if not args.wanted or s.get("access") == "wanted"]
    _out(args, rows, "\n".join(f"{s['id']:<40} {s.get('category', ''):<10} {s.get('extraction', ''):<13} {s.get('title')}"
                               for s in rows) or "no sources")


def cmd_source_show(args):
    from . import ingest, yamlio

    kb = _kb(args)
    meta, body = kb.load("source", args.id)
    if args.content:
        print(ingest.show_content(kb, args.id, args.from_para, args.to_para))
        return
    if args.json:
        return _out(args, {**meta, "body": body})
    print(yamlio.dump(meta) + ("\n" + body if body else ""))
    ev = [e for e in kb.metas("evidence") if e.get("source") == args.id]
    if ev:
        print(f"evidence from this source: {', '.join(e['id'] for e in ev)}")


def cmd_source_refetch(args):
    from . import ingest

    kb = _kb(args)
    ids = [s["id"] for s in kb.metas("source") if s.get("canonical_url")] if args.all else [args.id]
    for sid in ids:
        try:
            m = ingest.refetch(kb, sid)
            print(f"{sid}: {'changed' if m['_changed'] else 'unchanged'} ({m['chars']} chars)")
        except KwError as e:
            print(f"{sid}: {e}")


# --------------------------------------------------------------------------- evidence & claims


def cmd_evidence_add(args):
    kb = _kb(args)
    rid = _run_id(args, kb, args.topic)
    m = kb.add_evidence(args.source, args.quote, args.topic, locator=args.locator, note=args.note,
                        kind=args.kind, questions=args.question, concepts=args.concept, run=rid,
                        allow_unverified=args.allow_unverified)
    v = {True: "quote verified", False: "QUOTE UNVERIFIED", None: "no quote"}[m.get("quote_verified")]
    _out(args, m, f"{_status(m, 'evidence')}  ({v}{', ' + m['locator'] if m.get('locator') else ''})")


def cmd_evidence_list(args):
    kb = _kb(args)
    rows = [e for e in kb.metas("evidence", args.topic) if not args.source or e.get("source") == args.source]
    _out(args, rows, "\n".join(f"{e['id']}  {e.get('source')}  {e.get('locator', ''):<6} “{(e.get('quote') or e.get('note') or '')[:90]}”"
                               for e in rows) or "no evidence")


def cmd_claim_add(args):
    kb = _kb(args)
    rid = _run_id(args, kb, args.topic)
    m = kb.add_claim(args.topic, args.text, support=args.support, counter=args.counter, kind=args.kind,
                     strength=args.strength, uncertainty=args.uncertainty or "", concepts=args.concept,
                     contradicts=args.contradicts, questions=args.question, run=rid,
                     reasoning=_text_arg(args.reasoning, None))
    _out(args, m, f"{_status(m, 'claim')}  [{m['strength']} {m['kind']}] {m['text']}")


def _claim_topic(kb, cid):
    return (kb.load("claim", cid)[0].get("topics") or [None])[0]


def cmd_claim_update(args):
    kb = _kb(args)
    rid = _run_id(args, kb, _claim_topic(kb, args.id))
    m = kb.update_claim(args.id, reason=args.reason, run=rid, strength=args.strength, kind=args.kind,
                        add_support=args.add_support, add_counter=args.add_counter, uncertainty=args.uncertainty,
                        text=args.text, verified=args.verified, concepts=args.concept, contradicts=args.contradicts)
    _out(args, m, f"updated {m['id']}  [{m['strength']} {m['kind']}] {m['text']}")


def cmd_claim_supersede(args):
    kb = _kb(args)
    rid = _run_id(args, kb, _claim_topic(kb, args.old))
    kb.supersede_claim(args.old, args.by, args.reason, run=rid)
    print(f"{args.old} superseded by {args.by} (kept, with the reason, in its revision history)")


def cmd_claim_merge(args):
    kb = _kb(args)
    rid = _run_id(args, kb, _claim_topic(kb, args.keep))
    kb.merge_claims(args.keep, args.dup, args.reason, run=rid)
    print(f"{args.dup} merged into {args.keep}")


def cmd_claim_list(args):
    kb = _kb(args)
    rows = [c for c in kb.metas("claim", args.topic) if args.all or c.get("state") == "current"]
    _out(args, rows, "\n".join(f"{c['id']}  {c.get('state'):<10} {c.get('strength'):<11} {c.get('kind'):<14} {c['text']}"
                               for c in rows) or "no claims")


def cmd_show(args):
    """Show any record by id."""
    from . import yamlio

    kb = _kb(args)
    kind = store.kind_of(args.id) or ("concept" if kb.exists("concept", args.id) else None)
    if not kind:
        raise KwError(f"can't tell what '{args.id}' is", 2)
    meta, body = kb.load(kind, args.id)
    if args.json:
        return _out(args, {**meta, "body": body})
    print(yamlio.dump(meta) + ("\n" + body if body.strip() else ""))


# --------------------------------------------------------------------------- concepts & overview


def cmd_concept_add(args):
    kb = _kb(args)
    rid = _run_id(args, kb, args.topic)
    m = kb.add_concept(args.topic, args.title, cid=args.id, summary=args.summary or "",
                       explanation=_text_arg(args.explanation, args.explanation_file),
                       details=_text_arg(args.details, args.details_file), prompts=args.prompt,
                       prerequisites=args.prereq, related=args.related, claims=args.claim, sources=args.source,
                       perspective=args.perspective or "", aliases=args.alias, run=rid)
    _out(args, m, f"{_status(m, 'concept')}  {m['title']}")


def cmd_concept_update(args):
    kb = _kb(args)
    meta = kb.load("concept", args.id)[0]
    rid = _run_id(args, kb, (meta.get("topics") or [None])[0])
    m = kb.update_concept(args.id, run=rid, reason=args.reason or "", title=args.title, summary=args.summary,
                          explanation=_text_arg(args.explanation, args.explanation_file) or None,
                          details=_text_arg(args.details, args.details_file) or None,
                          alternative=_text_arg(args.alternative, args.alternative_file) or None,
                          prompts=args.prompt, prerequisites=args.prereq, related=args.related, claims=args.claim,
                          sources=args.source, aliases=args.alias, perspective=args.perspective, topic=args.topic)
    _out(args, m, f"updated {m['id']}")


def cmd_concept_list(args):
    kb = _kb(args)
    rows = kb.metas("concept", args.topic)
    _out(args, rows, "\n".join(f"{c['id']:<32} {c['title']} — {c.get('summary', '')[:80]}" for c in rows) or "no concepts")


def cmd_overview(args):
    kb = _kb(args)
    path = kb.p.topic_dir(args.topic) / "overview.md"
    kb.topic(args.topic)
    if args.file or args.text:
        text = _text_arg(args.text, args.file)
        with store.locked(kb.p):
            store.atomic_write(path, text.rstrip() + "\n")
            kb.log_change(args.topic, "overview", args.topic, "overview rewritten", _run_id(args, kb, args.topic),
                          detail=args.reason)
        print(f"overview written: {path}")
    else:
        print(path.read_text(encoding="utf-8"))


def cmd_dossier(args):
    from . import dossier

    kb = _kb(args)
    text = dossier.build(kb, args.topic)
    if args.print:
        print(text)
    else:
        print(f"dossier: {kb.p.topic_dir(args.topic) / 'dossier.md'}")


def cmd_consolidate(args):
    from . import consolidate

    kb = _kb(args)
    res, report, applied = consolidate.run(kb, args.topic, apply_safe=args.apply_safe,
                                           run_id=_run_id(args, kb, args.topic))
    if args.json:
        return _out(args, {k: [x.get("id") if isinstance(x, dict) and "id" in x else
                               {kk: vv.get("id") if isinstance(vv, dict) else vv for kk, vv in x.items()}
                               for x in v] for k, v in res.items()} | {"applied": applied})
    print(report)


def cmd_check(args):
    kb = _kb(args)
    probs = kb.check()
    errors = [m for lvl, m in probs if lvl == "error"]
    for lvl, m in probs:
        print(f"{lvl}: {m}")
    print(f"check: {len(errors)} error(s), {len(probs) - len(errors)} warning(s)")
    sys.exit(1 if errors else 0)


def cmd_commit(args):
    import subprocess

    kb = _kb(args)
    if not (kb.p.kb / ".git").exists():
        raise KwError("kb is not a git repository (kw init creates one)")
    subprocess.run(["git", "-C", str(kb.p.kb), "add", "-A"], check=True)
    r = subprocess.run(["git", "-C", str(kb.p.kb), "diff", "--cached", "--quiet"])
    if r.returncode == 0:
        print("nothing to commit")
        return
    subprocess.run(["git", "-C", str(kb.p.kb), "commit", "-q", "-m", args.message], check=True)
    print("committed: " + args.message)


# --------------------------------------------------------------------------- runs


def cmd_run_begin(args):
    from . import runs

    kb = _kb(args)
    meta, brief = runs.begin(kb, args.topic, agent=args.agent or "", ao_run_dir=args.ao_run_dir or "",
                             questions=args.questions, force=args.force, mode=args.mode)
    if args.json:
        return _out(args, {**meta, "brief": brief})
    print(brief)
    print(f"export KW_RUN={meta['id']}   # optional: later commands pick the active run up automatically")


def cmd_run_end(args):
    from . import runs

    kb = _kb(args)
    rid = args.run or os.environ.get("KW_RUN") or (runs.current_run(kb, args.topic) if args.topic else None)
    if not rid:
        act = runs.active_runs(kb, args.topic)
        raise KwError("which run? pass --run" + (f" (active: {', '.join(r['id'] for r in act)})" if act else " (none active)"), 2)
    cont = {"yes": True, "no": False, None: None}[args.continue_]
    m = runs.end(kb, rid, _text_arg(args.summary, args.summary_file), args.stop_reason, continue_=cont,
                 next_steps=args.next, notify_msg=args.notify, severity=args.severity)
    s = m["stats"]
    _out(args, m, f"run {rid} completed: {s['sources_added']} sources, {s['evidence_added']} evidence, "
                  f"{s['claims_added']} new / {s['claims_revised']} revised claims, {s['questions_answered']} answered, "
                  f"{s['questions_added']} new questions; {m['questions_remaining']} open questions remain."
                  + ("\nlow yield: nothing new was recorded" if m.get("low_yield") else ""))


def cmd_run_list(args):
    from . import runs

    kb = _kb(args)
    runs.sync_usage(kb)
    rows = sorted([r for r in kb.metas("run") if not args.topic or r.get("topic") == args.topic],
                  key=lambda r: r.get("started") or "", reverse=True)
    def fmt(r):
        s = r.get("stats") or {}
        u = r.get("usage") or {}
        cost = f" ${u['total_cost_usd']:.2f}" if isinstance(u.get("total_cost_usd"), (int, float)) else ""
        return (f"{r['id']}  {r.get('status'):<11} {r.get('topic'):<24} {(r.get('started') or '')[:16]}  "
                f"+{s.get('sources_added', 0)}src +{s.get('evidence_added', 0)}ev +{s.get('claims_added', 0)}cl"
                f"{cost}  {r.get('stop_reason') or ''}")
    _out(args, rows, "\n".join(fmt(r) for r in rows) or "no runs")


def cmd_run_recover(args):
    from . import runs

    kb = _kb(args)
    ids = [args.id] if args.id else [r["id"] for r in runs.active_runs(kb, args.topic)]
    for rid in ids:
        m = runs.recover(kb, rid, "interrupted")
        print(f"{rid}: {m['status']}; released {', '.join(m.get('released_questions') or []) or 'no questions'}")
    if not ids:
        print("no active runs")


# --------------------------------------------------------------------------- notifications


def cmd_notify_list(args):
    from . import notify

    kb = _kb(args)
    rows = notify.items(kb.p, include_acked=args.all)
    _out(args, rows, "\n".join(f"{n['id']}  {n['at'][:16]}  [{n['severity']}] {n.get('topic') or '-'}: {n['message']}"
                               for n in rows) or "no notifications")


def cmd_notify_add(args):
    from . import notify

    kb = _kb(args)
    n = notify.add(kb.p, args.message, topic=args.topic or "", severity=args.severity, run=args.run or "")
    _out(args, n, f"queued {n['id']}")


def cmd_notify_ack(args):
    from . import notify

    kb = _kb(args)
    print(f"acknowledged {notify.ack(kb.p, args.ids or None)}")


# --------------------------------------------------------------------------- learning


def cmd_learn(args):
    from . import learning

    kb = _kb(args)
    L = learning.Learning(kb)
    if args.learn_cmd == "next":
        recs = L.recommend(topic=args.topic, limit=args.limit)
        return _out(args, recs, "\n".join(
            f"{r['concept']:<32} {r['score']:4.1f}  {r['title']}\n    why: {'; '.join(r['reasons'])}" for r in recs)
            or "nothing to suggest (no concepts yet, or everything is marked known)")
    if args.learn_cmd == "status":
        st = L.overview(topic=args.topic)
        return _out(args, st, "\n".join(
            f"{c['concept']:<32} {c['inferred']['status']:<18} {c['inferred']['basis']}" for c in st["concepts"])
            or "no concepts")
    if args.learn_cmd == "mark":
        L.self_report(args.concept, args.value, note=args.note)
        return print(f"{args.concept}: self-reported '{args.value}'" +
                     (" — it won't be suggested in learning sessions" if args.value == "known" else ""))
    if args.learn_cmd == "interest":
        L.set_interest(args.concept, args.value)
        return print(f"{args.concept}: interest {args.value}")
    if args.learn_cmd == "answers":
        rows = L.answers(pending=args.pending)
        return _out(args, rows, "\n".join(
            f"{a['id']}  {a['concept']:<28} {a.get('review', {}).get('assessment') or 'unreviewed':<12} {a['prompt'][:60]}\n    “{a['text'][:200]}”"
            for a in rows) or "no answers")
    if args.learn_cmd == "review":
        a = L.review_answer(args.id, args.assessment, args.note or "")
        return print(f"{a['id']}: reviewed as {args.assessment}")
    if args.learn_cmd == "session":
        s = L.create_session(minutes=args.minutes, topic=args.topic)
        return _out(args, s, f"session {s['id']} ({s['minutes']} min):\n" + "\n".join(
            f"  {i + 1}. {it['title']} — {it['depth']} (~{it['minutes']} min): {it['reason']}" for i, it in enumerate(s["items"])))
    if args.learn_cmd == "questions":
        rows = L.my_questions()
        return _out(args, rows, "\n".join(f"{q['id']}  {q['status']:<11} {q['text']}" + (f"\n    → {q['result']}" if q.get('result') else "")
                                          for q in rows) or "no questions from reading yet")


def cmd_highlight(args):
    from . import learning

    kb = _kb(args)
    L = learning.Learning(kb)
    if args.hl_cmd == "add":
        kind, _, tid = args.target.partition(":")
        h = L.add_highlight(kind, tid, args.quote, note=args.note or "", tags=args.tag)
        return _out(args, h, f"highlight {h['id']} on {args.target}")
    if args.hl_cmd == "list":
        rows = L.highlights(topic=args.topic)
        return _out(args, rows, "\n".join(f"{h['id']}  {h['target_kind']}:{h['target_id']:<30} “{h['quote'][:70]}”" +
                                          (f"\n    note: {h['note'][:100]}" if h.get("note") else "") for h in rows) or "no highlights")


def cmd_export(args):
    from . import export

    kb = _kb(args)
    res = export.obsidian(kb, highlights=store.split_list(args.highlights), concepts=store.split_list(args.concepts),
                          topic=args.topic, out=args.out, force=args.force)
    _out(args, res, "\n".join([f"exported to {res['dir']}:"] + [f"  {x['action']:<9} {x['path']}" for x in res["files"]]))


def cmd_report(args):
    from . import report

    kb = _kb(args)
    if args.report_cmd == "brief":
        text, info = report.brief(kb, args.topic, include_private_sources=args.include_private_sources)
        if args.out:
            report.write_brief(kb, args.out, text)
            print(f"brief written: {args.out}  ({info['claims']} claims, {info['sources']} sources; "
                  f"{info['excluded_sources']} private source(s) left out)")
        else:
            print(text)
    elif args.report_cmd == "guard":
        probs = report.guard(kb, args.dir)
        for p in probs:
            print("leak: " + p)
        print(f"guard: {len(probs)} problem(s) in {args.dir}")
        sys.exit(1 if probs else 0)


def cmd_schedule(args):
    from . import schedule

    kb = _kb(args)
    c = args.sched_cmd
    if c == "add":
        print(schedule.add(kb, args.topic, cron=args.cron, agent=args.agent, max_duration=args.max_duration))
    elif c == "run-now":
        print(schedule.run_now(kb, args.topic, agent=args.agent, max_duration=args.max_duration))
    elif c == "pause":
        print(schedule.set_enabled(kb, args.topic, False))
    elif c == "resume":
        print(schedule.set_enabled(kb, args.topic, True))
    elif c == "remove":
        print(schedule.remove(kb, args.topic))
    elif c == "list":
        print(schedule.listing(kb))
    elif c == "spec":
        print(schedule.render_spec(kb, args.topic, cron=args.cron or "", agent=args.agent, max_duration=args.max_duration))


def cmd_serve(args):
    from . import reader

    p = store.Paths(args.home)
    store.ensure_layout(p)
    reader.serve(KB(p), host=args.host, port=args.port)


# =========================================================================== parser


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="kw", description="kinwing: a personal research and learning knowledge base")
    ap.add_argument("--home", help="knowledge home (default $KW_HOME or ~/knowledge)")
    ap.add_argument("--version", action="version", version=f"kw {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, func, help_, parent=sub, **kw):
        sp = parent.add_parser(name, help=help_, description=help_, **kw)
        sp.set_defaults(func=func)
        sp.add_argument("--json", action="store_true", help="machine-readable output")
        return sp

    add("init", cmd_init, "create the knowledge home (kb git repo, library, learning, runtime)")
    add("status", cmd_status, "topics, schedules, active runs, unread notifications")
    s = add("show", cmd_show, "show any record by id (q-…, ev-…, cl-…, src-…, run-…, concept id)")
    s.add_argument("id")

    # topic
    tp = sub.add_parser("topic", help="create and configure research topics").add_subparsers(dest="topic_cmd", required=True)
    s = add("new", cmd_topic_new, "create a topic", tp)
    s.add_argument("--title", required=True)
    s.add_argument("--id", help="stable id (default: from the title)")
    s.add_argument("--description")
    s.add_argument("--objective", help="what the user wants to be able to understand or do")
    s.add_argument("--familiarity", help="what the user already knows, in their words")
    s.add_argument("--known", help="comma-separated concepts the user already knows")
    s.add_argument("--depth", choices=["orientation", "deep", "monitor", "targeted"], default="orientation")
    s.add_argument("--include", help="comma-separated: in scope")
    s.add_argument("--exclude", help="comma-separated: out of scope")
    s.add_argument("--sources", help="comma-separated preferred source kinds (papers, docs, code, books, discussions…)")
    s.add_argument("--perspective", action="append", help="id:Name:why (repeatable)")
    s.add_argument("--research-priorities")
    s.add_argument("--learning-priorities")
    s.add_argument("--frequency", help="e.g. manual, weekly, 'Mon/Wed/Fri'", default="manual")
    s.add_argument("--max-questions", type=int, help="questions per run (default 3)")
    s.add_argument("--max-sources", type=int, help="new sources per run (default 8)")
    s.add_argument("--max-minutes", type=int, help="minutes per run (default 40)")
    s.add_argument("--runs-per-week", type=int, help="runs per 7 days (default 3)")
    add("list", cmd_topic_list, "list topics", tp)
    s = add("show", cmd_topic_show, "show a topic's configuration", tp)
    s.add_argument("topic")
    s = add("set", cmd_topic_set, "change settings: kw topic set T depth=deep budget.max_minutes=30", tp)
    s.add_argument("topic")
    s.add_argument("pairs", nargs="+")
    s.add_argument("--note")
    for name, fn, h in (("pause", cmd_topic_pause, "pause research (and its schedule)"),
                        ("resume", cmd_topic_resume, "resume research (and its schedule)")):
        s = add(name, fn, h, tp)
        s.add_argument("topic")
        s.add_argument("--note")
    pp = tp.add_parser("perspective", help="perspectives that drive questions").add_subparsers(dest="p_cmd", required=True)
    s = add("add", cmd_topic_perspective, "add a perspective", pp)
    s.add_argument("topic")
    s.add_argument("id")
    s.add_argument("name")
    s.add_argument("--why")

    # questions
    qp = sub.add_parser("q", help="the research question queue").add_subparsers(dest="q_cmd", required=True)
    s = add("add", cmd_q_add, "add a research question", qp)
    s.add_argument("text")
    s.add_argument("--topic", required=True)
    s.add_argument("--origin", default="plan", choices=["user", "plan", "gap", "contradiction", "learning", "development", "related"])
    s.add_argument("--priority", default="medium", choices=["high", "medium", "low"])
    s.add_argument("--value", default="medium", choices=["high", "medium", "low"], help="expected research value")
    s.add_argument("--cost", default="medium", choices=["high", "medium", "low"], help="estimated effort")
    s.add_argument("--perspective")
    s.add_argument("--depends", help="comma-separated question ids")
    s.add_argument("--concept")
    s.add_argument("--claim")
    s.add_argument("--context", help="relevant existing knowledge or why it matters")
    s.add_argument("--asked-by", default="agent", choices=["agent", "user", "reader"])
    s.add_argument("--run")
    s = add("list", cmd_q_list, "list questions", qp)
    s.add_argument("--topic")
    s.add_argument("--status", help="comma-separated statuses")
    s = add("show", cmd_q_show, "show a question", qp)
    s.add_argument("id")
    s = add("update", cmd_q_update, "update status/result/priority", qp)
    s.add_argument("id")
    s.add_argument("--status", choices=["open", "in_progress", "answered", "partial", "blocked", "dropped"])
    s.add_argument("--result")
    s.add_argument("--result-file")
    s.add_argument("--note")
    for k in ("priority", "value", "cost"):
        s.add_argument(f"--{k}", choices=["high", "medium", "low"])
    s.add_argument("--concept")
    s.add_argument("--claim")
    s.add_argument("--depends")
    s.add_argument("--perspective")
    s.add_argument("--run")
    s = add("next", cmd_q_next, "the highest-value open questions, with the reason", qp)
    s.add_argument("--topic", required=True)
    s.add_argument("--limit", type=int, default=5)

    # sources
    sp_ = sub.add_parser("source", help="ingest and inspect sources").add_subparsers(dest="s_cmd", required=True)
    s = add("add", cmd_source_add, "add a source: URL, local file, agent-fetched content, or a book to acquire", sp_)
    s.add_argument("url", nargs="?")
    s.add_argument("--topic", required=True)
    s.add_argument("--file", help="local PDF/EPUB/Markdown/HTML/text file (copied into the library)")
    s.add_argument("--content-file", help="text you fetched yourself for URL (use - for stdin)")
    s.add_argument("--metadata-only", action="store_true", help="record without content (e.g. a book to acquire)")
    s.add_argument("--title")
    s.add_argument("--author", action="append")
    s.add_argument("--org")
    s.add_argument("--category", choices=["docs", "paper", "code", "discussion", "book", "article", "dataset", "video", "other"])
    s.add_argument("--rights", choices=["open", "copyrighted", "user-copy", "private", "unknown"])
    s.add_argument("--published")
    s.add_argument("--summary")
    s.add_argument("--summary-file")
    s.add_argument("--assessment", help="why this source is (or isn't) authoritative for this topic")
    s.add_argument("--question", help="question id this source was found for")
    s.add_argument("--why", help="for books to acquire: why it is worth getting")
    s.add_argument("--isbn")
    s.add_argument("--run")
    s = add("list", cmd_source_list, "list sources", sp_)
    s.add_argument("--topic")
    s.add_argument("--wanted", action="store_true", help="only the acquisition list")
    s = add("show", cmd_source_show, "metadata, or --content for the (untrusted) text with ¶ numbers", sp_)
    s.add_argument("id")
    s.add_argument("--content", action="store_true")
    s.add_argument("--from-para", type=int, default=1)
    s.add_argument("--to-para", type=int)
    s = add("refetch", cmd_source_refetch, "re-download a source (keeps the previous text)", sp_)
    s.add_argument("id", nargs="?")
    s.add_argument("--all", action="store_true")

    # evidence
    ep = sub.add_parser("evidence", help="passages and observations from sources").add_subparsers(dest="e_cmd", required=True)
    s = add("add", cmd_evidence_add, "record an exact quote (verified against the stored text) or an observation", ep)
    s.add_argument("--source", required=True)
    s.add_argument("--topic", required=True)
    s.add_argument("--quote")
    s.add_argument("--locator", help="section, page or ¶ (default: the ¶ where the quote was found)")
    s.add_argument("--note", help="your (AI) note on what it shows; kept apart from the quote")
    s.add_argument("--kind", default="quote", choices=["quote", "observation", "data"])
    s.add_argument("--question")
    s.add_argument("--concept")
    s.add_argument("--allow-unverified", action="store_true")
    s.add_argument("--run")
    s = add("list", cmd_evidence_list, "list evidence", ep)
    s.add_argument("--topic")
    s.add_argument("--source")

    # claims
    cp = sub.add_parser("claim", help="synthesized assertions with provenance").add_subparsers(dest="c_cmd", required=True)
    s = add("add", cmd_claim_add, "add a claim backed by evidence", cp)
    s.add_argument("text")
    s.add_argument("--topic", required=True)
    s.add_argument("--support", help="comma-separated evidence ids")
    s.add_argument("--counter", help="comma-separated evidence ids against it")
    s.add_argument("--kind", default="finding", choices=["finding", "interpretation", "hypothesis"])
    s.add_argument("--strength", default="moderate", choices=["strong", "moderate", "weak", "unsupported", "contested"])
    s.add_argument("--uncertainty")
    s.add_argument("--concept")
    s.add_argument("--contradicts", help="claim ids this conflicts with (both become contested)")
    s.add_argument("--question")
    s.add_argument("--reasoning")
    s.add_argument("--run")
    s = add("update", cmd_claim_update, "revise a claim (the reason is recorded)", cp)
    s.add_argument("id")
    s.add_argument("--reason", required=True)
    s.add_argument("--strength", choices=["strong", "moderate", "weak", "unsupported", "contested"])
    s.add_argument("--kind", choices=["finding", "interpretation", "hypothesis"])
    s.add_argument("--add-support")
    s.add_argument("--add-counter")
    s.add_argument("--contradicts")
    s.add_argument("--uncertainty")
    s.add_argument("--text")
    s.add_argument("--concept")
    s.add_argument("--verified", action="store_true", help="re-verified today")
    s.add_argument("--run")
    s = add("supersede", cmd_claim_supersede, "replace a claim with a newer one (old one kept)", cp)
    s.add_argument("old")
    s.add_argument("--by", required=True)
    s.add_argument("--reason", required=True)
    s.add_argument("--run")
    s = add("merge", cmd_claim_merge, "merge a duplicate claim into another", cp)
    s.add_argument("keep")
    s.add_argument("dup")
    s.add_argument("--reason", required=True)
    s.add_argument("--run")
    s = add("list", cmd_claim_list, "list claims", cp)
    s.add_argument("--topic")
    s.add_argument("--all", action="store_true", help="include superseded/retracted")

    # concepts
    kp = sub.add_parser("concept", help="concepts = units of knowledge for learning").add_subparsers(dest="k_cmd", required=True)
    for name, fn in (("add", cmd_concept_add), ("update", cmd_concept_update)):
        s = add(name, fn, f"{name} a concept", kp)
        if name == "add":
            s.add_argument("--topic", required=True)
            s.add_argument("--title", required=True)
            s.add_argument("--id")
        else:
            s.add_argument("id")
            s.add_argument("--topic", help="also link to this topic")
            s.add_argument("--title")
            s.add_argument("--reason")
            s.add_argument("--alternative", help="an alternative explanation (e.g. after 'explain it differently')")
            s.add_argument("--alternative-file")
        s.add_argument("--summary", help="one line (glance depth)")
        s.add_argument("--explanation")
        s.add_argument("--explanation-file")
        s.add_argument("--details")
        s.add_argument("--details-file")
        s.add_argument("--prompt", action="append", help="kind:text, kind in explain|predict|compare|apply|critique|reflect")
        s.add_argument("--prereq", help="comma-separated concept ids")
        s.add_argument("--related", help="comma-separated id[:relation]")
        s.add_argument("--claim")
        s.add_argument("--source")
        s.add_argument("--alias")
        s.add_argument("--perspective")
        s.add_argument("--run")
    s = add("list", cmd_concept_list, "list concepts", kp)
    s.add_argument("--topic")

    s = add("overview", cmd_overview, "show or rewrite a topic's narrative overview", sub)
    s.add_argument("topic")
    s.add_argument("--file", help="Markdown file (- for stdin)")
    s.add_argument("--text")
    s.add_argument("--reason")
    s.add_argument("--run")
    s = add("dossier", cmd_dossier, "regenerate a topic's dossier", sub)
    s.add_argument("topic")
    s.add_argument("--print", action="store_true")
    s = add("consolidate", cmd_consolidate, "find duplicates, conflicts, stale and unsupported knowledge", sub)
    s.add_argument("topic")
    s.add_argument("--apply-safe", action="store_true", help="apply only reversible, non-destructive fixes")
    s.add_argument("--run")
    add("check", cmd_check, "validate records and references", sub)
    s = add("commit", cmd_commit, "git commit the kb", sub)
    s.add_argument("-m", "--message", required=True)

    # runs
    rp = sub.add_parser("run", help="bounded research runs").add_subparsers(dest="r_cmd", required=True)
    s = add("begin", cmd_run_begin, "start a run: checks budget, picks questions, prints the brief", rp)
    s.add_argument("--topic", required=True)
    s.add_argument("--agent")
    s.add_argument("--ao-run-dir", help="agent-orchestrator run directory (for usage stats)")
    s.add_argument("--questions", type=int)
    s.add_argument("--mode", choices=["orientation", "deep", "monitor", "targeted"])
    s.add_argument("--force", action="store_true", help="recover a still-active run and go past the weekly limit")
    s = add("end", cmd_run_end, "finish a run and record its outcome", rp)
    s.add_argument("--run")
    s.add_argument("--topic")
    s.add_argument("--summary")
    s.add_argument("--summary-file")
    s.add_argument("--stop-reason", required=True,
                   help="why it stopped: questions-done | budget | exhausted | blocked | deadline | …")
    s.add_argument("--continue", dest="continue_", choices=["yes", "no"], help="is more research worthwhile?")
    s.add_argument("--next", action="append", help="recommended next investigation (repeatable)")
    s.add_argument("--notify", help="queue a notification for the user (only when it matters)")
    s.add_argument("--severity", default="important", choices=["info", "important", "action", "blocker"])
    s = add("list", cmd_run_list, "list runs with outcomes and usage", rp)
    s.add_argument("--topic")
    s = add("recover", cmd_run_recover, "mark dead active runs interrupted and release their questions", rp)
    s.add_argument("id", nargs="?")
    s.add_argument("--topic")

    np_ = sub.add_parser("notify", help="the durable notification queue").add_subparsers(dest="n_cmd", required=True)
    s = add("list", cmd_notify_list, "unread notifications", np_)
    s.add_argument("--all", action="store_true")
    s = add("add", cmd_notify_add, "queue a notification", np_)
    s.add_argument("message")
    s.add_argument("--topic")
    s.add_argument("--severity", default="info", choices=["info", "important", "action", "blocker"])
    s.add_argument("--run")
    s = add("ack", cmd_notify_ack, "mark notifications read (all if no ids)", np_)
    s.add_argument("ids", nargs="*")

    # learning
    lp = sub.add_parser("learn", help="the user's learning state (separate from the kb)").add_subparsers(dest="learn_cmd", required=True)
    s = add("next", cmd_learn, "what to learn next, with reasons", lp)
    s.add_argument("--topic")
    s.add_argument("--limit", type=int, default=5)
    s = add("status", cmd_learn, "per-concept state: observed, self-reported, inferred", lp)
    s.add_argument("--topic")
    s = add("mark", cmd_learn, "record the user's own assessment of a concept", lp)
    s.add_argument("concept")
    s.add_argument("value", choices=["new", "heard", "familiar", "known", "confused"])
    s.add_argument("--note")
    s = add("interest", cmd_learn, "mark interest in a concept", lp)
    s.add_argument("concept")
    s.add_argument("value", choices=["high", "normal", "low"])
    s = add("answers", cmd_learn, "the user's written explanations (for review)", lp)
    s.add_argument("--pending", action="store_true", help="only unreviewed")
    s = add("review", cmd_learn, "record an agent's review of a user's explanation", lp)
    s.add_argument("id")
    s.add_argument("--assessment", required=True, choices=["sound", "partial", "misconception"])
    s.add_argument("--note")
    s = add("session", cmd_learn, "plan a learning session for N minutes", lp)
    s.add_argument("--minutes", type=int, default=15)
    s.add_argument("--topic")
    add("questions", cmd_learn, "questions the user raised while reading, and their research status", lp)

    hp = sub.add_parser("highlight", help="highlights and annotations").add_subparsers(dest="hl_cmd", required=True)
    s = add("add", cmd_highlight, "highlight a passage (target: source:ID or concept:ID)", hp)
    s.add_argument("--target", required=True)
    s.add_argument("--quote", required=True)
    s.add_argument("--note")
    s.add_argument("--tag", action="append")
    s = add("list", cmd_highlight, "list highlights", hp)
    s.add_argument("--topic")

    xp = sub.add_parser("export", help="export notes").add_subparsers(dest="x_cmd", required=True)
    s = add("obsidian", cmd_export, "Obsidian-compatible Markdown: source notes and concept notes", xp)
    s.add_argument("--highlights", help="ids, or 'all'")
    s.add_argument("--concepts", help="concept ids")
    s.add_argument("--topic", help="limit 'all' highlights to a topic")
    s.add_argument("--out", help="target directory (default $KW_EXPORT_DIR or $KW_HOME/exports/obsidian)")
    s.add_argument("--force", action="store_true", help="overwrite notes you edited after export")

    rp2 = sub.add_parser("report", help="create-report integration").add_subparsers(dest="report_cmd", required=True)
    s = add("brief", cmd_report, "a create-report brief.md from the dossier (no personal learning data)", rp2)
    s.add_argument("topic")
    s.add_argument("--out", help="write here (e.g. ~/reports/<slug>/brief.md)")
    s.add_argument("--include-private-sources", action="store_true")
    s = add("guard", cmd_report, "scan a report site/ for private kinwing data before publishing", rp2)
    s.add_argument("dir")

    sc = sub.add_parser("schedule", help="recurring research via agent-orchestrator").add_subparsers(dest="sched_cmd", required=True)
    for name, h in (("add", "schedule recurring runs (cron, machine-local time)"),
                    ("run-now", "launch one background run now"),
                    ("spec", "print the agent-orchestrator task spec without scheduling")):
        s = add(name, cmd_schedule, h, sc)
        s.add_argument("topic")
        if name == "add":
            s.add_argument("--cron", required=True)
        elif name == "spec":
            s.add_argument("--cron")
        s.add_argument("--agent", choices=["claude", "codex"])
        s.add_argument("--max-duration", help="hard wall-clock limit, e.g. 45m (needs the ai-box patch)")
    for name, h in (("pause", "disable the schedule"), ("resume", "enable the schedule"), ("remove", "delete the schedule")):
        s = add(name, cmd_schedule, h, sc)
        s.add_argument("topic")
    add("list", cmd_schedule, "kinwing schedules and agent-orchestrator status", sc)

    s = add("serve", cmd_serve, "run the private reader (localhost)", sub)
    s.add_argument("--host", default=os.environ.get("KW_READER_HOST", "127.0.0.1"))
    s.add_argument("--port", type=int, default=int(os.environ.get("KW_READER_PORT", "8765")))
    return ap


def main(argv=None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    try:
        args.func(args)
    except KwError as e:
        print(f"kw: {e}", file=sys.stderr)
        return e.code
    except BrokenPipeError:  # pragma: no cover
        return 0
    return 0
