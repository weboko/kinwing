# Modern spaced-repetition scheduling (FSRS)

FSRS replaces SM-2's single "ease" number with a small model of memory for each card — [[retrievability]], [[stability]] and [[difficulty]] — fitted to your own review history, and it predicts recall far better than SM-2 does; whether that saves you reviews in practice is shown so far only by simulation.

What matters most:

- **The model.** Recall probability decays along a power-law [[forgetting-curve]] (its steepness became trainable per user in FSRS-6); stability is "days until recall drops to 90%". A successful review multiplies stability by a factor that shrinks for hard cards and already-stable memories and grows when the review came late. See [[stability-increase]].
- **The training.** Maximum likelihood (log loss) with backpropagation through time over each card's history ([[parameter-optimisation]]); defaults fitted on ~10k users are used below a few hundred reviews.
- **The control.** You set [[desired-retention]]; workload rises steeply toward 100%. Grades must be honest: Hard counts as a success ([[grading]]).
- **The evidence.** On the developers' public benchmark (~10k Anki users), FSRS-6 out-predicts half-life regression and a constant baseline, and — in the last version that still listed it (August 2025) — Anki's SM-2 by a wide margin (log loss 0.346 vs 0.616). Anki's SM-2 even lost to the constant baseline. See [[benchmark-metrics]] and [[sm2]].

**Caveats that matter:** SM-2 doesn't predict recall natively, so its benchmark probabilities were constructed; all performance evidence comes from the FSRS developers (public, reproducible, not independent); the SM-17 comparison covers 19 users; and rankings of weaker models flip depending on whether users are weighted by review count.

**Open:** does better prediction mean fewer reviews for real learners? The "20–30% fewer reviews" figure is simulated, and its setup isn't documented in the sources read.
