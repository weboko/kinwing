# 0005 — Recurring research through agent-orchestrator; budgets in the CLI

- Date: 2026-10-28 · Status: Accepted

## Context
agent-orchestrator already provides cron scheduling (rebuilt on container start), one-shot
runs, `local`/`push` modes with persistent workdirs, skip-if-previous-alive, run logs, reports
and finalization. It has no wall-clock limit and no notion of a research budget. Subscription
logins expose no reliable token or cost meter before the fact.

## Decision
- `kw schedule add T --cron …` writes an orchestrator spec (`mode: local`,
  `workdir: $KW_HOME/kb`, explicit `kw --home …` commands) and calls `schedule.sh add`;
  `pause`/`resume`/`remove`/`run-now` call `schedule.sh` and `run-task.sh`. No scheduler of our own.
- The spec tells the agent to bracket its work with `kw run begin` / `kw run end`.
  `kw run begin` is the stopping gate. It refuses (exit 10/11/12) a paused topic, a topic
  with a run in progress, or one past `max_runs_per_week`. It selects at most
  `max_questions_per_run` questions by an explainable score and sets a deadline from
  `max_minutes`.
- `kw source add` refuses past `max_sources_per_run` or after the deadline (exit 13/14).
- `kw run end` records stats from the records tagged with the run, releases unfinished
  questions, flags low-yield runs (two in a row → "consider pausing" notification) and
  rebuilds the dossier.
- Missing capability, fixed minimally: `patches/0001` adds an optional `max_duration` key
  to agent-orchestrator (a `timeout` around the agent). An unpatched orchestrator ignores it.
- Usage numbers are read after the fact from the orchestrator's `agent.log` (Claude's
  `result` event: `total_cost_usd`, turns, tokens), and labelled as reported, not enforced.

## Alternatives considered
- Our own scheduler or daemon: duplicates cron and the orchestrator.
- Token budgets: no reliable meter under subscription logins; claiming one would be false.
- One orchestrator workdir per topic: allows parallel runs but lets two agents write the
  shared kb at once (see ADR-0006).

## Consequences
- Every run is bounded by question count, source count, deadline, weekly frequency and
  (with the patch) wall-clock time. Thinking time inside the limit is not metered.
- All topics share one workdir, so scheduled runs never overlap; a collision is logged in
  `runs/cron.<slug>.log` and the next firing catches up. Stagger the crons of busy topics.
- Interrupted runs are recovered by the next `kw run begin`: immediately if the orchestrator
  recorded an exit code, else after 2×max_minutes. Their evidence and claims are kept and
  their questions released.

## Reversibility
High. The spec is a text template; the patch is optional.
