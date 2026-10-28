<!-- create-report brief drafted by kinwing from the fsrs dossier on 2026-10-28. Private, never published. It contains no personal learning data. Edit freely before rendering. -->
# Modern spaced-repetition scheduling (FSRS)
Subtitle / dek: How the FSRS scheduler models memory, how it is fitted, and what the published benchmarks do and don't show against SM-2.
Kicker: Research dossier
As of: 2026-10-28

## TL;DR
L0: FSRS replaces SM-2's single "ease" number with a small model of memory for each card — retrievability, stability and difficulty — fitted to your own review history, and it predicts recall far better than SM-2 does; whether that saves you reviews in practice is shown so far only by simulation.
L1: What matters most: **The model.** Recall probability decays along a power-law forgetting-curve (its steepness became trainable per user in FSRS-6); stability is "days until recall drops to 90%". A successful review multiplies stability by a factor that shrinks for hard cards and already-stable memories and grows when the review came late. See stability-increase. **The training.** Maximum likelihood (log loss) with backpropagation through time over each card's history (parameter-optimisation); defaults fitted on ~10k users are used below a few hundred reviews. **The control.** You set desired-retention; workload rises steeply toward 100%. Grades must be honest: Hard counts as a success (grading). **The evidence.** On the developers' public benchmark (~10k Anki users), FSRS-6 out-predicts half-life regression and a constant baseline, and — in the last version that still listed it (August 2

## Findings
1. **FSRS parameters are fitted to the user's own review log by maximum likelihood (minimising log loss on recall outcomes) with backpropagation through time; stability and difficulty are latent, never observed.** Strength: strong (finding). {S:src-awesome-fsrs-wiki-the-39f6}
2. **Desired retention is the user's main control: higher retention gives shorter intervals and more reviews, and the workload rises steeply as it approaches 100%.** Strength: strong (finding). {S:src-deck-options-0397}
3. **FSRS describes each card with three variables: retrievability (probability of recall now), stability (days until retrievability falls to 90%) and difficulty (how hard it is to raise stability).** Strength: strong (finding). {S:src-awesome-fsrs-wiki-abc-of-103e}
4. **FSRS uses a power-law forgetting curve (steep before the stability point, flat after it), and since FSRS-6 its decay is a trainable per-user parameter.** Strength: strong (finding). {S:src-awesome-fsrs-wiki-the-4c03}
5. **After a successful review, stability grows less for difficult cards and for already-stable memories, and grows more when retrievability was low at review time (the spacing effect).** Strength: strong (finding). {S:src-awesome-fsrs-wiki-the-4c03}
6. **On the open-spaced-repetition benchmark (about 10,000 Anki users, tested on later reviews), FSRS-6 predicts recall better than half-life regression and the constant-average baseline: log loss 0.346 vs 0.469 (HLR) and 0.395 (AVG).** Strength: strong (finding). {S:src-srs-benchmark-8eec}
7. **FSRS grew out of MaiMemo's DHP memory model and the SSP-MMC scheduling research (KDD 2022, 220 million review logs), which used Duolingo's half-life regression as a baseline model.** Strength: strong (finding). {S:src-awesome-fsrs-wiki-the-4c03} {S:src-ssp-mmc-5d10} {S:src-half-life-regression-68b9}
8. **On the benchmark's last version that included SM-2 (August 2025, ~10k Anki users), FSRS-6 predicted recall far better than Anki's SM-2 — log loss 0.346 vs 0.616 per user (0.321 vs 0.490 weighted by reviews) — and Anki's SM-2 did worse than the constant-average baseline (0.395); FSRS-6 with default parameters (0.366) also beat it.** Strength: moderate (finding). {S:src-srs-benchmark-readme-at-f371} {S:src-awesome-fsrs-wiki-abc-of-103e} Uncertainty: SM-2 doesn't predict recall natively; the benchmark built its probabilities from assumed forgetting curves, so this measures prediction calibration, not review workload. Same organisation as FSRS; SM-2 rows were removed from the README in Aug 2025.
9. **FSRS's performance evidence comes from the same organisation that develops FSRS; the data and scripts are public, so it is reproducible but not independent.** Strength: moderate (interpretation). {S:src-srs-benchmark-8eec} {S:src-fsrs-vs-sm-17-3cec} {I}
10. **FSRS treats Hard as a successful recall, so pressing Hard after forgetting inflates future intervals.** Strength: moderate (finding). {S:src-deck-options-0397}
11. **The two rankings differ because weighting by reviews favours users with long histories ('best case' performance); trainable SM-2 benefits more from plenty of data than HLR does — so 'which is better' depends on how much history a learner has.** Strength: moderate (interpretation). {S:src-srs-benchmark-readme-at-f371} {I} Uncertainty: An interpretation of two tables; per-user data would settle it.
12. **For overdue reviews, FSRS's gain in stability levels off at an upper limit instead of growing with the delay as in SM-2.** Strength: moderate (finding). {S:src-awesome-fsrs-wiki-the-4c03} Uncertainty: One source (the authors' specification); not checked against data here.
13. **Personalised parameters need at least a few hundred reviews; with fewer, FSRS uses default parameters fitted on roughly 10,000 users.** Strength: moderate (finding). {S:src-awesome-fsrs-wiki-abc-of-103e} {S:src-deck-options-0397} Uncertainty: 'A few hundred' is the manual's rule of thumb, not a measured threshold.

## Memory model
### Difficulty
L0: How hard it is to raise a card's stability — not how hard it felt.
L1: Difficulty (D, from 1 to 10) is not how hard the card *felt*; it is how hard it is to *raise its stability*. High-difficulty cards gain less stability from each successful review, so their intervals grow more slowly. D starts from your first grade and moves with each later grade. Since FSRS v4 it also drifts back toward a default value ("mean reversion"), which keeps cards from being stuck forever with tiny intervals — the "ease hell" SM-2 users know.
L3: FSRS describes each card with three variables: retrievability (probability of recall now), stability (days until retrievability falls to 90%) and difficulty (how hard it is to raise stability). {S:src-awesome-fsrs-wiki-abc-of-103e}
### How a review changes stability
L0: After a success, stability grows less for hard cards and already-stable memories, and more when recall odds were low (the spacing effect).
L1: After a successful review, FSRS multiplies stability by a factor called SInc (the analogue of Anki's ease). Three rules shape it: 1. **Harder cards grow less** — higher difficulty means a smaller SInc. 2. **Stable memories grow less** — the larger S already is, the smaller SInc ("saturation"). 3. **Reviews at lower recall odds grow more** — the lower retrievability was at review time, the larger SInc. This is the spacing effect, built into the formula. Rule 3 is also why FSRS handles overdue cards better than SM-2: a late but successful review raises stability more, but only up to a limit set by your parameters, instead of growing without bound. A failed review ("Again") uses a separate formula that resets stability to a much smaller value.
L3: After a successful review, stability grows less for difficult cards and for already-stable memories, and grows more when retrievability was low at review time (the spacing effect). {S:src-awesome-fsrs-wiki-the-4c03}
L3: For overdue reviews, FSRS's gain in stability levels off at an upper limit instead of growing with the delay as in SM-2. {S:src-awesome-fsrs-wiki-the-4c03}
### Memory stability
L0: Days until recall probability falls from 100% to 90%.
L1: Stability (S) is measured in days: it is the time it takes for retrievability to fall from 100% to 90%. A card with S = 365 would still be recalled with 90% probability after a year without reviews. Because "90% after S days" is the definition, an interval equal to S is exactly what FSRS schedules when your desired retention is 90%. Higher desired retention gives intervals shorter than S; lower gives longer ones.
### Retrievability
L0: The probability you can recall a card right now; it falls every day without review.
L1: Retrievability (R) is the probability that you can recall the card at a given moment. It is 100% just after a successful review and decays as days pass. *How fast* it decays is set by the card's stability, and the shape of the decay is FSRS's forgetting-curve. R is the only part of the memory state that changes daily, which is why a card can be "due" without anything having happened to it: its predicted R has crossed your desired-retention.
### The DSR memory model
L0: FSRS tracks each card with three numbers — retrievability, stability, difficulty — instead of SM-2's single ease factor.
L1: SM-2 keeps one number per card (an "ease" factor) and multiplies the last interval by it. FSRS instead keeps a small **memory state** per card, borrowed from the three-component model of memory (MaiMemo's DHP model, a variant of the DSR model): - retrievability — how likely you are to recall the card *right now*. It falls every day you don't review. - stability — how long the memory lasts: the number of days until retrievability drops to 90%. - difficulty — how hard it is to make this card's memory more stable. Only retrievability moves on its own (with time). Stability and difficulty change only when you review the card, using the grade you pressed. Scheduling then becomes a question you can state precisely: *when will retrievability fall to the retention I asked for?*
L2: The state is per card, but the formulas that update it are shared by all your cards and controlled by the FSRS parameters (21 in FSRS-6), which are fitted to your own review history (parameter-optimisation). FSRS-6 also uses same-day reviews; older versions used only the first review of each day.
L3: FSRS grew out of MaiMemo's DHP memory model and the SSP-MMC scheduling research (KDD 2022, 220 million review logs), which used Duolingo's half-life regression as a baseline model. {S:src-awesome-fsrs-wiki-the-4c03} {S:src-ssp-mmc-5d10} {S:src-half-life-regression-68b9}
### The power-law forgetting curve
L0: Recall odds drop fast before the stability point and flatly after it; FSRS-6 learns the curve's shape per user.
L1: FSRS assumes forgetting follows a **power curve**, not an exponential: retrievability drops quickly before the stability point and then flattens. In formula form (FSRS-4.5 onward), R(t, S) = (1 + factor · t/S)^(−decay), with the factor chosen so that R = 90% exactly when t = S. A power curve is what you get when you average many exponential curves with different speeds — a reasonable model for a card whose "true" forgetting rate is uncertain. In FSRS-6 the decay itself became a trainable parameter, so the curve's flatness can differ from person to person.
L3: FSRS uses a power-law forgetting curve (steep before the stability point, flat after it), and since FSRS-6 its decay is a trainable per-user parameter. {S:src-awesome-fsrs-wiki-the-4c03}

## Parameter fitting
### Fitting parameters to your review log
L0: The optimiser fits FSRS's parameters to your history by maximum likelihood (minimising log loss) with backpropagation through time.
L1: Your review log is a list of (card, date, grade) events — it never records stability or difficulty, which are hidden quantities. The optimiser treats FSRS as a model that turns each card's history of grades and intervals into a predicted recall probability for the next review, and compares that prediction with what actually happened (recalled = Good/Hard/Easy, forgot = Again). It adjusts the parameters to maximise the likelihood of your actual outcomes (equivalently, minimise log loss), using backpropagation through time because each prediction depends on the whole sequence of earlier reviews. With too few reviews (under a few hundred) there isn't enough signal, so FSRS falls back to default parameters fitted on roughly 10k users.
L3: FSRS parameters are fitted to the user's own review log by maximum likelihood (minimising log loss on recall outcomes) with backpropagation through time; stability and difficulty are latent, never observed. {S:src-awesome-fsrs-wiki-the-39f6}
L3: Personalised parameters need at least a few hundred reviews; with fewer, FSRS uses default parameters fitted on roughly 10,000 users. {S:src-awesome-fsrs-wiki-abc-of-103e} {S:src-deck-options-0397}

## Evidence and benchmarks
### How schedulers are compared
L0: Log loss and RMSE(bins) test calibration, AUC tests discrimination; beating the constant AVG baseline is the minimum.
L1: A scheduler is only as good as its predictions of recall. The open-spaced-repetition benchmark replays real Anki histories and scores each algorithm's predicted recall probability against what happened, training on older reviews and testing on newer ones. - **Log loss** and **RMSE (bins)** measure *calibration*: when the model says 80%, do you recall about 80% of the time? Lower is better. - **AUC** measures *discrimination*: does it rank the cards you'll forget below the ones you'll remember? Higher is better. - **AVG**, which always predicts your average retention, is the baseline: an algorithm that can't beat it predicts nothing useful.
L3: On the benchmark's last version that included SM-2 (August 2025, ~10k Anki users), FSRS-6 predicted recall far better than Anki's SM-2 — log loss 0.346 vs 0.616 per user (0.321 vs 0.490 weighted by reviews) — and Anki's SM-2 did worse than the constant-average baseline (0.395); FSRS-6 with default parameters (0.366) also beat it. {S:src-srs-benchmark-readme-at-f371} {S:src-awesome-fsrs-wiki-abc-of-103e}
L3: FSRS's performance evidence comes from the same organisation that develops FSRS; the data and scripts are public, so it is reproducible but not independent. {S:src-srs-benchmark-8eec} {S:src-fsrs-vs-sm-17-3cec} {I}
L3: In the FSRS author's comparison on 19 SuperMemo users, FSRS-6 had lower prediction error than SuperMemo's SM-17 (average universal metric 0.029 vs 0.044). {S:src-fsrs-vs-sm-17-3cec}
L3: The two rankings differ because weighting by reviews favours users with long histories ('best case' performance); trainable SM-2 benefits more from plenty of data than HLR does — so 'which is better' depends on how much history a learner has. {S:src-srs-benchmark-readme-at-f371} {I}
L3: Counting each user equally, half-life regression predicts recall better than trainable Anki-SM-2 (log loss 0.469 vs 0.513). {S:src-srs-benchmark-readme-at-f371}
L3: On the open-spaced-repetition benchmark (about 10,000 Anki users, tested on later reviews), FSRS-6 predicts recall better than half-life regression and the constant-average baseline: log loss 0.346 vs 0.469 (HLR) and 0.395 (AVG). {S:src-srs-benchmark-8eec}
L3: Weighted by number of reviews, trainable Anki-SM-2 predicts recall slightly better than half-life regression (log loss 0.407 vs 0.415). {S:src-srs-benchmark-readme-at-f371}

## Scheduling in practice
### Desired retention
L0: The recall probability you want when a card comes due — the one setting to tune; workload rises steeply toward 100%.
L1: Desired retention is the probability of recall you want at the moment a card comes due. FSRS turns it into an interval by solving its forgetting-curve for the time at which retrievability reaches that value. It is the one setting users are meant to change. Higher retention means shorter intervals and more reviews; the workload climbs steeply as you approach 100%. Lower retention saves time but you forget more cards. The Anki manual's default is 90%.
L3: Desired retention is the user's main control: higher retention gives shorter intervals and more reviews, and the workload rises steeply as it approaches 100%. {S:src-deck-options-0397}
### What your grades mean to FSRS
L0: Again means forgot; Hard means recalled. Using Hard for a failure inflates intervals.
L1: FSRS learns from your grades, so it trusts their meaning: **Again** = forgot, **Hard/Good/Easy** = recalled. Pressing Hard when you actually forgot teaches the model that you remembered, which inflates stability and makes later intervals unreasonably long. It is the one habit the Anki manual says FSRS cannot adapt to.
L3: FSRS treats Hard as a successful recall, so pressing Hard after forgetting inflates future intervals. {S:src-deck-options-0397}

## Lineage and alternatives
### SM-2, Anki's legacy scheduler
L0: One ease factor per card multiplies the interval; no explicit recall probability, nothing fitted to you.
L1: SM-2 is the scheduler Anki used before FSRS (and still offers). Each card has an ease factor; a successful review multiplies the interval by it, with extra options such as graduating interval and easy bonus. It has no explicit model of recall probability, so you can't ask it for "90% retention", and its parameters are not fitted to your history.
L2: How it fares as a predictor: SM-2 doesn't output recall probabilities, so benchmarks construct them from assumed forgetting curves. Treated that way, Anki's SM-2 predicted recall worse than a constant guess in the August 2025 benchmark, and FSRS-6 was far better — see the claims on the Conclusions tab.

## Disagreements
### A. Counting each user equally, half-life regression predicts recall better than…
Side 1: Counting each user equally, half-life regression predicts recall better than trainable Anki-SM-2 (log loss 0.469 vs 0.513). {S:src-srs-benchmark-readme-at-f371}   Side 2: Weighted by number of reviews, trainable Anki-SM-2 predicts recall slightly better than half-life regression (log loss 0.407 vs 0.415). {S:src-srs-benchmark-readme-at-f371}
Conclusion: both tables are right; weighting by reviews shows best-case performance for users with long histories, so the ranking of these two weaker models depends on how much history a learner has. Neither matters next to FSRS-6, which leads in both. {I}

## Risks / Next steps
- Uncertain: In the FSRS author's comparison on 19 SuperMemo users, FSRS-6 had lower prediction error than SuperMemo's SM-17 (average universal metric 0.029 vs 0.044). {S:src-fsrs-vs-sm-17-3cec}
- Open question: Does FSRS's better recall prediction actually translate into fewer reviews or better retention for real learners (not simulations)?
- Open question: What are the known limitations or failure modes of FSRS and of its evaluation?
- Open question: What does a log-loss difference like 0.346 vs 0.395 mean in practice for a learner's workload or retention?

## Sources
- src-awesome-fsrs-wiki-the-39f6: awesome-fsrs wiki: The mechanism of optimization, https://github.com/open-spaced-repetition/awesome-fsrs/wiki/The-mechanism-of-optimization, accessed 2026-10-28
- src-deck-options-0397: Deck Options, https://github.com/ankitects/anki-manual/blob/main/src/deck-options.md, accessed 2026-10-28
- src-awesome-fsrs-wiki-abc-of-103e: awesome-fsrs wiki: ABC of FSRS, https://github.com/open-spaced-repetition/awesome-fsrs/wiki/ABC-of-FSRS, accessed 2026-10-28
- src-awesome-fsrs-wiki-the-4c03: awesome-fsrs wiki: The Algorithm, https://github.com/open-spaced-repetition/awesome-fsrs/wiki/The-Algorithm, accessed 2026-10-28
- src-srs-benchmark-8eec: SRS Benchmark, https://github.com/open-spaced-repetition/srs-benchmark, accessed 2026-10-28
- src-ssp-mmc-5d10: SSP-MMC, https://github.com/maimemo/SSP-MMC, accessed 2026-10-28
- src-half-life-regression-68b9: Half-Life Regression, https://github.com/duolingo/halflife-regression, accessed 2026-10-28
- src-srs-benchmark-readme-at-f371: SRS Benchmark README at b9ee6cc (before SM-2 rows were removed, 2025-08) (2025-08-21), https://github.com/open-spaced-repetition/srs-benchmark/blob/b9ee6cc3f21780f622ae1605f32703f155e5531a/README.md, accessed 2026-10-28
- src-fsrs-vs-sm-17-3cec: FSRS vs SM-17, https://github.com/open-spaced-repetition/fsrs-vs-sm17, accessed 2026-10-28
