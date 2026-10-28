---
id: dsr-model
type: concept
title: The DSR memory model
aliases: []
topics:
  - fsrs
perspective: memory-model
summary: "FSRS tracks each card with three numbers — retrievability, stability, difficulty — instead of SM-2's single ease factor."
prerequisites: []
related:
  - id: sm2
    rel: contrasts
claims: []
sources: []
created: "2026-10-28T02:14:32Z"
updated: "2026-10-28T02:14:32Z"
run: run-20261028-2unq
---

## Explanation

SM-2 keeps one number per card (an "ease" factor) and multiplies the last interval by it. FSRS instead keeps a small **memory state** per card, borrowed from the three-component model of memory (MaiMemo's DHP model, a variant of the DSR model):

- [[retrievability]] — how likely you are to recall the card *right now*. It falls every day you don't review.
- [[stability]] — how long the memory lasts: the number of days until retrievability drops to 90%.
- [[difficulty]] — how hard it is to make this card's memory more stable.

Only retrievability moves on its own (with time). Stability and difficulty change only when you review the card, using the grade you pressed. Scheduling then becomes a question you can state precisely: *when will retrievability fall to the retention I asked for?*

## Details

The state is per card, but the formulas that update it are shared by all your cards and controlled by the FSRS parameters (21 in FSRS-6), which are fitted to your own review history ([[parameter-optimisation]]). FSRS-6 also uses same-day reviews; older versions used only the first review of each day.

## Prompts

- **explain**: In your own words, why does FSRS need three variables where SM-2 had one?
- **compare**: What can FSRS answer about a card that SM-2 cannot?
