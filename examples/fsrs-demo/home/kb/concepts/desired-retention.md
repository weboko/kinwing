---
id: desired-retention
type: concept
title: Desired retention
aliases: []
topics:
  - fsrs
perspective: practice
summary: "The recall probability you want when a card comes due — the one setting to tune; workload rises steeply toward 100%."
prerequisites:
  - forgetting-curve
related: []
claims: []
sources: []
created: "2026-10-28T02:14:32Z"
updated: "2026-10-28T02:14:32Z"
run: run-20261028-2unq
---

## Explanation

Desired retention is the probability of recall you want at the moment a card comes due. FSRS turns it into an interval by solving its [[forgetting-curve]] for the time at which retrievability reaches that value.

It is the one setting users are meant to change. Higher retention means shorter intervals and more reviews; the workload climbs steeply as you approach 100%. Lower retention saves time but you forget more cards. The Anki manual's default is 90%.

## Prompts

- **apply**: You're short on time this month. What would you change, and what do you give up?
