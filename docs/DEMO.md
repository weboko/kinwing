# Demonstration (2026-10-28)

Run the scenario from the brief on a real topic and record what actually happened. All
artifacts are in [`examples/fsrs-demo/`](../examples/fsrs-demo/). Every `kw` command and its
output is in [`transcript.md`](../examples/fsrs-demo/transcript.md).

**Topic:** modern spaced-repetition scheduling (FSRS). It suits this environment because its
primary material is public and on GitHub, which this session could reach.

**Who did what.** The research runs were carried out by Claude Code acting as the research
agent, following the `knowledge-research` skill command by command, in this session.
Launching a separate autonomous agent was blocked by the session's safety policy (see
DISCOVERY §4). Scheduled runs in Step 8 went through ai-box's real agent-orchestrator scripts
with a stand-in agent (`tests/fakes/claude`). The stand-in follows the same protocol (`kw run
begin` … `kw run end`) without an LLM, so those runs add no knowledge. Codex was not available.

| Status legend | |
|---|---|
| ✅ executed and checked | the step ran here, and the outcome was checked |
| 🟡 executed with a substitute | the mechanism ran; one part was replaced (named) |

## Step 1 — create a topic conversationally ✅

The user's request (in the transcript) was turned into
`kw topic new --id fsrs --objective … --familiarity "Has used Anki for years…" --known "spaced repetition basics,forgetting curve" --depth orientation --exclude "flashcard-making advice,Anki UI how-tos" …`,
plus six perspectives derived from the subject (memory model, parameter fitting, evidence,
practice, lineage, limits) and nine seed questions. The three the user cared about most were
marked `origin: user`. Result: [`topic.yaml`](../examples/fsrs-demo/home/kb/topics/fsrs/topic.yaml).

## Step 2 — first research run (orientation) ✅

`kw run begin` selected the three user questions (score 7.5 each, reason shown) and printed
the brief. 5 sources ingested from GitHub (FSRS specification, introduction, optimiser
description, the srs-benchmark README, the Anki manual), plus one deliberate re-add of a known
URL with a tracking parameter → `known (same URL)`. 28 evidence records; **26 verbatim quotes,
all verified against the stored text** (2 labelled observations). 11 concepts with
explanations, prerequisites and prompts. 11 claims. 3 new gap questions.

The key finding for "evidence, not marketing": the current benchmark tables have **no SM-2
row**. "FSRS beats SM-2" therefore rested on the authors' statement and a simulation, and was
recorded as a **weak interpretation**, with the missing row as counter-evidence. A
notification said so. `kw check`: 0 errors.

## Step 3 — continue research; reuse state, revise a conclusion ✅

`kw run begin` (run 2) printed run 1's advice, the 11 known conclusions and the known sources,
and selected the new gap question ("is there a head-to-head comparison?"). The agent found
SM-2 rows in the **git history** of the benchmark: commit `3f0b7b7` (2025-08-22) removed them,
and revision `b9ee6cc` was ingested by pinned URL. Outcome:

- run 1's SM-2 claim was **superseded, not overwritten**. Its file keeps the reason
  ([cl-…3xrx](../examples/fsrs-demo/home/kb/claims/cl-20261028-3xrx.md)), and the new claim
  ([cl-…5csf](../examples/fsrs-demo/home/kb/claims/cl-20261028-5csf.md)) says FSRS-6 predicted
  recall far better (log loss 0.346 vs 0.616 for Anki's SM-2, which even lost to a constant
  guess), with the caveat that SM-2's probabilities were constructed for the benchmark;
- a **genuine conflict** was preserved: trainable Anki-SM-2 vs half-life regression rank in
  opposite order with and without weighting by review count. The result is two contested,
  linked claims plus a reconciling interpretation;
- 4 new sources, 25 evidence records, 6 new and 6 revised claims; dossier §10 shows each change and its reason.

**A system defect surfaced and was fixed**: `kw consolidate --apply-safe` marked two claims
"contested" because they carried caveat-type counter-evidence. They were restored with
recorded reasons (both steps stay visible in the claims' revision history), the rule was
narrowed to explicit contradictions, and a test was added (ADR-0007).

## Step 4 — report through create-report ✅ (published only to a scratch web root)

`new-report.sh "FSRS vs SM-2: what the evidence says" longread` → `kw report brief fsrs --out
…/brief.md` (16 claims, 9 sources, `{S:src-…}` tags) → GAP line resolved, prompt saved →
`site/index.html` written from the longread skeleton with a log-loss chart and a
reconciliation block → **`check.mjs`: ok** (390 px, 1440 px, no-JS; no errors, overflow or
missing citations) → **`kw report guard`: 0 problems** → **`publish.sh`** into a scratch
`WWW_ROOT` (nothing served or public). After the learning session, the guard was run again
(still 0) and on a copy with a planted annotation (caught: `contains annotation h-…`).
Files: [`report/`](../examples/fsrs-demo/report/) with
[check-1440.png](../examples/fsrs-demo/report/check-1440.png) and
[check-1440-evidence.png](../examples/fsrs-demo/report/check-1440-evidence.png).

## Step 5 — learn in the reader ✅

The reader ran in its container (`docker compose up -d reader`, port 127.0.0.1:8765, only the
knowledge folder mounted). [`demo/learn-session.js`](../demo/learn-session.js) drove it in
Chromium the way a user would ([log](../examples/fsrs-demo/learn-session.log)):

| Shown | Screenshot |
|---|---|
| home: notifications, suggestions with reasons, topic progress | [01-home](../examples/fsrs-demo/shots/01-home.png) |
| topic overview (agent narrative, start here, still unknown) | [02-topic-overview](../examples/fsrs-demo/shots/02-topic-overview.png) |
| concept map by prerequisite layers | [03-concept-map](../examples/fsrs-demo/shots/03-concept-map.png) |
| concept at Read depth, highlight with note, answer to a prompt, "Familiar" | [04-concept-highlight](../examples/fsrs-demo/shots/04-concept-highlight.png) |
| "continue where you left off" after leaving a source mid-way | [05-home-continue](../examples/fsrs-demo/shots/05-home-continue.png) |
| resume: "Resumed where you left off (¶86)" | [06-source-resumed](../examples/fsrs-demo/shots/06-source-resumed.png) |
| conclusions → exact evidence → source paragraph | [07-conclusions-evidence](../examples/fsrs-demo/shots/07-conclusions-evidence.png) |
| "My questions" (the user's challenge in the research queue) | [08-my-questions](../examples/fsrs-demo/shots/08-my-questions.png) |
| highlights selected and exported | [09-highlights-export](../examples/fsrs-demo/shots/09-highlights-export.png) |
| a 15-minute session | [10-session](../examples/fsrs-demo/shots/10-session.png) |
| phone width, no sideways scrolling | [11-phone-concept](../examples/fsrs-demo/shots/11-phone-concept.png) |

No page errors. Read back with the CLI afterwards: 2 highlights (one an exact source quote at
¶86, one on AI text, both labelled as such), 1 answer, stability "practised" (opened 5×; read
100%; 1 written answer; said "familiar"), then **"shows understanding"** once the
`knowledge-learn` agent reviewed the answer as sound. Every other concept stayed "not
encountered": opening the topic does not count as knowing it.

**Feedback into research (5b).** The user's "I'm not convinced: log-loss gaps look small" became
question `q-…f9zj` (origin learning). The next `kw run begin` selected it first (score 7.5 with
"origin learning +1.5"). A targeted run 3 answered it: RMSE(bins) is in probability units, so
FSRS-6 is off by ~6.5 percentage points versus ~10 for a constant guess and ~17 for Anki's SM-2.
The run added an "Another way to see it" explanation to the concept and a notification
pointing the user to it.

## Step 6 — export to Obsidian ✅

From the reader's Highlights page: two source notes, one concept note and one topic map in
[`exports/obsidian/`](../examples/fsrs-demo/home/exports/obsidian/). Checked: frontmatter
parses (`kw_id`, `kw_type`, `tags`, `topics`, `sources`, `created`); exact quotes as `>`
blocks with `^h-…` block ids and ¶ locators; the user's words under **My thoughts** / **My
note**; AI text in collapsed callouts labelled AI-written; the concept note's evidence quotes
link to the source notes; kinwing's internal `[[concept-id]]` links rewritten to note names.
Re-export is idempotent, and edits made in Obsidian are protected (tested).

## Step 7 — persistence ✅

Same snapshot before, after `docker compose up -d --force-recreate reader`, and after
`docker compose down` + `up`: topic, 11 concepts, 17 claims, "continue" position (¶),
2 highlights, the reviewed answer, and the 9 export files. Separately, the Docker
integration test recreated an ai-box-style agent container and the reader: the kb, reading
progress and the **crontab block** (rebuilt by ai-box's supervisor) all survived.

## Step 8 — orchestration 🟡 (stand-in agent; cron firing executed from the generated crontab line)

`kw schedule add fsrs --cron "0 9 * * 1,3,5" --max-duration 30m` wrote the orchestrator spec
(`mode: local`, `workdir: …/kb`) and the crontab block (a test crontab file; the Docker test
covers a real crontab). Executing the cron line as cron would:

1. **Limit**: the 4th run in a week was refused by `kw run begin` (exit 12, "weekly budget
   reached: 3/3"). The orchestrator run still finished `done`, with the reason in its report.
2. Budget raised (`kw topic set fsrs budget.max_runs_per_week=6`) → the next firing ran.
   A second firing two seconds later was **skipped**: `SKIP … reason=previous-run-alive`.
3. **Pause**: `kw topic pause fsrs` disabled the schedule (crontab block emptied); a manual
   firing logged `SKIP … reason=stopped`. **Resume** restored it.
4. **Hard stop**: with `--max-duration 3s` (patched orchestrator) a slow agent was killed:
   orchestrator run `failed`, exit `124`. The next `kw run begin` reported "Recovered
   interrupted run(s)" and released its questions.
5. **Integrity afterwards**: `kw check` 0 errors; no duplicate sources; one git commit per
   run in `kb/`; two empty runs in a row produced the "consider pausing" notification.

## Numbers

| | |
|---|---|
| Sources | 9 (docs 4, benchmark/dataset 3, paper companions 2), all fetched by kw from GitHub |
| Evidence | 54 records: 36 verbatim quotes and 15 quoted data rows (all verified against the stored text), 3 observations |
| Claims | 18: current 7 strong, 7 moderate, 1 weak, 2 contested (the linked conflict); 1 superseded |
| Concepts | 11, with prerequisites, relations and 10 prompts |
| Questions | 14: 9 answered, 2 partial, 2 open, 1 blocked (the simulation behind "20–30% fewer reviews" isn't documented in reachable sources) |
| Runs | 3 research runs, 1 stand-in scheduled run, 1 run killed by max_duration (recovered), 1 recovery-check run |

## What this demo did not show

- An autonomous Claude or Codex run under the scheduler (OQ-2, OQ-3).
- Reddit, arXiv or other sites outside GitHub (unreachable here; the ingestion paths are tested
  with local HTTP servers and files).
- Publication to a real public site (deliberately not done).
