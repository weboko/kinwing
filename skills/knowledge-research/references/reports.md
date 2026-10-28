# From dossier to report (create-report)

kinwing never renders or publishes. The pathway, with kinwing's parts marked ★:

1. The user asks for a report on topic T (and, separately, whether to publish it).
2. `bash <create-report>/scripts/new-report.sh "<Title>" <template> [short-name]` → prints the slug.
   Pick the template by the dossier's shape (create-report's `references/choosing.md`):
   most dossiers are an argument → `longread`; many distinct areas → `atlas`; a system → `blueprint`.
3. Write the verbatim request into `~/reports/<slug>/prompt.md` (private).
4. ★ `kw report brief T --out ~/reports/<slug>/brief.md` drafts the brief in create-report's
   format: TL;DR from the overview, findings from strong/moderate claims with `{S:src-id}`
   tags (kinwing source ids already look like `src-…`), one section per perspective with the
   concepts at L0–L3, disagreements from contested claims, uncertainties and open questions,
   and a Sources list with URLs and access dates. Edit it: resolve every `GAP:` line,
   write the disagreement conclusions, cut what doesn't serve the reader.
   It leaves out, by construction: everything under `learning/` (progress, highlights,
   annotations, answers, the user's questions), the topic's familiarity/objective text, and
   sources with `rights: private|user-copy` or local files (pass `--include-private-sources`
   only if the user says so; the claims resting only on them are dropped otherwise).
5. Render `site/index.html` and run `node <create-report>/scripts/check.mjs ~/reports/<slug>/site`.
6. ★ `kw report guard ~/reports/<slug>/site` must print `0 problem(s)`. It looks for the user's
   annotations, answers and questions, private source titles and paths, and learning-state files.
7. Only if the user asked to publish: `bash <create-report>/scripts/publish.sh <slug>`.
   Otherwise stop after the check and tell the user where the local preview is.

The dossier stays the source of truth; regenerate the brief for a newer snapshot.
