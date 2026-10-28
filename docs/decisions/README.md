# Architecture decision records

One file per decision: `NNNN-short-title.md` with Context, Problem, Alternatives, Decision,
Rationale, Consequences, Reversibility, Date and Status. To change a decision, add a new ADR
with `Supersedes: NNNN` and set the old one's status to `Superseded by NNNN`. Don't edit or
delete the old reasoning.

| # | Decision | Status |
|---|---|---|
| [0001](0001-companion-repo-mounted-into-ai-box.md) | A companion repo, mounted into ai-box, not a fork or a new agent container | Accepted |
| [0002](0002-filesystem-source-of-truth.md) | Markdown + YAML files are the source of truth; no database yet | Accepted |
| [0003](0003-knowledge-home-layout.md) | Separate kb (git), library, learning and runtime folders | Accepted |
| [0004](0004-agent-native-cli-and-skills.md) | Agents are the engine; a stdlib CLI and two skills, no LLM orchestration of our own | Accepted |
| [0005](0005-recurring-research-via-agent-orchestrator.md) | Recurring research through agent-orchestrator; budgets enforced by the CLI | Accepted |
| [0006](0006-concurrency.md) | flock plus one orchestrator workdir for safe concurrent writes | Accepted |
| [0007](0007-claims-and-provenance.md) | Claims backed by verified quotes; revise and supersede, never overwrite | Accepted |
| [0008](0008-reader-stdlib-web-app.md) | The reader is a stdlib HTTP server and a vanilla-JS app in its own container | Accepted |
| [0009](0009-learning-state-model.md) | Learning state: observed vs self-reported vs inferred; FSRS deferred | Accepted |
| [0010](0010-obsidian-export.md) | One-way Obsidian export, two note styles, never overwrite user edits | Accepted |
| [0011](0011-create-report-integration.md) | create-report integration through a generated brief and a privacy guard | Accepted |
| [0012](0012-two-skills.md) | Two skills (knowledge-research, knowledge-learn) sharing one CLI | Accepted |
| [0013](0013-stdlib-python-with-builtin-yaml.md) | Stdlib-only Python with a built-in YAML subset | Accepted |
