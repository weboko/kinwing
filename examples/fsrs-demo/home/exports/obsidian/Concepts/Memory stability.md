---
kw_id: "concept:stability"
kw_type: concept-note
aliases: []
topics:
  - "[[Modern spaced-repetition scheduling (FSRS)]]"
sources:
  - "[[awesome-fsrs wiki ABC of FSRS]]"
related: []
tags:
  - kinwing
  - topic/fsrs
  - kinwing/concept
created: "2026-10-28"
---

# Memory stability

## My thoughts

- On “it is the time it takes for”: So stability is a "90%-life", not a half-life: it is defined where recall odds hit 90%, not 50%.
- My explanation (2026-10-28, prompt: _What does a stability of 10 days mean for when this card will be shown at 90% desired retention?_):
    > At 90% desired retention the card would come back after about 10 days, because S is exactly the time until recall odds fall to 90%.

## AI synthesis

> [!note]- AI-written by kinwing's research agent (2026-10-28) — check the evidence before relying on it
> **In one line:** Days until recall probability falls from 100% to 90%.
>
> Stability (S) is measured in days: it is the time it takes for Retrievability to fall from 100% to 90%. A card with S = 365 would still be recalled with 90% probability after a year without reviews.
>
> Because "90% after S days" is the definition, an interval equal to S is exactly what FSRS schedules when your desired retention is 90%. Higher desired retention gives intervals shorter than S; lower gives longer ones.

## Key evidence

- **Claim (strong finding, AI-synthesized):** FSRS describes each card with three variables: retrievability (probability of recall now), stability (days until retrievability falls to 90%) and difficulty (how hard it is to raise stability).
    - “The time, in days, required for R to decrease from 100% to 90%.” — [[awesome-fsrs wiki ABC of FSRS]] ¶5
    - “The probability that the person can successfully recall a particular piece of information at a given moment.” — [[awesome-fsrs wiki ABC of FSRS]] ¶4
    - “It represents how difficult it is to increase memory stability after a review.” — [[awesome-fsrs wiki ABC of FSRS]] ¶6

## Related

- Retrievability — contrasts
- The DSR memory model — builds on

## Links

- Topics: [[Modern spaced-repetition scheduling (FSRS)]]
