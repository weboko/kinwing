# 0010 — One-way Obsidian export, two note styles

- Date: 2026-10-28 · Status: Accepted

## Decision
`kw export obsidian` (or the reader's Export button) writes to `$KW_EXPORT_DIR`, default
`$KW_HOME/exports/obsidian`, and never to the vault unless pointed there:
- **Source notes** for sources with selected highlights: exact quotations as `>` blocks with
  `^h-…` block ids and locators, the user's notes as **My note**, the AI summary or
  assessment in a collapsed callout labelled AI-written.
- **Concept notes**, only for concepts the user picks (curated, no bulk generation):
  **My thoughts** (annotations, the user's own answers) before the AI synthesis callout, key
  evidence quotes linking to source notes, related concepts (wikilinks only where a note exists).
- A **topic note** (map of content) listing what was exported.
- Frontmatter: `kw_id` (stable), `kw_type`, `tags` (`kinwing`, `topic/<id>`), `topics`,
  `sources`, `aliases`, `created`.
- A manifest stores each note's hash. A note changed in Obsidian after export is not
  overwritten; the new version goes to `.kinwing/pending/` (`--force` overrides). Exports
  are idempotent: unchanged notes stay unchanged.

## Alternatives
Bidirectional sync (read edits back), writing straight into the vault, or a plugin. All
deferred: they risk clobbering the user's notes and are P2.

## Reversibility
High.

## Sync options (not required)
Point `--export` at a folder synced by Syncthing/Obsidian Sync/git, or copy it into the
vault; or bind-mount the vault's `Inbox/kinwing` folder as the export dir.
