# Discovery

What was learned by inspecting the existing infrastructure, the referenced projects and the
environment, before and during implementation. Each item is marked:

- **[confirmed]** — verified by reading code or running it in this session.
- **[assumed]** — taken from prior knowledge or documentation not inspected here; treat as
  unverified.
- **[blocked]** — could not be inspected; see the note.

Started 2026-10-28. ai-box inspected at commit `e91cfed` (2026-10-24).

## 1. The knowledge-assimilation report (xyz.tabdump.xyz)

**[blocked]** `https://xyz.tabdump.xyz/2026-10-25-knowledge-assimilation/` was not reachable
from the build environment. The egress proxy refused the host (`CONNECT tunnel failed, 403`),
WebFetch could not resolve it (`ENOTFOUND`), and a web search found no copy or mirror.

Nothing in this implementation claims to be based on that report. The learning design was
derived from the task specification and the conceptual references below. To incorporate it:
allow the host in the environment's network settings (or paste the report), then review
`docs/OPEN_QUESTIONS.md` §OQ-1, where the design choices most likely to be affected are
listed.

## 2. weboko/ai-box

### Containers and persistence [confirmed]
- Three services in `docker-compose.yml`: `claude` (Dockerfile.claude), `codex`
  (Dockerfile.codex), and opt-in `box` (both agents, `profiles: [box]`).
- `$HOME` of each is a bind mount: `./claude-box`, `./codex-box`, `./ai-box`. Credentials,
  agent config, `~/www`, `~/reports`, `~/.agent-orchestrator` all live there and survive
  rebuilds and recreation.
- `./context` is mounted **read-only** at `/opt/box-context`. `entrypoint.sh` links
  `context/AGENTS.md` (Claude: `/etc/claude-code/CLAUDE.md` at build time; Codex:
  `$CODEX_HOME/AGENTS.md`) and every `context/skills/<name>/` with a `SKILL.md` into
  `$CLAUDE_CONFIG_DIR/skills` and `$CODEX_HOME/skills` on every start.
  `link_skills` tests `[ -f "$s/SKILL.md" ]` *inside the container*. A skill folder can
  therefore be a symlink to an absolute container path (e.g. `/opt/kinwing/skills/x`), as
  long as that path is mounted. The kinwing integration relies on this (verified in
  `tests/test_aibox_integration.py`).
- Every container runs as root. The agents run with permissions bypassed:
  `bypassPermissions` in managed settings for Claude; `approval_policy = "never"` and
  `sandbox_mode = "danger-full-access"` for Codex. **The container is the only boundary.**
  Anything mounted into an agent container is fully readable and writable by an agent that
  has just read a malicious web page.
- No Docker socket is mounted into any service. `docker-ce-cli` is installed in the claude and
  box images, but without a socket it is inert.
- `box-supervisor.sh` runs the agents, `cron -f`, Caddy (`file-server --browse --root
  ~/www`, port 8080) and, with `TUNNEL_TOKEN`, cloudflared. **Everything in `~/www` may be
  public.** Before starting cron it runs
  `agent-orchestrator/bin/schedule.sh sync`, so schedules survive recreation.
- **Tooling differs per image.** `Dockerfile.claude` and `Dockerfile.box` ship `python3`
  (3.12 on Ubuntu 24.04, **no PyYAML**), node 22, jq, git and cron. `Dockerfile.codex` ships
  only `ca-certificates curl git openssh-client jq ripgrep procps caddy cron`: **no
  python3, no node.** This is why the kinwing CLI is stdlib-only Python (ADR-0013) and why
  codex-only users need a one-line image addition (`integrations/ai-box/`).
- `.env` is loaded into every container. `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` must not
  be set (remote control needs subscription OAuth). Consequence: **no reliable
  per-token budget enforcement is available.** Usage numbers only exist after the fact, in
  agent logs (see §2.3).

### agent-orchestrator [confirmed]
- Bash + jq. State in `$AO_HOME` (`~/.agent-orchestrator`). Specs are Markdown with simple
  `key: value` frontmatter (`fm_get` is an awk one-liner: no nesting, no lists).
- Modes: `pr` (worktree + PR), `push` (persistent clone), `local` (persistent local git
  repo at `workdir:`, default `$AO_HOME/workspaces/<slug>`). The README describes `local`
  and `push` as the "knowledge research mode" (commit `45a766d`).
- `run-task.sh` refuses to start when another run with the same `workdir` is still alive
  (`workdir_busy`). `run-scheduled.sh` skips a firing when the previous run of the same slug
  is alive. **Both are useful concurrency guarantees we reuse** (ADR-0006).
- `schedule.sh add|disable|resume|remove|list|sync` maintains one managed crontab block
  generated from `scheduled/*.md`. `disable` doesn't kill running agents.
- `run-agent.sh` launches `claude -p --dangerously-skip-permissions --output-format
  stream-json --verbose` or `codex exec --dangerously-bypass-approvals-and-sandbox --json -`
  under `setsid`, with the task on stdin. It writes `agent.log`, `agent.pid`, `exit_code`,
  then finalizes. The contract appended to every task gives the agent `{{RUN_ID}}` and
  `{{RUN_DIR}}`. That is how a kinwing research run can link to its orchestrator run.
- **Gap: no wall-clock limit.** Nothing bounds how long an agent runs: no `timeout`, no
  `--max-turns`. A recurring research task therefore has no hard stop at the orchestration
  level. Smallest fix: an optional `max_duration:` spec key that wraps the agent in
  `timeout` (`integrations/ai-box/patches/0001-agent-orchestrator-max-duration.patch`). The
  patch is applied by the install script only with `--apply-patches`.
- Usage data: Claude's `stream-json` log ends with a `result` event that has
  `total_cost_usd`, `usage`, `num_turns` and `duration_ms` (verified by running `claude -p
  --output-format json` here). Codex `--json` emits `turn.completed` events with `usage`
  **[assumed: event names change between releases, as the skill's own troubleshooting
  notes]**.
- Errors when a workdir is busy reach the user only through `runs/cron.<slug>.log`. With
  `set -e`, a busy shared workdir makes that firing fail and log an error rather than
  `SKIP`. Acceptable (the next firing retries); documented in OQ-4.

### create-report [confirmed]
- A presentation skill, explicitly *not* an investigator. Workflow:
  `new-report.sh "<Title>" <template>` → `~/reports/<slug>/{prompt.md, brief.md, site/}` →
  the agent writes `brief.md` (format in `references/brief.md`: TL;DR L0/L1, Findings with
  `{S:src-id}` tags, sections at L0–L3, Disagreements, Sources as `src-id: Title, URL,
  accessed`) → the agent renders `site/index.html` from the template skeleton →
  `node scripts/check.mjs site` (Playwright render check) → `publish.sh <slug>` copies to
  `~/www/<slug>/` and rebuilds `~/www/index.html`.
- `publish.sh` refuses: placeholders, missing TL;DR, citations without sources, empty
  `report.json` fields, prompt/brief files inside `site/`, an empty `brief.md`.
  `REPORTS_HOME` and `WWW_ROOT` env vars redirect both roots, which lets the demo
  validate a full publish into a scratch directory without touching a real `~/www`.
- Source ids must look like `src-<name>`. Kinwing source ids use the same shape on purpose,
  so a dossier's citations map one-to-one into a report.
- It already separates the private parts (`~/reports/<slug>/prompt.md`, `brief.md`) from the
  public `site/`. Kinwing keeps that boundary and adds its own check
  (`kw report guard`) for personal learning data.

## 3. Conceptual references

| Reference | Status | What matters for us |
|---|---|---|
| STORM / Co-STORM (README) | [confirmed] README fetched | Perspective-guided question asking (discover perspectives first, then use them to drive questions); a pre-writing stage (research + outline) separate from writing; Co-STORM's moderator raises questions from retrieved-but-unused information; a dynamic **mind map** as a shared conceptual space between user and system. The papers (arXiv) were not reachable: **[assumed]** details beyond the README. |
| SuperMemo incremental reading | [blocked] host unreachable; [assumed] from prior knowledge | Interleave many articles in small slices; extract important passages into new elements; cloze-delete extracts into items; a priority queue decides what to read next; topics get growing review intervals; overload is handled by priority, not guilt. |
| Elicit Routines | [blocked]; [assumed] | Research that "keeps working": recurring searches over a fixed question, with only the new results surfaced. |
| Letta / MemGPT, context repositories | [confirmed] Letta README (development moved to `letta-code`); blog [blocked]; [assumed] concept | Agent memory as editable, versioned files (a git-backed "context repository") that the agent reads and rewrites with ordinary file tools. Kinwing's kb is exactly such a repository for research memory. The MemGPT paging machinery is unnecessary: Claude/Codex already manage their context. |
| FSRS (open-spaced-repetition) | [confirmed] py-fsrs README and the fsrs4anki wiki fetched; they also became demo sources | Three-component memory model (difficulty, stability, retrievability). It needs graded recall events on well-defined items. Most of the learning here is generative and exploratory, so FSRS is deferred (ADR-0009). |

## 4. Build environment facts that shaped the POC [confirmed]

- Outbound network: GitHub (git clone, `raw.githubusercontent.com`), PyPI, npm, Docker Hub
  and Ubuntu archives were reachable. Wikipedia, arXiv, Reddit, HN, super-memory.org,
  letta.com and elicit.com were not. Real-source research in the demo therefore uses
  GitHub-hosted documentation, papers' companion repositories and wikis. The robots.txt
  check and the user-agent are exercised against those hosts.
- Docker 29 works (daemon started manually). Headless `claude -p` works and reports
  `total_cost_usd`, which let the demo run one *real* scheduled research cycle through
  agent-orchestrator. Codex could not be installed (`chatgpt.com` refused), so **Codex
  compatibility is by construction (same skills, same CLI), not tested live.**
- Python 3.13 locally, 3.12 in ai-box images. sqlite3 has FTS5, but it isn't used yet
  (ADR-0002).
