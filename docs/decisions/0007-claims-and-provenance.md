# 0007 — Claims backed by verified quotes; revise, never overwrite

- Date: 2026-10-28 · Status: Accepted

## Decision
- **Evidence** is a verbatim passage (or a labelled observation/data point) from one source,
  with a locator. `kw evidence add` verifies the quote against the stored text, ignoring
  whitespace, typographic quotes and Markdown markup, and refuses it otherwise (or records
  it as `quote_verified: false` with `--allow-unverified`). The paragraph locator is filled in
  automatically. The agent's paraphrase goes into a separate `note`.
- **Claim** = one sentence + `kind` (finding / interpretation / hypothesis) + `strength`
  (strong / moderate / weak / unsupported / contested) + support and counter evidence +
  uncertainty + last-verified date. No numeric confidence. A finding must cite evidence;
  without evidence a claim can only be unsupported or weak.
- **Change is additive.** `claim update` requires `--reason` and appends to the claim's
  revision history and the topic change log. `claim supersede` and `claim merge` keep the old
  record (state `superseded`, link to the replacement). `--contradicts` links both claims and
  marks both contested; neither text changes.
- **Consolidation** reports duplicates (token similarity), unlinked conflicts (similar wording,
  opposite polarity), contradicted claims, findings without evidence, stale claims, orphan
  evidence and answers resting on superseded claims. `--apply-safe` applies only flags for
  explicit contradictions and staleness.

## Rationale
The user asked for evidence, not marketing, and for conclusions they can trace. Verbatim
verification closes the most common failure (a "quote" that is a paraphrase) and makes the
navigation dossier → claim → evidence → source paragraph exact.

## Lesson recorded during the demo
A first version of `--apply-safe` also marked claims with *counter* evidence as contested.
In the demo that mislabelled two claims whose counter-evidence was a caveat. The rule was
narrowed to explicit `contradicts` links; counter-evidence is now listed for judgement.
The revision history of those claims shows both the mistake and the correction.

## Consequences
- Data from tables or figures needs `--kind data` with the row quoted. Prose figures can't
  be quoted unless the source's text contains them.
- Similarity-based duplicate detection is lexical, so it misses paraphrases (ROADMAP: embeddings).

## Reversibility
Moderate. Fields are plain YAML; a graph store could be built from them later.
