# 0001 — A companion repo mounted into ai-box

- Date: 2026-10-28 · Status: Accepted

## Context
The user already runs Claude Code and Codex in ai-box containers with persistent logins,
remote control, cron, agent-orchestrator and create-report. The knowledge system has to be
usable from those sessions, survive container recreation and not duplicate that setup.

## Problem
Where does kinwing live and how does it reach the agents?

## Alternatives
1. **Extend ai-box itself** (code in `context/skills`, services in its compose). Simple to wire,
   but couples a large application to an infrastructure repo the user maintains separately.
2. **A separate agent container for knowledge work.** Needs its own Claude/Codex logins and
   remote control: exactly the duplication the brief rules out.
3. **An optional profile in ai-box.** Same coupling as 1.
4. **A companion repo, mounted into the existing boxes** (skills linked in, a shared
   knowledge folder mounted at `/knowledge`) plus a small reader container.

## Decision
Option 4. `integrations/ai-box/install.sh` adds two symlinks under `context/skills/` (pointing
to `/opt/kinwing/skills/*`, a path that exists inside the boxes) and a generated
`docker-compose.override.yml`. The override mounts the knowledge folder and a read-only
kinwing checkout into `claude`, `codex` and `box`, sets `KW_HOME`, and adds `kinwing-reader`.

## Rationale
- No logins, remote control or schedulers are duplicated. Agents keep working where they are.
- ai-box's entrypoint already links any `context/skills/<name>/SKILL.md` for both agents. A
  symlink whose target exists only inside the container is enough (verified in
  `tests/test_aibox_integration.py`).
- Compose loads `docker-compose.override.yml` automatically, so `./box` needs no change.
- kinwing can be versioned, tested and published on its own.

## Consequences
- Two untracked files in the ai-box checkout (the links and the override); install.sh refuses
  to overwrite an override it didn't write.
- The codex-only image has no python3; a one-line patch (`--codex-python`) is needed for it.
- kinwing updates arrive with `git pull` in the kinwing checkout, with no copying.

## Reversibility
High. `install.sh --uninstall` removes the links and the override; the knowledge folder is
plain files and stays.
