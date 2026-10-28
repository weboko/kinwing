---
id: parameter-optimisation
type: concept
title: Fitting parameters to your review log
aliases: []
topics:
  - fsrs
perspective: training
summary: The optimiser fits FSRS's parameters to your history by maximum likelihood (minimising log loss) with backpropagation through time.
prerequisites:
  - forgetting-curve
  - stability-increase
related: []
claims: []
sources: []
created: "2026-10-28T02:14:32Z"
updated: "2026-10-28T02:14:32Z"
run: run-20261028-2unq
---

## Explanation

Your review log is a list of (card, date, grade) events — it never records stability or difficulty, which are hidden quantities. The optimiser treats FSRS as a model that turns each card's history of grades and intervals into a predicted recall probability for the next review, and compares that prediction with what actually happened (recalled = Good/Hard/Easy, forgot = Again).

It adjusts the parameters to maximise the likelihood of your actual outcomes (equivalently, minimise log loss), using backpropagation through time because each prediction depends on the whole sequence of earlier reviews. With too few reviews (under a few hundred) there isn't enough signal, so FSRS falls back to default parameters fitted on roughly 10k users.

## Prompts

- **explain**: Stability never appears in the review log. How can the optimiser estimate it anyway?
