# 0011 — create-report through a generated brief and a privacy guard

- Date: 2026-10-28 · Status: Accepted

## Decision
kinwing does not render or publish. `kw report brief T --out ~/reports/<slug>/brief.md`
drafts create-report's private brief from the topic's records (TL;DR from the overview,
findings with `{S:src-id}` tags, perspective sections at L0–L3, disagreements, risks and
open questions, sources with access dates). kinwing source ids already have create-report's
`src-…` shape. The agent edits it and continues create-report's own workflow (render,
`check.mjs`, `publish.sh` only when asked). `kw report guard <site>` scans a report for
the user's annotations, answers and questions, private source titles and paths, and
learning-state files; the skill requires 0 problems before `publish.sh`.

By construction the brief excludes `learning/`, questions the user raised, the topic's
objective and familiarity text, and private or user-provided sources; claims resting only
on excluded sources are dropped.

## Rationale
create-report stays a presentation skill, unchanged. Its checks (citations, placeholders,
private files) still run. The dossier remains the living record; a report is a snapshot.

## Verified
Demo: brief → longread page → `check.mjs` ok → guard 0 problems → `publish.sh` into a scratch
`WWW_ROOT`. Tests: no ordinary kw operation writes under `WWW_ROOT`; the guard catches a
planted annotation.

## Reversibility
High.
