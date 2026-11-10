---
id: EXP-007
title: "Skew against Avellaneda-Stoikov, head to head on liquidated P&L"
status: done             # draft | approved | done
approved_by: "Nick"      # approved in chat: "Утверждаю оба"
approved_on: 2026-11-10
scenario: "inventory"
config_hash: "462cf8b0d9ce"
decision: "CONFIRMED"    # CONFIRMED | REJECTED | INCONCLUSIVE
kind: "head_to_head"
strategy: "skew"
grid: {}
seed: 707
episodes: 4000
settings:
  a: {"strategy": "skew", "params": {"half_spread": 0.75, "kappa": 0.2}}
  b: {"strategy": "avellaneda_stoikov", "params": {"gamma": 0.1}}
---

# EXP-007 — skew against Avellaneda–Stoikov

Written before the run. It turns an observation from EXP-003 into a test.

## Why this experiment exists

In EXP-003 the skew points lay above the Avellaneda–Stoikov points on the risk–return
frontier. That was noticed after the run; EXP-003's criteria compared each strategy with
fixed quotes, not with each other. A pattern found by looking at results is a hypothesis, not
a finding, so it is tested here on a new seed.

## Hypothesis

In scenario `inventory` (noise traders only, liquidation cost `0.5 + 0.05·|q|` per lot), a
plain skew with `κ = 0.2` and half-spread 0.75 beats Avellaneda–Stoikov with `γ = 0.1` on
liquidated P&L: higher mean and no more risk. The two quote almost the same average spread
(1.51 and 1.50 in EXP-003), so the comparison is not about the spread.

## Where the prediction comes from

EXP-003, seed 303, 1000 episodes (`reports/experiments/EXP-003/frontier.csv`): skew `κ = 0.2`
had mean liquidated P&L 56.50 and std 6.04; AS `γ = 0.1` had 55.53 and 6.46. That is the only
evidence, it is from one seed, and this pair was picked **because** it looked like a clean win
there. Selection of that kind inflates effects, which is why the test uses a new seed, four
times the episodes, and criteria fixed now.

Possible mechanism (not tested here): AS is derived for mark-to-market wealth without a
liquidation cost. Its inventory shift per lot, `γ·σ²·(T − t)`, is 0.4 at the start of the
episode and zero at the end, so it gives up edge early and stops controlling inventory when
liquidation is near; the skew shifts by a constant 0.2 per lot throughout.

## Setup

- A = `skew` (`half_spread = 0.75`, `κ = 0.2`); B = `avellaneda_stoikov` (`γ = 0.1`).
- Scenario `inventory`, reference engine, 4000 episodes of 200 steps, root seed 707 for both
  (common random numbers; the comparison is paired).
- CIs: paired t-interval for the mean difference; paired bootstrap (2000 resamples) for the
  std ratio and the certainty-equivalent difference.
- Seeds used while building this analysis and not used here: 51 (tests, 80 episodes).

## Numbers that confirm or reject

Implemented in `src/mm_sim/analysis/exp_head_to_head.py::verdict`, on **liquidated** P&L:

- **H1:** mean(A) − mean(B) has a 95% paired CI entirely above 0.
- **H2:** std(A) / std(B) has a 95% bootstrap CI whose upper end is below 1.

Decision rule: **CONFIRMED** if both hold. **REJECTED** if the mean-difference CI is entirely
below 0 (AS earns more) or the std-ratio CI is entirely above 1 (skew is riskier).
**INCONCLUSIVE** otherwise.

Reported without a prediction: the same comparison on **mark-to-market** P&L, which is the
objective AS is derived for, and the certainty-equivalent difference on both measures. If AS
wins there, the conclusion is "AS is better at its own objective and worse once closing the
position costs something"; that would be stated, not hidden.

What a CONFIRMED verdict would and would not mean: it would hold for this one pair of
parameter settings under this liquidation cost. It would not show that skew beats AS in
general; a tuned `γ`, or an AS variant that accounts for the liquidation cost, is not tested.

## Result

Run once on 2026-11-10: run id `20261110T055616Z-ecb1a6`, git commit `3596e05026ef` (clean),
config hash `462cf8b0d9ce`, seed 707, 4000 episodes. Numbers from
`reports/experiments/EXP-007/head_to_head.csv`; report:
`reports/experiments/EXP-007/report.md`.

A = skew (`κ = 0.2`, half-spread 0.75), B = Avellaneda–Stoikov (`γ = 0.1`):

| measure | A: mean [95% CI] | A: std | B: mean [95% CI] | B: std | mean A − B [95% CI] | std A / B [95% CI] | CE A − B [95% CI] |
|---|---|---|---|---|---|---|---|
| liquidated P&L | 56.59 [56.40, 56.77] | 6.05 | 55.60 [55.40, 55.80] | 6.40 | 0.98 [0.89, 1.08] | 0.946 [0.932, 0.961] | 1.22 [1.09, 1.33] |
| mark-to-market P&L | 57.14 [56.96, 57.33] | 6.06 | 57.24 [57.04, 57.44] | 6.33 | -0.10 [-0.19, -0.01] | 0.957 [0.944, 0.971] | 0.07 [-0.04, 0.18] |

Average quoted spread: A 1.510, B 1.502. Std of terminal inventory: A 1.27, B 3.02 lots.
Mean |inventory| during the episode: A 0.93, B 1.06.

- H1 PASS: mean liquidated P&L of skew is 0.98 higher, CI [0.89, 1.08].
- H2 PASS: std ratio 0.946, CI [0.932, 0.961], upper end below 1.

## Decision

**CONFIRMED.** On liquidated P&L, skew `κ = 0.2` earns more than Avellaneda–Stoikov `γ = 0.1`
(by 0.98, about 1.8% of the mean) with a lower std (5.4% lower).

What the verdict does not say, from the row reported without a prediction:

- **On mark-to-market P&L, the objective AS is derived for, AS is not worse.** Its mean is 0.10
  higher (CI [0.01, 0.19]), the skew's std is 4.3% lower, and the certainty-equivalent
  difference is 0.07 with a CI that includes zero ([−0.04, 0.18]). On AS's own objective the
  two are a tie.
- **The whole advantage of the skew is the liquidation cost.** Mark-to-market the means differ
  by −0.10; liquidated by +0.98. AS finishes with a terminal inventory std of 3.02 lots
  against 1.27, although its average inventory during the episode is almost the same (1.06
  against 0.93). That is what the proposed mechanism predicts: AS's inventory shift
  `γ·σ²·(T − t)` fades to zero at the end, so it stops pulling inventory back exactly when the
  position is about to be closed at a cost. The mechanism is consistent with these numbers; it
  was not tested by intervention.
- One parameter pair, chosen because it looked best in EXP-003, under one invented liquidation
  cost. It does not show that skew beats AS in general, and an AS variant that knows about the
  liquidation cost would be the fair opponent.
- The effect is small in absolute terms. It is measured precisely only because the comparison
  is paired.

## What I learned

- "Which strategy is better" depends on the objective. AS is as good as the skew at what it
  optimises (terminal mark-to-market wealth) and worse once terminal inventory has a price,
  because the model it was derived from has no such price.
- A strategy that is optimal in a model inherits the model's blind spots. Here the blind spot
  is visible in one number: terminal inventory.
- Looking only at the liquidated row, I would have concluded "skew beats AS". The
  mark-to-market row changes that to "they tie, until closing the position costs something".
  Reporting the measure the other side was designed for is what kept the conclusion honest.
- EXP-003's observation survived a new seed, with nearly the same numbers (0.97 there, 0.98
  here). It was a real effect of this model, and a narrower one than it looked.
