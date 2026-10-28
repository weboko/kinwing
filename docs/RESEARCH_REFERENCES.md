# Research references

What each reference contributed, and what was adopted, rejected or deferred. Whether a source
was actually read in this session is recorded in DISCOVERY.md §3.

| Reference | Idea | Verdict |
|---|---|---|
| [weboko/ai-box](https://github.com/weboko/ai-box) | Containers as the sandbox, persistent homes, read-only shared skills, cron rebuilt on start, `~/www` publication | **Adopted** as the platform (ADR-0001) |
| ai-box `agent-orchestrator` | Task specs, local/push knowledge modes, one run per workdir, skip-if-alive, reports | **Adopted** for all recurring runs (ADR-0005); added `max_duration` |
| ai-box `create-report` | Brief with L0–L3 depth and evidence tags; templates; check and publish | **Adopted** as the presentation layer (ADR-0011) |
| [STORM](https://github.com/stanford-oval/storm) (Shao et al., NAACL 2024) | Perspective-guided question asking; research before writing | **Adopted**: per-topic perspectives drive the queue and coverage gaps. **Rejected**: simulated expert conversations (a capable agent asks better questions directly) |
| Co-STORM (Jiang et al., EMNLP 2024) | A mind map as shared human–AI conceptual space; a moderator surfacing unused information | **Adopted** in spirit: the concept map with prerequisites and contrasts; orphan-evidence reports. **Deferred**: turn-taking discourse |
| [SuperMemo incremental reading](https://www.super-memory.org/archive/help/read.htm) | Interleaved reading in slices, extracts, priority queue, growing intervals | **Adopted**: priority-ordered suggestions, glance/read/deep slices, resume position, highlights as extracts, expanding revisit dates. **Deferred**: cloze items, forced item review |
| [Elicit Routines](https://elicit.com/blog/introducing-routines-research-that-keeps-working) | Research that keeps running and surfaces only what is new | **Adopted**: monitor mode, `kw changes --since`, notifications reserved for what matters, low-yield detection |
| [MemGPT / Letta](https://github.com/letta-ai/letta); [context repositories](https://www.letta.com/blog/context-repositories/) | Agent memory as editable, versioned files | **Adopted**: the kb is a git-backed context repository the agents read at the start of every run (the brief). **Rejected**: memory paging machinery (the agents manage their own context) |
| [FSRS](https://github.com/open-spaced-repetition) | DSR memory model, per-user fitting, desired retention | **Deferred** for user learning (ADR-0009); it was also the demo topic |
| Generative learning, active recall, Socratic questioning (general learning-science literature; the user's report, unread) | Learners understand more by explaining, predicting and applying | **Adopted**: concept prompts (explain/predict/compare/apply/critique), answers kept verbatim and reviewed by an agent, no quizzes after every section |
| W3C Web Annotation text-quote selector | Anchor highlights by exact text plus prefix | **Adopted** in the reader's highlight anchoring |
