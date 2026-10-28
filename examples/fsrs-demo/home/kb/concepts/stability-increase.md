---
id: stability-increase
type: concept
title: How a review changes stability
aliases: []
topics:
  - fsrs
perspective: memory-model
summary: After a success, stability grows less for hard cards and already-stable memories, and more when recall odds were low (the spacing effect).
prerequisites:
  - stability
  - difficulty
  - retrievability
related: []
claims: []
sources: []
created: "2026-10-28T02:14:32Z"
updated: "2026-10-28T02:14:32Z"
run: run-20261028-2unq
---

## Explanation

After a successful review, FSRS multiplies stability by a factor called SInc (the analogue of Anki's ease). Three rules shape it:

1. **Harder cards grow less** — higher [[difficulty]] means a smaller SInc.
2. **Stable memories grow less** — the larger S already is, the smaller SInc ("saturation").
3. **Reviews at lower recall odds grow more** — the lower [[retrievability]] was at review time, the larger SInc. This is the spacing effect, built into the formula.

Rule 3 is also why FSRS handles overdue cards better than SM-2: a late but successful review raises stability more, but only up to a limit set by your parameters, instead of growing without bound. A failed review ("Again") uses a separate formula that resets stability to a much smaller value.

## Prompts

- **predict**: You review a card when its retrievability is 95% versus 70%. Which review raises stability more, and why?
