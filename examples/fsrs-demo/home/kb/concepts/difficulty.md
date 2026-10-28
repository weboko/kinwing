---
id: difficulty
type: concept
title: Difficulty
aliases: []
topics:
  - fsrs
perspective: memory-model
summary: "How hard it is to raise a card's stability — not how hard it felt."
prerequisites:
  - dsr-model
related: []
claims: []
sources: []
created: "2026-10-28T02:14:32Z"
updated: "2026-10-28T02:14:32Z"
run: run-20261028-2unq
---

## Explanation

Difficulty (D, from 1 to 10) is not how hard the card *felt*; it is how hard it is to *raise its stability*. High-difficulty cards gain less stability from each successful review, so their intervals grow more slowly.

D starts from your first grade and moves with each later grade. Since FSRS v4 it also drifts back toward a default value ("mean reversion"), which keeps cards from being stuck forever with tiny intervals — the "ease hell" SM-2 users know.

## Prompts

- **apply**: Two cards both have S = 20 days; one has D = 2, the other D = 9. Both are answered Good today. What happens to each?
