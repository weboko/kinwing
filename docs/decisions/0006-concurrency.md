# 0006 — flock plus one orchestrator workdir

- Date: 2026-10-28 · Status: Accepted

## Context
Writers: interactive Claude and Codex sessions (possibly in different containers), scheduled
runs, and the reader container (progress, highlights, questions). All share one bind-mounted
folder on one host.

## Decision
- Every read-modify-write in `kw` holds an exclusive `flock` on `runtime/kb.lock`. flock works
  across processes and across containers that bind-mount the same host directory.
- Every file write is atomic: temp file in the same directory, fsync, rename.
- Append-only logs (`changes.jsonl`, `events.jsonl`, notifications) use single `O_APPEND`
  writes, and readers skip a torn last line.
- Scheduled runs share one orchestrator workdir, so at most one runs at a time.
- One file per record keeps concurrent edits to different records conflict-free.

## Verified
`tests/test_aibox_integration.py`: 24 concurrent writers in two containers (12 CLI processes
in the agent box, 12 HTTP writes to the reader) — all questions present, every log line intact,
`kw check` clean.

## Consequences
- The lock serializes writes; each takes milliseconds, so contention is negligible at
  personal scale.
- A scheduled run's commit can include changes an interactive session made meanwhile.
  Nothing is lost, but commit attribution is approximate.
- flock is not reliable on network filesystems (NFS/SMB). Keep `$KW_HOME` on a local disk.

## Reversibility
High.
