# Data model (files and fields)

All records: Markdown with YAML frontmatter, one file per record, under `$KW_HOME/kb/`.
Ids are stable once created. `kw check` validates references.

| Record | Path | Id | Key fields |
|---|---|---|---|
| Topic | `topics/<id>/topic.yaml` | slug, chosen at creation | title, objective, familiarity, known_concepts, depth, boundaries, preferred_sources, perspectives[], budget{max_questions_per_run, max_sources_per_run, max_minutes, max_runs_per_week}, schedule{}, status, last_investigated, stale_after_days, research_priorities, learning_priorities |
| Overview | `topics/<id>/overview.md` | — | the agent's narrative; embedded in the dossier |
| Dossier | `topics/<id>/dossier.md` | — | generated; never edit |
| Change log | `topics/<id>/changes.jsonl` (+ generated `changes.md`) | — | at, kind, id, summary, run, detail (the why) |
| Question | `questions/q-YYYYMMDD-xxxx.md` | `q-…` | topic, text, origin, asked_by, perspective, priority, value, cost, status, depends_on, concepts, claims, context, result, runs, last_evaluated; body: history |
| Source | `sources/src-<slug>-<hash>.md` | `src-…` | title, authors, organization, url, canonical_url, aliases, local_path, published, retrieved, content_type, category, rights, access, content_hash, extraction, topics, questions, added_by_run, assessment; body: AI summary. Text: `library/<id>/content.txt`, original: `library/<id>/original.*` |
| Evidence | `evidence/ev-….md` | `ev-…` | source, kind (quote/observation/data), quote, quote_verified, locator (¶n, §, page), note (AI), topics, questions, concepts, run |
| Claim | `claims/cl-….md` | `cl-…` | text, topics, concepts, kind, strength, state (current/superseded/retracted), support[], counter[], contradicts[], supersedes[], superseded_by, uncertainty, last_verified, run; body: reasoning + revisions |
| Concept | `concepts/<slug>.md` | slug | title, aliases, topics, perspective, summary, prerequisites[], related[{id, rel}], claims[], sources[]; body sections: Explanation, Details, Alternative explanation, Prompts, Previous versions |
| Run | `runs/run-….md` | `run-…` | topic, mode, status, started, deadline, ended, budget, questions_selected, stats, stop_reason, continue, next_steps, low_yield, usage, ao_run_dir; body: summary |

Learning state (`$KW_HOME/learning/`) is described in the knowledge-learn skill.
