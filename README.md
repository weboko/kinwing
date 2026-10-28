# kinwing

A personal, continuously running research and learning system for people who already work
with Claude Code and Codex in [ai-box](https://github.com/weboko/ai-box) containers.

- **Research agents accumulate knowledge.** Topics, a prioritized question queue, sources,
  verbatim evidence, claims with provenance and revision history, concepts, and an evolving
  dossier per topic. Runs are bounded and cumulative, and recurring research is scheduled
  through ai-box's agent-orchestrator.
- **You assimilate it.** A private reader with a concept map, adjustable depth, evidence down
  to the source paragraph, highlights and notes, resume, prompts that ask you to explain or
  predict, and a "not convinced / go deeper" button that becomes the next research question.
  Your learning state is kept separate: research never counts as your knowledge.
- **It stays yours.** Plain Markdown + YAML in a git repo, raw material next to it, an
  Obsidian export, reports through ai-box's create-report only when you ask.

**Continuing this work? Read [HANDOFF.md](HANDOFF.md) first:** state, blockers, known gaps
and the next tasks.

Start here: [ARCHITECTURE.md](ARCHITECTURE.md) · [decisions](docs/decisions/) ·
[demo](docs/DEMO.md) · [discovery](docs/DISCOVERY.md) · [open questions](docs/OPEN_QUESTIONS.md) ·
[roadmap](docs/ROADMAP.md) · [implementation log](docs/IMPLEMENTATION_LOG.md) ·
[references](docs/RESEARCH_REFERENCES.md).

## Setup with ai-box (recommended)

Prerequisites: a working ai-box checkout with Claude and/or Codex logged in (see its README).
kinwing adds no logins of its own.

```bash
git clone https://github.com/weboko/kinwing.git      # next to your ai-box checkout
```

```bash
kinwing/integrations/ai-box/install.sh ai-box --apply-patches
```

`--apply-patches` adds an optional `max_duration` limit to agent-orchestrator (review it in
`integrations/ai-box/patches/`). For a codex-only box add `--codex-python`. To keep Obsidian
exports in a separate host folder add `--export ~/obsidian-inbox/kinwing`. Storage defaults
to `knowledge/` next to ai-box; change it with `--knowledge DIR`. What the script changes is
listed in [integrations/ai-box/README.md](integrations/ai-box/README.md).

```bash
cd ai-box && ./box build kinwing-reader
```

```bash
./box up -d --force-recreate box kinwing-reader       # or: claude / codex
```

```bash
./box exec box /opt/box-context/skills/knowledge-research/bin/kw status
```

The skills load in new agent sessions after the recreate. The reader is at
<http://localhost:8765/> on the host; from a laptop, tunnel it:

```bash
ssh -L 8765:127.0.0.1:8765 your-vps
```

Optionally put `KW_READER_TOKEN=<random>` in ai-box's `.env`, recreate `kinwing-reader`, and
open `http://localhost:8765/?token=<random>` once.

## Using it

Talk to Claude or Codex in your box (remote control or terminal):

| You say | What happens |
|---|---|
| "I want to understand the economics of decentralized messaging. Start researching it. I know the protocols; focus on incentives, network effects and failed adoption attempts." | `knowledge-research` onboards the topic (objective, familiarity, scope, perspectives, seed questions) and runs the first orientation run |
| "Research this every Monday, Wednesday and Friday." | `kw schedule add <topic> --cron "0 9 * * 1,3,5" --max-duration 45m` |
| "What have you discovered since last week?" / "What is still unknown?" | `kw changes --since 7d`, `kw notify list` / `kw unknowns <topic>` |
| "Find the most authoritative books on this." | research + `kw source add --metadata-only …` (an acquisition list; no unauthorized downloads) |
| "Add this paper." | `kw source add <url>` or `--file paper.pdf` |
| "Pause recurring research for this topic." | `kw topic pause <topic>` (also disables the schedule) |
| "What should I learn next?" / "Teach me for 15 minutes." | `knowledge-learn`: `kw learn next`, `kw learn session --minutes 15`, then a conversation |
| "I already understand X." / "I don't understand this explanation." | `kw learn mark X known` / `confused` + another explanation, or a research question |
| "Generate a comprehensive report from what we know." | `kw report brief` → create-report (render, check, `kw report guard`); published only if you ask |
| "Export my highlights to Obsidian." | `kw export obsidian --highlights all [--concepts …]` |

In the reader: open a topic, read the overview or pick from the concept map, switch
glance/read/deep, select any text to highlight, add a note or question it, answer the
prompts, mark how well you know a concept, and use **I'm not convinced / Go deeper /
Explain differently**. Those buttons create research questions that the next run picks up.

The CLI directly (inside a box, or `docker compose run --rm kw …` standalone):

```bash
kw status
kw topic new --title "…" --objective "…" --familiarity "…" --depth orientation|deep|monitor|targeted
kw run begin --topic T        # … research …     kw run end --topic T --summary "…" --stop-reason "…"
kw dossier T                  # kb/topics/T/dossier.md
kw schedule list | pause T | resume T
kw export obsidian --highlights all --out ~/obsidian-inbox
kw serve                      # the reader on 127.0.0.1:8765
```

`kw <command> -h` documents every option. The agents' guides are
[skills/knowledge-research/SKILL.md](skills/knowledge-research/SKILL.md) (+ `references/`) and
[skills/knowledge-learn/SKILL.md](skills/knowledge-learn/SKILL.md).

## Standalone (without ai-box)

```bash
docker compose build
```

```bash
KW_HOST_DIR=$HOME/knowledge docker compose up -d reader
```

```bash
KW_HOST_DIR=$HOME/knowledge docker compose run --rm kw topic new --title "My topic"
```

Or without Docker: `skills/knowledge-research/bin/kw` needs only Python ≥ 3.10 (`KW_HOME`
defaults to `~/knowledge`). Any agent that can run shell commands can use the skills. Without
agent-orchestrator, `kw schedule` is unavailable; run research by asking your agent.

## Stopping, restarting, upgrading

```bash
./box stop kinwing-reader          # or: docker compose stop reader
```

```bash
./box up -d kinwing-reader         # state is in the knowledge folder; nothing is lost
```

```bash
git -C ../kinwing pull && ./box build kinwing-reader && ./box up -d --force-recreate box kinwing-reader
```

Backups: `knowledge/kb` is a git repo (add a private remote and push), `knowledge/learning`
holds your personal state (back it up), and `knowledge/library` can be re-fetched for web
sources (`kw source refetch --all`) but not for your own files.

## Tests

```bash
scripts/test.sh            # unit + scenario tests, both YAML parsers (clones ai-box once for the orchestrator tests)
```

```bash
scripts/test.sh --docker   # inside the image, plus the ai-box Docker integration test
```

The suite needs no network or LLM: fetches use local HTTP servers, scheduling uses a
stand-in agent and a fake crontab.

## Status

| | Capability |
|---|---|
| **Implemented and tested** | Docker image and compose; ai-box install (skills linking, override, patches; Docker integration test with ai-box's own compose, entrypoint and supervisor); topics and configuration; question queue with explainable priorities and dependencies; ingestion of URLs (HTML, Markdown, GitHub repo, blob and wiki pages), PDF, EPUB and text, with robots.txt and dedup by URL and content; acquisition list; verified evidence; claims with kinds, strengths, revisions, supersede, merge and contradictions; concepts; dossier and change history; consolidation; bounded runs (question, source, deadline and weekly limits, recovery, low-yield notice, usage from logs); scheduling, pause/resume, overlap skip and max_duration via agent-orchestrator; notifications; learning state (observed, self-reported, inferred), highlights, answers and reviews, sessions, recommendations; reader API with security checks; Obsidian export; create-report brief and privacy guard; persistence across container recreation; concurrent writers across containers |
| **Implemented, tested less** | The reader UI (Playwright-driven demo and screenshots, no automated UI tests in the suite); real research quality (one topic, three runs, done interactively by Claude Code) |
| **Partially implemented** | Codex: same skills and CLI, never run live here (OQ-3); usage parsing for Codex logs is a best guess |
| **Deferred** | Spaced-repetition items (FSRS), search index, graph view, bidirectional Obsidian sync, push notifications, multi-user — see [ROADMAP](docs/ROADMAP.md) |
| **Blocked** | Reading the knowledge-assimilation report (host unreachable from the build environment, OQ-1); a fully autonomous scheduled agent run (not allowed in the build session, OQ-2) |

## Repository layout

```
skills/knowledge-research/   SKILL.md, references/, bin/kw, lib/kinwing/ (the CLI, reader, static app)
skills/knowledge-learn/      SKILL.md
integrations/ai-box/         install.sh, README.md, patches/
tests/                       unittest suite, fakes/ (stand-in agent, crontab)
examples/fsrs-demo/          the demonstration's knowledge base, learning state, export, report, screenshots
demo/learn-session.js        the browser-driven learning session used in the demo
docs/                        DISCOVERY, DEMO, OPEN_QUESTIONS, ROADMAP, IMPLEMENTATION_LOG, RESEARCH_REFERENCES, decisions/
```
