# 0009 — Learning state: observed, self-reported, inferred; FSRS deferred

- Date: 2026-10-28 · Status: Accepted

## Context
The system must never assume the user knows something because an agent researched it or a
page was opened. It should still give useful "what next" suggestions and gentle revisiting.
The knowledge-assimilation report could not be read (DISCOVERY §1), so this rests on the
brief and the references.

## Alternatives
1. Flashcards with FSRS scheduling. Precise for memorisation, but it needs well-formed recall
   items, and the brief warns against reducing learning to quizzes.
2. Knowledge tracing (BKT/IRT-style mastery probabilities). Opaque, needs graded data, and
   invents precision.
3. **A transparent record** of observed behaviour and self-reports, with rule-based
   inferences that state their basis, generative prompts instead of quizzes, and expanding
   "worth revisiting" dates.

## Decision
Option 3. Per concept: `observed` (views, time, furthest depth, progress, last paragraph,
completion, answers), `self_report` (new/heard/familiar/known/confused), `interest`,
`revisit` (1, 3, 7, 21, 60, 150 days; confusion resets to 1 day; "known" removes it).
Inferred status is computed on read and shows its basis: not encountered → started → read
→ practised (wrote an answer) → shows understanding (an answer reviewed "sound" by an agent);
"needs another look" on confusion or a reviewed misconception; "self-reported known".
There is never a mastered state. Recommendations combine interest, unmet prerequisites,
confusion, unfinished reading, due revisits, research updates since last reading, the topic's
learning priorities and the user's known concepts. Each suggestion lists its reasons.

SuperMemo ideas kept: a priority queue of what to read next, reading in small slices
(glance/read/deep, short sessions), resuming where you stopped, extracts as highlights,
expanding intervals for revisiting. Rejected for now: cloze items and forced item review.

## Consequences
- "Shows understanding" needs the user to write and an agent to review. That is deliberate.
- No memory model of the user. FSRS proper can be added for an opt-in flashcard layer
  built from highlights (ROADMAP).

## Reversibility
High. The event log (`events.jsonl`) keeps the raw observations a future model would need.
