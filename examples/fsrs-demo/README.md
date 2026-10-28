# Example: FSRS research (from the 2026-10-28 demonstration)

What three research runs, a reading session and an export produced. See
[docs/DEMO.md](../../docs/DEMO.md) for the story and [transcript.md](transcript.md) for every command.

| Path | What |
|---|---|
| `home/kb/` | the knowledge base: `topics/fsrs/{topic.yaml, overview.md, dossier.md, changes.md}`, `questions/`, `sources/`, `evidence/`, `claims/`, `concepts/`, `runs/` |
| `home/learning/` | the learning state the reader recorded: `state.json`, `events.jsonl`, `highlights/`, `answers/`, `sessions/` |
| `home/exports/obsidian/` | the Obsidian export |
| `home/runtime/notifications.jsonl` | what the runs told the user |
| `report/` | the create-report brief, the request, the rendered `index.html` and `report.json`, check screenshots |
| `shots/` | reader screenshots |

Start with `home/kb/topics/fsrs/dossier.md`.

`library/` (the fetched source texts) is not included: it is third-party content. To browse
this example in the reader with source texts:

```bash
cp -r examples/fsrs-demo/home /tmp/fsrs-home
```

```bash
KW_HOME=/tmp/fsrs-home skills/knowledge-research/bin/kw source refetch --all
```

```bash
KW_HOME=/tmp/fsrs-home skills/knowledge-research/bin/kw serve
```

Paths inside run records were rewritten to `$DEMO` (the demo's working folder).
