---
id: EXP-001
title: "Fixed half-spread against noise flow only: P&L mean and std versus theory"
status: approved         # draft | approved | done
approved_by: "Nick"      # approved in chat: "Утверждаю EXP-001"
approved_on: 2026-11-09
scenario: "baseline"
config_hash: "98f30782c37f"
decision: null           # CONFIRMED | REJECTED | INCONCLUSIVE
kind: "fixed_spread_sweep"
strategy: "fixed"
grid:
  half_spread: [0.1, 0.25, 0.4, 0.55, 0.7, 0.85, 1.0, 1.25, 1.5, 2.0]
seed: 101
episodes: 1000
---

# EXP-001 — fixed half-spread, noise flow only

Written before the run. Nothing in this file comes from a simulation at seed 101: every
number in the prediction table is computed from the formulas in
`src/mm_sim/analysis/theory.py` (derived in `docs/model_notes.md`, section 9).

## Hypothesis

With noise traders only and an inventory limit that does not bind, the fixed-spread market
maker's mean episode P&L follows the closed form below, rising and then falling in the
half-spread `h`: wider quotes earn more per fill but fill less often. Its P&L std comes mostly
from carried inventory and falls as `h` widens.

## Prediction from theory

Per step and per side the market maker earns the distance `δ` with probability
`p(δ) = 1 − exp(−A·exp(−k·δ)·dt)`, so

```
E[P&L]   = N · 2 · E[δ·p(δ)]                     δ = h + U,  U ~ Uniform[0, tick)
Var[P&L] = N·2·d²·p·(1−p) + σ²·dt·2·p·(1−p)·N·(N+1)/2          d = h + tick/2, p = E[p(δ)]
```

`U` is the outward rounding offset. Without a tick this is the build prompt's formula
`N·2·h·(1 − exp(−A·exp(−k·h)·dt))`.

**Where is the optimum?** For `A·dt → 0` the maximum is at `h = 1/k = 0.667`. In the baseline
`A·dt = 0.7` is not small, and the exact maximiser of the closed form is **`h* = 0.744`**
(0.749 without the tick). So the prediction is an optimum near 0.75, not at 0.667.

Baseline: `N = 200, dt = 0.005, σ = 2, A = 140, k = 1.5, tick = 0.01, q_max = 50`.

| h | fill prob. per side | fills per episode | mean P&L | mean P&L, no tick | P&L std | std of terminal inventory |
|---|---|---|---|---|---|---|
| 0.1 | 0.4501 | 180.0 | 18.90 | 18.10 | 14.15 | 9.95 |
| 0.25 | 0.3797 | 151.9 | 38.73 | 38.19 | 13.98 | 9.71 |
| 0.4 | 0.3170 | 126.8 | 51.36 | 51.04 | 13.72 | 9.31 |
| 0.55 | 0.2625 | 105.0 | 58.27 | 58.12 | 13.40 | 8.80 |
| 0.7 | 0.2158 | 86.3 | 60.86 | 60.83 | 13.03 | 8.23 |
| 0.85 | 0.1765 | 70.6 | 60.35 | 60.40 | 12.62 | 7.62 |
| 1.0 | 0.1436 | 57.4 | 57.73 | 57.84 | 12.19 | 7.01 |
| 1.25 | 0.1011 | 40.4 | 50.74 | 50.89 | 11.41 | 6.03 |
| 1.5 | 0.0706 | 28.2 | 42.51 | 42.67 | 10.59 | 5.12 |
| 2.0 | 0.0340 | 13.6 | 27.27 | 27.40 | 8.90 | 3.62 |

The inventory limit should not bind: the largest predicted std of terminal inventory is 9.95
lots against a limit of 50.

## Setup

- Scenario `baseline` (random walk, public mid, noise traders only, requote every step, no fees).
- Strategy `fixed`, 10 half-spreads (grid in the front matter), 1000 episodes of 200 steps each.
- Root seed 101 for every grid point (common random numbers: same value paths, same noise
  draws).
- Seeds already looked at while building Stage A, and therefore **not** used here: 1 (the
  `mm-sim run` acceptance command), 7, 77, 2025, 12345 (tests and smoke runs).

## Numbers that confirm or reject

Fixed before the run and implemented in `src/mm_sim/analysis/exp_fixed_spread.py::verdict`:

- **C1 (mean):** at every grid point `|simulated mean − predicted mean| ≤ 3.5` standard errors.
  With 10 points, a correct model fails this by chance in about 0.5% of runs.
- **C2 (optimum):** the grid point with the highest simulated mean is the one the theory
  predicts (`h = 0.7`) or its neighbour (`0.55` or `0.85`).
- **C3a (std):** at every grid point the simulated std is within 10% of the predicted std.
  (The standard error of a std estimate from 1000 episodes is about 2.2%, somewhat more for a
  non-normal P&L; 10% leaves room for that.)
- **C3b (std direction):** the simulated std at `h = 2.0` is below the std at `h = 0.1`.

Decision rule: **CONFIRMED** if all four hold. **REJECTED** if C1 or C3a fails (the simulator
and the formula disagree; then find out whether the derivation or the code is wrong).
**INCONCLUSIVE** if only C2 or C3b fails.

Precondition reported with the result: the share of steps at the inventory limit. If it is
not 0 at some grid point, the theory's assumption fails there and that is stated next to the
verdict.

## Result

Not run yet.

## Decision

Not run yet.

## What I learned

Not run yet.
