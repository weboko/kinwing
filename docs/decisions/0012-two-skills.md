# 0012 — Two skills sharing one CLI

- Date: 2026-10-28 · Status: Accepted

## Alternatives
One `kinwing` skill with sections; three or more skills (research, learn, export, report); two.

## Decision
`knowledge-research` (acquire and maintain knowledge; owns the CLI in its `bin/` and `lib/`)
and `knowledge-learn` (the user's understanding: sessions, marks, answers, reader, export).
Separation of concerns: `agent-orchestrator` decides when and how agents run,
`knowledge-research` how they acquire knowledge, `create-report` how it is presented, and
`knowledge-learn` how the user takes it in.

## Rationale
The two have different triggers ("research X" vs "what should I learn next") and different
rules (research may change the kb; learning must not invent user state). Report and export
are small enough to be sections. Both skills are discovered by Claude and Codex through
ai-box's normal skill linking.

## Reversibility
High.
