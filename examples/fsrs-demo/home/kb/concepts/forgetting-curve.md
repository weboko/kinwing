---
id: forgetting-curve
type: concept
title: The power-law forgetting curve
aliases: []
topics:
  - fsrs
perspective: memory-model
summary: "Recall odds drop fast before the stability point and flatly after it; FSRS-6 learns the curve's shape per user."
prerequisites:
  - retrievability
  - stability
related: []
claims: []
sources: []
created: "2026-10-28T02:14:32Z"
updated: "2026-10-28T02:14:32Z"
run: run-20261028-2unq
---

## Explanation

FSRS assumes forgetting follows a **power curve**, not an exponential: retrievability drops quickly before the stability point and then flattens. In formula form (FSRS-4.5 onward), R(t, S) = (1 + factor · t/S)^(−decay), with the factor chosen so that R = 90% exactly when t = S.

A power curve is what you get when you average many exponential curves with different speeds — a reasonable model for a card whose "true" forgetting rate is uncertain. In FSRS-6 the decay itself became a trainable parameter, so the curve's flatness can differ from person to person.

## Prompts

- **critique**: Why might a power curve fit real review data better than an exponential one?
