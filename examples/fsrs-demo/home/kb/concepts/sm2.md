---
id: sm2
type: concept
title: SM-2, Anki's legacy scheduler
aliases: []
topics:
  - fsrs
perspective: lineage
summary: "One ease factor per card multiplies the interval; no explicit recall probability, nothing fitted to you."
prerequisites: []
related:
  - id: dsr-model
    rel: contrasts
claims: []
sources: []
created: "2026-10-28T02:14:32Z"
updated: "2026-10-28T02:19:01Z"
run: run-20261028-2unq
---

## Explanation

SM-2 is the scheduler Anki used before FSRS (and still offers). Each card has an ease factor; a successful review multiplies the interval by it, with extra options such as graduating interval and easy bonus. It has no explicit model of recall probability, so you can't ask it for "90% retention", and its parameters are not fitted to your history.

## Details

How it fares as a predictor: SM-2 doesn't output recall probabilities, so benchmarks construct them from assumed forgetting curves. Treated that way, Anki's SM-2 predicted recall worse than a constant guess in the August 2025 benchmark, and FSRS-6 was far better — see the claims on the Conclusions tab.

## Prompts
