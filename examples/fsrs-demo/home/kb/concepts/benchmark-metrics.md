---
id: benchmark-metrics
type: concept
title: How schedulers are compared
aliases: []
topics:
  - fsrs
perspective: evidence
summary: "Log loss and RMSE(bins) test calibration, AUC tests discrimination; beating the constant AVG baseline is the minimum."
prerequisites: []
related:
  - id: parameter-optimisation
    rel: related
claims: []
sources: []
created: "2026-10-28T02:14:32Z"
updated: "2026-10-28T02:24:22Z"
run: run-20261028-2unq
---

## Explanation

A scheduler is only as good as its predictions of recall. The open-spaced-repetition benchmark replays real Anki histories and scores each algorithm's predicted recall probability against what happened, training on older reviews and testing on newer ones.

- **Log loss** and **RMSE (bins)** measure *calibration*: when the model says 80%, do you recall about 80% of the time? Lower is better.
- **AUC** measures *discrimination*: does it rank the cards you'll forget below the ones you'll remember? Higher is better.
- **AVG**, which always predicts your average retention, is the baseline: an algorithm that can't beat it predicts nothing useful.

## Alternative explanation

Think of it as "how far off are the percentages?" RMSE (bins) groups reviews into similar situations and compares the predicted recall with the recall that actually happened, in probability units. FSRS-6 is off by about 6.5 percentage points on average; always guessing your average retention is off by about 10; Anki's SM-2, as the benchmark adapted it, by about 17. So when FSRS says "90%" for a group of cards, the real figure is usually within a few points, which is what makes scheduling by a target retention work at all. Log-loss gaps look small because log loss is dominated by the many reviews that every model gets roughly right.

## Prompts

- **critique**: Why is a lower log loss not by itself proof that a scheduler saves you reviews?
