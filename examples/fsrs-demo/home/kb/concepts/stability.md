---
id: stability
type: concept
title: Memory stability
aliases: []
topics:
  - fsrs
perspective: memory-model
summary: "Days until recall probability falls from 100% to 90%."
prerequisites:
  - dsr-model
related:
  - id: retrievability
    rel: contrasts
claims: []
sources: []
created: "2026-10-28T02:14:32Z"
updated: "2026-10-28T02:14:32Z"
run: run-20261028-2unq
---

## Explanation

Stability (S) is measured in days: it is the time it takes for [[retrievability]] to fall from 100% to 90%. A card with S = 365 would still be recalled with 90% probability after a year without reviews.

Because "90% after S days" is the definition, an interval equal to S is exactly what FSRS schedules when your desired retention is 90%. Higher desired retention gives intervals shorter than S; lower gives longer ones.

## Prompts

- **explain**: What does a stability of 10 days mean for when this card will be shown at 90% desired retention?
