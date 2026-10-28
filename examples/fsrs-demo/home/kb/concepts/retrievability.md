---
id: retrievability
type: concept
title: Retrievability
aliases: []
topics:
  - fsrs
perspective: memory-model
summary: "The probability you can recall a card right now; it falls every day without review."
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

Retrievability (R) is the probability that you can recall the card at a given moment. It is 100% just after a successful review and decays as days pass. *How fast* it decays is set by the card's [[stability]], and the shape of the decay is FSRS's [[forgetting-curve]].

R is the only part of the memory state that changes daily, which is why a card can be "due" without anything having happened to it: its predicted R has crossed your [[desired-retention]].

## Prompts

- **predict**: A card was reviewed yesterday and another a year ago, both with S = 30 days. Which has higher retrievability today, and why?
