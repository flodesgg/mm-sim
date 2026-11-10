---
id: EXP-007
title: "Skew against Avellaneda-Stoikov, head to head on liquidated P&L"
status: approved         # draft | approved | done
approved_by: "Nick"      # approved in chat: "Утверждаю оба"
approved_on: 2026-11-10
scenario: "inventory"
config_hash: "462cf8b0d9ce"
decision: null           # CONFIRMED | REJECTED | INCONCLUSIVE
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

Not run yet.

## Decision

Not run yet.

## What I learned

Not run yet.
