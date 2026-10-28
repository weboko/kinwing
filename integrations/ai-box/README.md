# kinwing in ai-box

kinwing is a companion to [weboko/ai-box](https://github.com/weboko/ai-box): it adds two
skills and a reader service, and reuses everything ai-box already has (Claude/Codex logins,
remote control, cron, agent-orchestrator, create-report). Nothing of ai-box is duplicated.

```
host
├── ai-box/                      your checkout (unchanged except what install.sh adds)
│   ├── context/skills/knowledge-research -> /opt/kinwing/skills/knowledge-research   (symlink)
│   ├── context/skills/knowledge-learn    -> /opt/kinwing/skills/knowledge-learn      (symlink)
│   └── docker-compose.override.yml       (generated; Compose loads it automatically)
├── kinwing/                     this repo, mounted read-only at /opt/kinwing in every box
└── knowledge/                   the knowledge home, mounted at /knowledge (KW_HOME)

containers: claude / codex / box  ── run the agents, use the skills, write /knowledge
            kinwing-reader        ── the reader; only /knowledge mounted; 127.0.0.1:8765
```

## Install

```bash
git clone https://github.com/weboko/kinwing.git          # next to ai-box
kinwing/integrations/ai-box/install.sh ai-box --apply-patches
cd ai-box
./box build kinwing-reader
./box up -d --force-recreate box kinwing-reader            # or claude / codex
```

Options: `--knowledge DIR` (default: `knowledge/` next to ai-box), `--export DIR` (a folder for
Obsidian exports, mounted at `/exports`), `--port N` (reader port, default 8765),
`--apply-patches` (agent-orchestrator `max_duration`, see below), `--codex-python` (adds
`python3` to `Dockerfile.codex`; then rebuild: `./box up -d --build --force-recreate codex`),
`--uninstall`.

Check: `./box exec box /opt/box-context/skills/knowledge-research/bin/kw status`.
The skills show up in new sessions after the recreate (entrypoint.sh links them).

## What the override does

For `claude`, `codex` and `box`: mounts the knowledge folder at `/knowledge` and kinwing at
`/opt/kinwing:ro`, and sets `KW_HOME=/knowledge`. It adds `kinwing-reader` (the kinwing image:
Python and the reader, no agent, no credentials, no Docker socket; read-only root filesystem,
all capabilities dropped; port on the host's loopback only).

If you already have a `docker-compose.override.yml`, install.sh refuses to touch it; copy the
blocks it would generate (run it against a scratch copy of ai-box to see them).

## Concurrency

- All `kw` writes take an `flock` on `/knowledge/runtime/kb.lock`. The folder is the same
  bind mount in every container, so the lock holds across containers (tested with 24
  concurrent writers in two containers).
- Every scheduled research task uses the kb folder as its agent-orchestrator workdir, and
  agent-orchestrator runs one task per workdir at a time. So scheduled research never runs
  twice at once; a firing that collides is logged in `runs/cron.<slug>.log` and the next
  firing catches up.
- Interactive sessions can still write while a scheduled run works; the run's commit then
  includes those changes. Records are separate files, so nothing is lost.

## Patches (optional, reviewed in `patches/`)

- `0001-agent-orchestrator-max-duration.patch`: an optional `max_duration: "45m"` key in task
  specs, implemented with `timeout` around the agent. Without it, kinwing's per-run budget
  still refuses new sources after the deadline, but nothing stops a run that keeps thinking.
  `kw schedule add … --max-duration 45m` writes the key; an unpatched orchestrator ignores it.
- `0002-codex-image-python3.patch`: `python3` in the codex-only image, which has none.
  Not needed for `claude` or `box`.

## Security notes

- Agents run with permissions bypassed (ai-box design). Anything mounted into a box is
  readable and writable by an agent that has just read a hostile web page. Only the
  knowledge folder and a read-only kinwing checkout are added.
- The reader is private: loopback port, Host-header check, custom-header requirement on
  writes, strict CSP, optional `KW_READER_TOKEN` (put it in ai-box's `.env`).
- `~/www` (public through the tunnel) is never written by kinwing. Reports reach it only
  through create-report's `publish.sh`, when asked, after `kw report guard`.
