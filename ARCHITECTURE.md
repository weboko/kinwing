# Architecture

kinwing is a personal research and learning system built around the agents the user already
runs. Claude Code and Codex do the research. A small CLI (`kw`) keeps the knowledge, its
provenance and the user's learning state in plain files. A private reader lets the user
explore and learn from it. Decisions and their alternatives are in [`docs/decisions/`](docs/decisions/).

```
                ┌────────────────────────────── ai-box (existing) ──────────────────────────────┐
  user ──chat──▶│ claude / codex / box containers                                               │
  (remote       │   skills: knowledge-research · knowledge-learn · agent-orchestrator ·         │
   control)     │           create-report                                                       │
                │   kw CLI  (/opt/kinwing, read-only) ──┐        cron ─▶ agent-orchestrator ─┐  │
                │                                       │                 (scheduled runs)    │  │
                │   ~/reports/<slug>/ (private) ─publish.sh─▶ ~/www (public via tunnel)       │  │
                └───────────────────────────────────────┼─────────────────────────────────────┼──┘
                                                        ▼                                     ▼
                              /knowledge  ($KW_HOME, a host folder bind-mounted everywhere)
                              ├── kb/        git: topics, questions, sources, evidence, claims,
                              │              concepts, runs, dossiers (Markdown + YAML)
                              ├── library/   raw files + extracted text (not in git)
                              ├── learning/  progress, highlights, answers (personal)
                              ├── runtime/   lock, notifications, run briefs
                              └── exports/   Obsidian notes
                                                        ▲
                ┌──────────── kinwing-reader container ─┴──────────┐
  user ─browser▶│ kw serve: JSON API + static app, 127.0.0.1:8765  │   (no credentials,
  (ssh -L)      │ only /knowledge mounted                          │    no Docker socket)
                └──────────────────────────────────────────────────┘
```

## Components

| Component | What it is | Where |
|---|---|---|
| `kw` CLI | Stdlib-only Python 3.10+ package; every operation on the knowledge home | `skills/knowledge-research/bin/kw`, `lib/kinwing/` |
| knowledge-research skill | How agents onboard topics, run research, keep evidence, schedule, report | `skills/knowledge-research/SKILL.md`, `references/` |
| knowledge-learn skill | How agents help the user learn: sessions, marks, answer review, export | `skills/knowledge-learn/SKILL.md` |
| Reader | `kw serve`: HTTP JSON API (`reader.py`) + single-page app (`static/`) | same package |
| Docker image | ubuntu:24.04 + python3 + poppler + git (same Python as ai-box) | `Dockerfile`, `docker-compose.yml` |
| ai-box integration | install script, generated compose override, optional patches | `integrations/ai-box/` |

Modules: `store` (paths, lock, atomic writes, ids), `yamlio` (YAML subset), `kb` (records,
validation), `ingest` (fetch, extract, dedupe), `runs` (lifecycle, budgets, recovery, usage),
`dossier`, `consolidate`, `learning`, `export` (Obsidian), `report` (create-report brief and
guard), `schedule` (agent-orchestrator), `notify`, `mdrender` (safe Markdown), `reader`, `cli`.

## Data model

Records (one Markdown file each, YAML frontmatter, stable ids). Full fields:
[`skills/knowledge-research/references/data-model.md`](skills/knowledge-research/references/data-model.md).

```
Topic ─┬─< Question (queue: origin, priority, value, cost, status, depends_on, result)
       ├─< Run (budget, selected questions, stats, stop reason, usage)
       └── overview.md (agent narrative) → dossier.md (generated) + changes.jsonl (append-only)
Source ─< Evidence (verbatim quote | observation | data, locator, verified?)
Claim  >─ Evidence (support / counter), Claim ─ Claim (contradicts / supersedes)
Concept ─ Concept (prerequisites, related: contrasts, part-of, …) ─ Claims, Sources
learning/: per-concept observed · self-report · interest · revisit; highlights; answers; sessions
```

Topics, sources, claims and concepts are many-to-many through `topics:` lists. Raw text sits
in `library/` and derived knowledge in `kb/`, so evidence quotes survive a lost library.

## Research lifecycle (one run)

```
kw run begin ──▶ checks: topic active? another run active? weekly budget? (exit 10/11/12)
     │           recovers interrupted runs (agent exited, or 2×max_minutes passed)
     │           selects ≤ max_questions by score (priority, value, origin, cost, deps)
     │           prints the brief: objective, familiarity, prior run's advice, known
     │           conclusions and sources, perspective coverage, selected questions
     ▼
agent works: kw source add (dedupe by canonical URL + content hash; robots.txt; budget/deadline
             enforced) → kw source show --content (UNTRUSTED markers) → kw evidence add (quote
             verified) → kw claim add/update/supersede (--reason) → kw concept add/update →
             kw q update/add → overview.md
     ▼
kw consolidate → kw check → kw run end (stats, release unfinished questions, low-yield
             detection, dossier rebuild, optional notification) → git commit
```

Modes (orientation, deep, monitor, targeted) share this mechanism and differ only in the
brief's guidance. Perspectives (STORM-style, derived per topic) drive question generation
and show up as coverage gaps.

Recurring runs: `kw schedule add` writes an agent-orchestrator spec (local mode, workdir
`kb/`) and registers it with `schedule.sh`. Cron fires `run-scheduled.sh` (skipped if the last
run is alive), then `run-task.sh` (one run per workdir), then `run-agent.sh` (Claude or Codex,
optionally under `timeout` with the max_duration patch). The agent follows the spec, which
calls `kw run begin` … `kw run end`. The orchestrator's `agent.log` later yields usage numbers.

## Reading lifecycle

```
reader home ─▶ notifications, "continue where you left off", suggested next (with reasons),
               topics (changes since last visit, your progress), due revisits, sessions
topic ───────▶ overview · concept map (layers by prerequisite) · conclusions (claims →
               quoted evidence → source paragraph) · unknowns · sources · activity
concept ─────▶ depth: glance | read | deep · prompts (answers saved verbatim) · familiarity
               buttons · interest · go deeper / explain differently / not convinced / ask
source ──────▶ extracted text with ¶ numbers, evidence paragraphs marked, resume position
anywhere ────▶ select text → highlight / note / ask / not convinced
```

What the reader records: observed behaviour (views, scroll progress, paragraph, time, depth,
completion), self-reports, highlights and notes, answers, and questions. Questions become
research questions (`origin: learning`, priority boost), so the next run picks them up; the
"My questions" page shows their status and answers. Inferred understanding is computed from
these records with its basis shown, and is never assumed.

## Public / private boundary

| Thing | Private? | Guarantee |
|---|---|---|
| `kb/`, `library/` | private | never written under `WWW_ROOT` (kw refuses a home or export dir inside it) |
| `learning/` | private, personal | never read by `kw report brief`; `kw report guard` flags it if found in a site |
| reader | private | loopback port, Host allowlist, CSRF header, optional token, CSP, escaped content |
| report workspace `~/reports/<slug>/` | private | create-report's own rule (prompt.md, brief.md never published) |
| `~/www/<slug>/` | public | only via create-report `publish.sh`, after `check.mjs` and `kw report guard`, when asked |

External text is untrusted: stored as data, shown between UNTRUSTED markers to agents,
escaped in the reader, and the skills forbid following instructions found in it. The agents
still run with permissions bypassed (ai-box's design), so a prompt-injected agent could
misuse anything mounted in its box. kinwing adds only the knowledge folder and a read-only
code mount to the boxes, and the reader container holds neither credentials nor the Docker
socket. See `docs/OPEN_QUESTIONS.md` for what remains open.

## Docker layout

- **With ai-box** (recommended): `integrations/ai-box/install.sh` → knowledge folder and code
  mounted into `claude`/`codex`/`box`; `kinwing-reader` service added. Persistence comes from
  the host folder; ai-box's supervisor rebuilds the cron block on start, so schedules survive
  recreation (tested).
- **Standalone**: `docker compose up -d reader` (+ `docker compose run --rm kw …`) on `./knowledge`.
- Tests: `docker compose run --rm test` or `scripts/test.sh --docker`.
