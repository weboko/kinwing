# 0002 — Files are the source of truth; no database yet

- Date: 2026-10-28 · Status: Accepted

## Context
Knowledge must stay portable, inspectable, versionable and easy for agents to read and edit.
Agents work best with files they can `cat`, `grep` and diff.

## Problem
Filesystem only, or files plus SQLite?

## Alternatives
1. **SQLite as the source of truth.** Fast queries and transactions, but opaque to agents
   and humans, harder to diff and to merge, and a migration burden.
2. **Files plus a rebuildable SQLite index** (FTS5 for search, joins for the reader).
3. **Files only**, scanned on demand.

## Decision
Option 3 for the POC. Every record is one Markdown file with YAML frontmatter
(`kb/<kind>/<id>.md`); topic config is `topic.yaml`; append-only logs are JSONL. The design
keeps option 2 open: an index would be derived from the files and could be deleted at any time.

## Rationale
- At POC scale (hundreds to low thousands of records) a full scan costs milliseconds.
  The reader and CLI stay simple, and there is one source of truth with nothing to keep in sync.
- Git history of `kb/` doubles as the audit log of what each run changed.
- Obsidian and any editor can read the records directly.

## Consequences
- Search is a substring scan (`/api/search`). It is slow beyond ~10k records, and there is no ranking.
- Cross-record queries (which claims cite this source?) are linear scans.
- Atomic multi-file updates rely on the lock (ADR-0006), not transactions. Each file write is
  atomic (temp file + fsync + rename), and an interrupted run is detected and recovered (ADR-0005).

## Reversibility
High. Add `runtime/index.sqlite` built from the files (FTS5 is available in the images); no
record format changes. See ROADMAP "Search index".
