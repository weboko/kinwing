# HANDOFF — read this first

For whoever (human or agent) continues this project. It records what exists, what was
decided, what is missing, broken or unverified, and what to do next. Keep it current: when you
close an item, delete it here and note the change in `docs/IMPLEMENTATION_LOG.md`.

Last updated: 2026-10-28, branch `feat/great-ride-jsqdfd` (pushed to `weboko/kinwing`).

## 1. What this is, in five lines

- kinwing = a personal research + learning system for people running Claude Code / Codex in
  [weboko/ai-box](https://github.com/weboko/ai-box). It is a companion repo, not a fork.
- Agents do the research. The `kw` CLI (stdlib Python, `skills/knowledge-research/bin/kw`)
  stores everything as Markdown + YAML under `$KW_HOME` (`kb/` git repo, `library/`, `learning/`,
  `runtime/`, `exports/`).
- Two skills: `skills/knowledge-research` (research) and `skills/knowledge-learn` (the user's learning).
- A private reader (`kw serve`, port 8765) runs in its own container (`Dockerfile`, `docker-compose.yml`).
- `integrations/ai-box/install.sh` wires it into ai-box. Recurring research uses ai-box's
  agent-orchestrator; reports use ai-box's create-report.

## 2. Where everything is documented

| Need | File |
|---|---|
| Setup and usage | `README.md` |
| How it fits together | `ARCHITECTURE.md` |
| Why each choice was made (13 ADRs with alternatives) | `docs/decisions/` |
| What was found inspecting ai-box, the references and the environment | `docs/DISCOVERY.md` |
| What was actually run in the demo, step by step | `docs/DEMO.md`, `examples/fsrs-demo/transcript.md` |
| Chronological changes and problems hit | `docs/IMPLEMENTATION_LOG.md` |
| Unresolved design questions | `docs/OPEN_QUESTIONS.md` (OQ-1 … OQ-9) |
| Deferred features | `docs/ROADMAP.md` |
| What was borrowed from STORM, SuperMemo, Letta, etc. | `docs/RESEARCH_REFERENCES.md` |
| The agent protocol for a research run | `skills/knowledge-research/references/research-run.md` |
| Record formats | `skills/knowledge-research/references/data-model.md` |
| Example output (kb, learning state, export, report, screenshots) | `examples/fsrs-demo/` |

## 3. How to get going (5 minutes)

```bash
python3 -m unittest discover -s tests -t .          # 77 tests; needs only python3 ≥ 3.10
```

```bash
AIBOX_DIR=/path/to/ai-box scripts/test.sh            # + agent-orchestrator tests, both YAML parsers
```

```bash
AIBOX_DIR=/path/to/ai-box scripts/test.sh --docker   # in the image + ai-box Docker integration test
```

```bash
cp -r examples/fsrs-demo/home /tmp/h && KW_HOME=/tmp/h skills/knowledge-research/bin/kw source refetch --all && KW_HOME=/tmp/h skills/knowledge-research/bin/kw serve
```

The last one gives you the demo knowledge base in the reader at http://localhost:8765/.
Code map: `skills/knowledge-research/lib/kinwing/` — `store` (paths, lock, ids), `yamlio`,
`kb` (records), `ingest`, `runs`, `dossier`, `consolidate`, `learning`, `export`, `report`,
`schedule`, `notify`, `mdrender`, `reader`, `cli`, `static/` (reader UI).

## 4. Blockers that were outside this session's control

| # | What | Why | What to do |
|---|---|---|---|
| B1 | **The user's knowledge-assimilation report was never read** (`https://xyz.tabdump.xyz/2026-10-25-knowledge-assimilation/`) | Host blocked by the build environment's network policy | Get its content (allow the host or ask the user to paste it). Compare it with ADR-0009 and the reader flows; supersede ADRs where it disagrees. See OQ-1. |
| B2 | **No real autonomous agent has run a scheduled research task** | Launching a background agent with bypassed permissions was blocked in the build session | In a real ai-box: `kw schedule run-now <topic>` with Claude; read `~/.agent-orchestrator/runs/<id>/report.md` and `git -C /knowledge/kb log -p`; fix the protocol where the agent drifts. See OQ-2. |
| B3 | **Codex never ran** | Codex installer host refused in the build environment | Same as B2 with `--agent codex`. Check that the skills load and that `runs.read_usage` parses `codex exec --json` events (names are a guess). See OQ-3. |

The research in the demo was done by Claude Code interactively, following the skill. The
scheduled runs used `tests/fakes/claude`, a stand-in that follows the protocol without an LLM.
`docs/DEMO.md` marks this clearly; don't present those runs as real agent output.

## 5. Known gaps and weaknesses (by area)

Verified behaviour is in the tests. Everything below is **missing, partial or untested**.

### Research / CLI
- **Schedules of different topics can collide**: all use one orchestrator workdir, so a firing
  during another topic's run fails with "workdir busy" (logged in `runs/cron.<slug>.log`, not a
  clean SKIP) and waits for the next firing. Advice for now: stagger crons. (OQ-4)
- **Weekly budget** counts interrupted runs and any manual `kw run begin` too.
- **No token or money limit** is enforced (none can be under subscription logins). Only
  questions, sources, deadline, runs per week and, with the patch, wall-clock time are limited.
- **Ingestion**: no JavaScript-rendered pages; no special handling for arXiv, DOI, Reddit, GitHub
  issues or discussions. GitHub repo, blob and wiki URLs are mapped to raw Markdown. PDF quote
  verification can fail on ligatures and hyphenation (OQ-5). Large books are fine in `library/`,
  but the reader shows at most 1,500 paragraphs, with no "load more" button.
- **Duplicate and conflict detection** in `consolidate` is lexical (token overlap and negation
  words), so paraphrases are missed.
- `kw report brief` is a **draft**: TL;DR L1 is rough when the overview is a list, and
  disagreement conclusions are left as `GAP:` for the agent.
- Concept quality depends on the agent; there's no check for thin or duplicate concepts (OQ-7).
- Search is a substring scan over files (fine below ~10k records; ADR-0002 has the upgrade path).

### Learning / reader
- **No automated UI tests.** The reader was checked with a Playwright script
  (`demo/learn-session.js`) and screenshots only. Turning that script into a test is a good
  first task.
- Highlight anchoring is text-based; overlapping highlights and selections across many
  elements may fail silently (the highlight is saved but not drawn). Touch and mobile
  selection is untested.
- A concept counts as "read to the end" only after 97% scroll and 15 s of dwell, or the
  explicit button. Short pages often stay "started".
- "Changes since last visit" is cleared by a button; the first visit marks the start silently.
- No CLI command to record "I revisited it" (the reader has it: `POST /api/revisited`).
- `/api/consolidation/<topic>` exists but the UI doesn't use it.
- Breadcrumbs show the topic id, not its title. The session bar's sticky offset is hard-coded.
- Single user. The token (`KW_READER_TOKEN`) is a shared secret; no accounts.

### Storage / ops
- `learning/` is **not versioned or backed up** by anything (OQ-6). `library/` is outside git;
  web sources can be re-fetched, the user's own files cannot.
- flock locking isn't reliable on network filesystems; keep `$KW_HOME` on local disk.
- Docker compose uses fixed container names (`kinwing-reader`, ai-box's `ai-box`), so the
  integration test skips when they already exist.
- `install.sh` won't touch an existing `docker-compose.override.yml` it didn't write; that case
  needs a manual merge.
- The ai-box patches (`integrations/ai-box/patches/`) are **not upstreamed** to ai-box. 0001
  (max_duration) was made against ai-box commit `e91cfed` and may stop applying cleanly.

### Security
- Agents in ai-box run with permissions bypassed; a prompt-injected agent can read and write
  everything mounted in its box, including `/knowledge`. kinwing adds only that folder and a
  read-only code mount (OQ-8). The reader container has no credentials.
- External text is marked UNTRUSTED for agents and escaped in the reader. That is a mitigation,
  not a guarantee.

### Docs
- The ADRs were written during one session; nothing in them has been validated by real use.
- `examples/fsrs-demo` reflects code as of the demo; regenerate it if the record format changes.

## 6. Decisions you might want to revisit (and the ADR to supersede)

| Decision | Revisit if… | ADR |
|---|---|---|
| Files only, no SQLite index | search or the reader gets slow (>~10k records) | 0002 |
| One orchestrator workdir for all topics | schedule collisions hurt (OQ-4) | 0005, 0006 |
| No flashcards / FSRS for the user | the user wants memorisation for some topics, or the report (B1) says so | 0009 |
| One-way Obsidian export | the user wants edits in Obsidian to flow back | 0010 |
| Two skills | agents mix them up in practice | 0012 |
| Stdlib Python + built-in YAML | ai-box images gain PyYAML (then simply prefer it; it already does) | 0013 |

## 7. Suggested next tasks, in order

1. **B1**: obtain the report and reconcile the learning design with it.
2. **B2/B3**: one real scheduled run each with Claude and Codex in ai-box; fix what breaks;
   record the results in `docs/DEMO.md`.
3. Turn `demo/learn-session.js` into an automated reader test (start `kw serve` on a temp
   home in `setUpClass`, run Playwright, assert recorded state).
4. Make a "workdir busy" collision a clean SKIP (small ai-box change) or stagger schedules
   automatically (OQ-4).
5. PDF normalization for quote verification (ligatures, soft hyphens) (OQ-5).
6. A backup story for `learning/` (OQ-6).
7. Upstream `patches/0001` to ai-box, or drop it if ai-box adds its own time limit.
8. Then `docs/ROADMAP.md` from the top.

## 8. Environment notes from the build session (may not apply to you)

- Only GitHub (git and raw), package registries and Docker Hub were reachable. Most research
  sites, the report host and the Codex installer were blocked.
- The Docker daemon was started manually; builds needed `docker build --network host`
  (the egress proxy was on localhost and HTTPS-only). On a normal host, `docker compose build` works.
- create-report's `check.mjs` was pointed at a preinstalled Playwright via `XDG_CACHE_HOME`.
