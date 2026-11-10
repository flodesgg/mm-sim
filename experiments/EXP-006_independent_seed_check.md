---
id: EXP-006
title: "Are the closed forms biased? A check on independent seeds"
status: done             # draft | approved | done
approved_by: "Nick"      # approved in chat: "Утверждаю оба"
approved_on: 2026-11-10
scenario: "baseline"
config_hash: "fbe6c4ea5f6c"
decision: "CONFIRMED"    # CONFIRMED | REJECTED
kind: "independent_seed_check"
strategy: "fixed"
grid: {}
seed: 6000
episodes: 4000
settings:
  std_half_spreads: [0.4, 0.7, 0.85, 1.0, 1.25, 1.5]
  informed: {"flow.informed.horizon_steps": 50, "engine.q_max": 200}
  mean_cells: [[20.0, 0.3], [40.0, 0.4], [80.0, 0.5], [120.0, 0.3], [160.0, 0.6], [200.0, 0.4]]
---

# EXP-006 — independent-seed check of the closed forms

Written before the run. It follows up two things that EXP-001 and EXP-002 left open; it does
not rerun them.

## Why this experiment exists

- **EXP-001:** all ten simulated P&L stds were below the variance formula, 5 to 6% below in the
  middle of the grid. It passed its 10% criterion.
- **EXP-002:** all 70 simulated means were above the closed form, by 1.3 to 3.1 standard
  errors. It passed its 4.0 criterion.

In both, every grid point used the same seed, so the points were not independent and a
one-sided pattern could be one fluctuation or a real bias. Neither experiment could tell.

## Hypothesis

Both closed forms are unbiased: the one-sided patterns were single shared fluctuations.

Reasoning, before any run at these seeds:

- The variance formula is a sum of two exact terms (spread capture as a sum of independent
  Bernoulli fills; carried inventory times independent value moves) whose covariance is zero.
  I can find no approximation in it beyond the tick offset. The sample std of this P&L has a
  heavy-tailed sampling error (the inventory part is a product of two random walks), which
  makes 5% deviations at 1000 episodes unremarkable.
- In EXP-002 the excess was already present without informed traders (about 2 standard errors
  at `λ_I = 0`, where EXP-001 had confirmed the formula on another seed), and the zero-mean
  parts of the decomposition were +0.85 in that sample.

If the hypothesis is wrong, this experiment is designed to show it: a common 2% bias in the
std or a common bias of 0.5 in the mean would give a pooled z near 4.

## Predictions

Every cell has its own seed (`6000 + 1000 × cell index`), 4000 episodes each. Predicted
values from `src/mm_sim/analysis/theory.py`:

Part A, std of P&L, noise traders only (`fixed_noise_pnl_std`):

| half-spread | predicted std |
|---|---|
| 0.4 | 13.722 |
| 0.7 | 13.028 |
| 0.85 | 12.623 |
| 1.0 | 12.189 |
| 1.25 | 11.414 |
| 1.5 | 10.593 |

Part B, mean P&L with informed flow, horizon 50 steps, `q_max = 200`
(`fixed_mean_pnl_with_informed`):

| λ_I | half-spread | predicted mean |
|---|---|---|
| 20 | 0.3 | 37.61 |
| 40 | 0.4 | 40.33 |
| 80 | 0.5 | 36.73 |
| 120 | 0.3 | 7.32 |
| 160 | 0.6 | 24.54 |
| 200 | 0.4 | -3.77 |

## Setup

- Reference engine, strategy `fixed`, 12 independent cells × 4000 episodes of 200 steps.
- Standard error of a std: from a bootstrap over episodes (2000 resamples). Standard error of
  a mean: std / √n.
- Seeds used while building this analysis and not used here: 50 (tests, 60 episodes).

## Numbers that confirm or reject

Implemented in `src/mm_sim/analysis/exp_formula_check.py::verdict`. With
`z = (simulated − predicted) / standard error`:

- **A1:** `|z| ≤ 3` in each of the six std cells.
- **A2:** pooled `|z| ≤ 3` for the std, where pooled z = mean z × √6. With independent cells
  this is standard normal if there is no bias; it is the statistic that catches a small bias
  with the same sign everywhere.
- **B1:** `|z| ≤ 3` in each of the six mean cells.
- **B2:** pooled `|z| ≤ 3` for the mean.

Decision rule: **CONFIRMED** (no bias found) if all four hold. **REJECTED** otherwise; then the
failing formula is biased or the code is wrong, and the next step is to find which.
Under the hypothesis the chance that some criterion fails is about 3.5%.

## Result

Run once on 2026-11-10: run id `20261110T055459Z-fb6728`, git commit `f4305a32555a` (clean),
config hash `fbe6c4ea5f6c`, 4000 episodes per cell, seeds 6000 to 17000. Numbers from
`reports/experiments/EXP-006/cells.csv`; report: `reports/experiments/EXP-006/report.md`.

Part A, std of P&L (noise traders only):

| half-spread | seed | simulated std [95% CI] | predicted | ratio | z |
|---|---|---|---|---|---|
| 0.4 | 6000 | 14.020 [13.459, 14.580] | 13.722 | 1.022 | 1.04 |
| 0.7 | 7000 | 12.891 [12.484, 13.319] | 13.028 | 0.989 | -0.64 |
| 0.85 | 8000 | 12.788 [12.412, 13.169] | 12.623 | 1.013 | 0.86 |
| 1.0 | 9000 | 12.092 [11.727, 12.463] | 12.189 | 0.992 | -0.51 |
| 1.25 | 10000 | 11.306 [10.987, 11.618] | 11.414 | 0.990 | -0.67 |
| 1.5 | 11000 | 10.536 [10.263, 10.807] | 10.593 | 0.995 | -0.41 |

Mean ratio 1.000; pooled z −0.14.

Part B, mean P&L with informed flow:

| λ_I | half-spread | seed | simulated mean [95% CI] | predicted | z |
|---|---|---|---|---|---|
| 20 | 0.3 | 12000 | 37.50 [37.02, 37.97] | 37.61 | -0.45 |
| 40 | 0.4 | 13000 | 39.97 [39.41, 40.54] | 40.33 | -1.24 |
| 80 | 0.5 | 14000 | 36.50 [35.63, 37.36] | 36.73 | -0.53 |
| 120 | 0.3 | 15000 | 7.02 [5.82, 8.21] | 7.32 | -0.50 |
| 160 | 0.6 | 16000 | 24.99 [23.43, 26.56] | 24.54 | 0.57 |
| 200 | 0.4 | 17000 | -4.41 [-6.38, -2.45] | -3.77 | -0.65 |

Pooled z −1.14. Share of steps at the inventory limit: 0 in every cell.

- A1 PASS: largest `|z|` for the std is 1.04.
- A2 PASS: pooled z for the std is −0.14.
- B1 PASS: largest `|z|` for the mean is 1.24.
- B2 PASS: pooled z for the mean is −1.14.

## Decision

**CONFIRMED.** No bias found in either closed form.

What this settles, and what it does not:

- The one-sided patterns in EXP-001 (every std below the formula) and EXP-002 (every mean
  above theory) did not reappear on independent seeds. Four of six std ratios are below 1 and
  two above; the mean ratio is 1.000. Five of six means are below theory this time, the
  opposite side from EXP-002. The patterns there were shared-seed fluctuations.
- "No bias found" has a resolution. With these standard errors (about 1.6 to 2% for a std,
  0.24 to 1.0 for a mean), a common std bias of 2% or more, or a common mean bias of about
  0.5 or more, would very likely have been caught by the pooled statistic. A smaller bias is
  not excluded.
- Only the twelve cells listed were tested.

## What I learned

- Grid points that share a seed move together. Ten ratios below 1, or seventy z-scores above
  0, are then one observation, and reading them as a trend is a mistake. The cure is cheap:
  independent seeds for the question "is there a bias", common seeds for the question "which
  of two strategies is better".
- The sample std of this P&L is noisy: even at 4000 episodes its 95% CI is about ±4%. The 5%
  deviations at 1000 episodes in EXP-001 were inside the noise.
- A pooled statistic across independent cells is far more sensitive to a small common bias
  than any single cell.
