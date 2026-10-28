# 0003 — kb, library, learning and runtime are separate

- Date: 2026-10-28 · Status: Accepted

## Context
Derived knowledge, raw material, the user's personal learning data and transient state have
different owners, sizes, sensitivity and lifecycles.

## Decision
`$KW_HOME` contains:

| Folder | Holds | Git | Who writes |
|---|---|---|---|
| `kb/` | topics, questions, source metadata, evidence, claims, concepts, runs, dossiers | yes (its own repo; the orchestrator's workdir) | research agents via `kw` |
| `library/<src-id>/` | original files and extracted text | no (large, possibly copyrighted) | `kw source add` |
| `learning/` | progress, highlights, answers, sessions, event log | no by default (personal) | the reader and `kw learn` |
| `runtime/` | lock, notifications, run briefs, schedule specs | no | `kw` |
| `exports/obsidian/` | exported notes (default; `KW_EXPORT_DIR` overrides) | no | `kw export` |

`kw` refuses a `KW_HOME` or export folder inside the public web root (`WWW_ROOT`, default `~/www`).

## Rationale
- Research never needs to read learning state, so report generation can't leak it by
  accident. `kw report brief` reads only `kb/`.
- The kb can be pushed to a private GitHub repo (orchestrator `push` mode) without shipping
  book texts or the user's annotations.
- Evidence quotes live in `kb/`, so a lost `library/` still leaves provenance intact and is
  rebuilt with `kw source refetch --all` for public sources.

## Consequences
- Backups need `kb/` (or its remote) **and** `learning/`. `library/` can be re-fetched for
  URL sources, but user-provided files must be backed up too.
- Two git repos would be needed to version learning state; it is left unversioned for now.

## Reversibility
Moderate. Paths are centralized in `store.Paths`; moving a folder is a small code change
plus a file move.
