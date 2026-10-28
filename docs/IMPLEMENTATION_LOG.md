# Implementation log

Chronological. Each entry: what changed, why, what was tested, problems, what remains.

## 2026-10-28 — Phase A: discovery

- Read ai-box at `e91cfed`: Dockerfiles, compose, entrypoint, supervisor, daemons, AGENTS.md,
  agent-orchestrator (all scripts and templates) and create-report (SKILL, core reference,
  brief format, longread template, new-report/publish/check/formats scripts). Findings in
  DISCOVERY.md §2. They decided the architecture: reuse skills linking and `local` mode;
  python3 but no PyYAML in claude/box; no python in codex; no time limit in the orchestrator.
- The knowledge-assimilation report URL was blocked by the environment (proxy 403, WebFetch
  ENOTFOUND, no search hits). Recorded in DISCOVERY §1 and OQ-1. Did not invent its content.
- Network map of the build environment: GitHub (git and raw) and package registries
  reachable; most research sites not. This set the demo's source strategy.

## Phase B/C: foundation and research pipeline

- `store` (paths, flock, atomic writes, ids), `yamlio` (emitter + built-in parser, PyYAML
  when present), `kb` (topics, questions with explainable scoring, evidence with verbatim
  verification, claims with revisions/supersede/merge/contradicts, concepts with sections),
  `ingest` (canonical URLs, GitHub→raw mapping, robots.txt, HTML/Markdown/PDF/EPUB extraction,
  URL + content-hash dedupe, untrusted wrapper), `runs` (begin/end, budgets, recovery,
  low-yield, usage from orchestrator logs), `dossier`, `consolidate`, `notify`, `cli`.
- Smoke-tested by hand, then with the test suite.
- Problems fixed: duplicate detection missed questions ending in "?"; change log and visit
  timestamps needed milliseconds to order events within one second; canonicalisation
  upgraded http→https, which broke fetching plain-http sites (now: canonical form for
  identity, original URL for fetching).

## Phase D: learning interface

- `learning` (observed/self-reported/inferred, highlights with source-quote verification,
  answers and agent review, questions into the research queue, recommendations with reasons,
  sessions, revisit dates), `mdrender` (escaping Markdown renderer), `reader` (JSON API,
  security checks) and the static app (topic tabs, concept map by prerequisite layers,
  glance/read/deep, prompts, familiarity and interest controls, ask/challenge/deeper/
  explain-differently, text-quote highlight anchoring, progress tracking and resume,
  highlights page with export, questions page, sessions, search).
- Browser-checked with Playwright. Problems fixed: inline `style` attributes violated the
  CSP (moved to classes); `replaceChildren` turned `null` into the text "null"; the session
  bar ignored `hidden` because of `display:flex`; reverse relations were labelled oddly; a
  fully scrolled but not completed page was called "unfinished".

## Phase E: export and reports

- `export` (source notes, curated concept notes, topic map, manifest-protected re-export),
  `report` (create-report brief, privacy guard), `schedule` (orchestrator spec, add/pause/
  resume/remove/run-now/list).
- Problems fixed: re-exporting concepts dropped highlights exported earlier from the same
  source note; kinwing wikilinks `[[concept-id]]` dangled in Obsidian (now rewritten to note
  names or plain text); the export timestamp made every re-export an "update" (moved to the
  manifest, `created` kept stable); user questions leaked into briefs' "open questions"
  (now excluded, and the guard looks for them).

## Tests

- 77 tests (`unittest`, no network, no LLM): YAML parity, entities, ingestion formats and
  dedupe, robots.txt, runs (budgets, deadline, weekly limit, recovery, low yield, usage), dossier,
  consolidation, learning, export, report privacy (including "ordinary operations never write
  to WWW_ROOT"), reader security, scheduling through the real agent-orchestrator scripts with a
  stand-in agent and a fake crontab, the max_duration patch, and a Docker integration test
  using ai-box's real compose, entrypoint and supervisor.
- Run on the host (PyYAML and built-in parser) and inside the image (Python 3.12, built-in parser).

## Docker and ai-box integration

- Image on ubuntu:24.04 (same Python as ai-box). The first attempt on python:3.12-slim failed
  in this environment: its Debian mirror wasn't reachable and the egress proxy only supports
  HTTPS CONNECT. Builds here use `--network host`; on a normal host plain `docker compose build` works.
- `install.sh`: symlinks to `/opt/kinwing/skills/*`, generated override, optional patches.
  The skill-link trick (symlink valid only inside the container) was verified with ai-box's
  real entrypoint in Docker.
- `patches/0001` (max_duration), `patches/0002` (python3 in the codex image).

## Phase F: demonstration (docs/DEMO.md)

- Real research on FSRS across three runs (two orientation runs and one targeted run). The
  second run found that the benchmark's SM-2 rows had been removed in August 2025, recovered
  them from git history, and superseded run 1's "not shown" conclusion.
- Report through create-report (brief → longread → check.mjs ok → guard → publish.sh into a
  scratch web root), learning session in the reader container driven by Playwright, Obsidian
  export, persistence across recreate and down/up, orchestration (weekly limit, overlap skip,
  pause/resume, max_duration kill and recovery).
- Problems found and fixed during the demo: GitHub wiki titles ("Symbol"); an over-eager
  `--apply-safe` that mislabelled caveated claims as contested (rule narrowed, claims
  restored with recorded reasons, test added); brief TL;DR carried wikilinks and repeated
  claims; the first run's brief wording.
- Not possible here: launching an autonomous nested Claude agent (blocked by the session's
  safety policy) and installing Codex (download host refused). Both are in OQ-2/OQ-3.

## Remaining work

See docs/OPEN_QUESTIONS.md and docs/ROADMAP.md.
