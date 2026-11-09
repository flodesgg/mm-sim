---
id: EXP-002
title: "Fixed half-spread against informed flow: mean P&L heatmap and break-even line"
status: done             # draft | approved | done
approved_by: "delegation during an overnight run"  # Nick, 2026-11-09, delegated the build overnight; not reviewed by Nick before the run
approved_on: 2026-11-09
scenario: "toxic"
config_hash: "92ddd4ad4197"
decision: "CONFIRMED"    # CONFIRMED | REJECTED | INCONCLUSIVE
kind: "spread_intensity_heatmap"
strategy: "fixed"
grid:
  half_spread: [0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.75, 1.0, 1.5]
config_grid:
  flow.informed.intensity: [0.0, 20.0, 40.0, 80.0, 120.0, 160.0, 200.0]
seed: 202
episodes: 1000
---

# EXP-002 — half-spread × informed intensity

Written before the run. Nothing in this file comes from a simulation at seed 202: every
predicted number is computed from `src/mm_sim/analysis/theory.py`
(`fixed_mean_pnl_with_informed`, `break_even_half_spread`; derived in `docs/model_notes.md`,
section 10).

## Hypothesis

Informed traders make a narrow fixed spread lose money. For each informed intensity `λ_I`
there is a break-even half-spread below which the market maker's mean P&L is negative, and
this break-even half-spread rises with `λ_I`. The mean P&L in every cell of the grid follows
the closed form below.

## Prediction from theory

An informed trader arrives with probability `π = λ_I·dt` per step, knows the value `h_I` steps
ahead (a move `M ~ N(0, s²)`, `s = σ·√(h_I·dt)`, shorter near the end of the episode), and
lifts the ask at distance `d` if `M > d + c_I` (symmetric for the bid). With `z = (d + c_I)/s`,
`Q = 1 − Φ`, `φ` the normal density and `p(d)` the noise fill probability, per step and side:

```
informed loss = π · (s·φ(z) − d·Q(z))
noise gain    = p(d) · ( d·(1 − π·Q(z)) + π·s·φ(z) )
E[P&L]        = Σ_steps 2 · (noise gain − informed loss)
```

Scenario `toxic`: the baseline plus `h_I = 50` steps (`s = 1.0`), `c_I = 0`, `q_max = 200`
(so that the inventory limit does not bind and the formula applies).

Predicted mean episode P&L and break-even half-spread:

| λ_I | π per step | h=0.05 | 0.1 | 0.2 | 0.3 | 0.4 | 0.5 | 0.6 | 0.75 | 1.0 | 1.5 | break-even h |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0.0 | 10.5 | 18.9 | 33.0 | 43.7 | 51.4 | 56.5 | 59.6 | 61.0 | 57.7 | 42.5 | 0.000 |
| 20 | 0.1 | 3.3 | 11.9 | 26.4 | 37.6 | 45.8 | 51.6 | 55.2 | 57.4 | 55.3 | 41.6 | 0.032 |
| 40 | 0.2 | -3.8 | 5.0 | 19.9 | 31.5 | 40.3 | 46.6 | 50.8 | 53.9 | 53.0 | 40.7 | 0.071 |
| 80 | 0.4 | -18.1 | -9.0 | 6.8 | 19.4 | 29.3 | 36.7 | 42.0 | 46.7 | 48.2 | 39.0 | 0.154 |
| 120 | 0.6 | -32.4 | -22.9 | -6.3 | 7.3 | 18.3 | 26.8 | 33.3 | 39.6 | 43.4 | 37.2 | 0.244 |
| 160 | 0.8 | -46.6 | -36.8 | -19.4 | -4.8 | 7.3 | 17.0 | 24.5 | 32.5 | 38.7 | 35.4 | 0.337 |
| 200 | 1.0 | -60.9 | -50.8 | -32.5 | -16.9 | -3.8 | 7.1 | 15.8 | 25.4 | 33.9 | 33.7 | 0.433 |

Also predicted: the best half-spread moves wider as `λ_I` grows (0.75 without informed
traders, 1.0 from `λ_I = 80` on, in this grid).

## Setup

- Scenario `toxic`; strategy `fixed`; 10 half-spreads × 7 informed intensities = 70 cells;
  1000 episodes of 200 steps per cell; root seed 202 in every cell (common random numbers).
- Seeds already looked at while building Stage B, and therefore not used here: 4242 (smoke
  runs against the theory), 8, 17, 21, 31 (tests).
- **Model choices Nick approves with this file:** the informed horizon `h_I = 50` steps, the
  threshold `c_I = 0`, and the intensity range up to `λ_I = 200` (an informed trader in every
  step). With the base value `h_I = 10` the informed edge is small (`s = 0.45`) and the
  break-even half-spread stays below 0.27 even at `λ_I = 200`; `h_I = 50` spreads the effect
  over the grid. These numbers are invented, not calibrated.

## Numbers that confirm or reject

Fixed before the run and implemented in `src/mm_sim/analysis/exp_heatmap.py::verdict`:

- **C1 (mean):** in every one of the 70 cells `|simulated mean − predicted mean| ≤ 4.0`
  standard errors. A correct model fails this by chance in about 0.4% of runs.
- **C2 (break-even):** for every `λ_I > 0` the simulated break-even half-spread (first zero of
  the mean P&L, linearly interpolated between grid points) is within 0.05 of the predicted
  one. If the simulated mean is already positive at `h = 0.05`, the simulated value is taken
  as 0.05 (an upper bound).
- **C3 (direction):** the simulated break-even rises strictly with `λ_I` over the intensities
  whose predicted break-even is inside the grid (`λ_I ≥ 40`).

Decision rule: **CONFIRMED** if all three hold. **REJECTED** if C1 or C2 fails.
**INCONCLUSIVE** if only C3 fails.

**SUSPICIOUS flag** (reported next to the verdict, a likely bug): a cell more than 0.05 below
the predicted break-even line whose 95% CI is entirely above zero.

Precondition reported with the result: the largest share of steps at the inventory limit.

## Result

Run once on 2026-11-09: git commit recorded in `reports/experiments/EXP-002/summary.json`
(clean tree), config hash `92ddd4ad4197`, seed 202, 1000 episodes per cell. Numbers below are
from `reports/experiments/EXP-002/cells.csv` and `break_even.csv`; the report with the heatmap
is `reports/experiments/EXP-002/report.md`.

Mean episode P&L (simulated):

| λ_I | h=0.05 | 0.1 | 0.2 | 0.3 | 0.4 | 0.5 | 0.6 | 0.75 | 1.0 | 1.5 |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 11.1 | 19.8 | 34.0 | 44.8 | 52.4 | 57.3 | 60.2 | 61.5 | 58.6 | 43.0 |
| 20 | 4.2 | 13.1 | 27.7 | 39.0 | 47.2 | 52.7 | 56.2 | 58.2 | 56.4 | 42.1 |
| 40 | -2.6 | 6.4 | 21.4 | 33.2 | 42.0 | 48.2 | 52.1 | 54.9 | 54.2 | 41.3 |
| 80 | -16.2 | -6.8 | 9.0 | 21.8 | 31.6 | 39.0 | 44.0 | 48.4 | 50.0 | 39.8 |
| 120 | -30.0 | -20.4 | -3.7 | 10.3 | 21.2 | 29.8 | 35.9 | 41.9 | 45.8 | 38.5 |
| 160 | -43.7 | -33.7 | -16.2 | -1.2 | 10.7 | 20.5 | 27.8 | 35.4 | 41.4 | 36.9 |
| 200 | -57.3 | -46.8 | -28.6 | -12.6 | 0.5 | 11.2 | 19.6 | 28.9 | 37.1 | 35.4 |

Break-even half-spread:

| λ_I | simulated | predicted | difference |
|---|---|---|---|
| 20 | 0.050 (upper bound) | 0.032 | 0.018 |
| 40 | 0.064 | 0.071 | -0.007 |
| 80 | 0.143 | 0.154 | -0.011 |
| 120 | 0.226 | 0.244 | -0.017 |
| 160 | 0.310 | 0.337 | -0.027 |
| 200 | 0.396 | 0.433 | -0.036 |

- C1 PASS: the largest `|z|` over the 70 cells is 3.10 (limit 4.0).
- C2 PASS: the largest break-even difference is 0.036 (limit 0.05).
- C3 PASS: the simulated break-even rises from 0.064 to 0.396 over `λ_I = 40 .. 200`.
- No SUSPICIOUS flag. Share of steps at the inventory limit: 0 in every cell.

Decomposition at `h = 0.4` (mean per episode): as `λ_I` goes from 0 to 200, spread capture
rises from 51.6 to 86.8 (informed traders also pay the half-spread, 127 informed fills per
episode at `λ_I = 200`), while the short-term move after fills falls from +0.3 to −89.6. The
total falls from 52.4 to 0.5.

## Decision

**CONFIRMED.** All three pre-registered criteria hold.

What the verdict does not say:

1. **All 70 z-scores are positive** (between 1.3 and 3.1, mean 2.3). The cells share one seed,
   so this is one upward fluctuation of that sample, not 70 confirmations and not 70 warnings:
   already without informed traders (`λ_I = 0`), where EXP-001 confirmed the formula on another
   seed, this sample sits about 2 standard errors above theory, and the zero-mean parts of the
   decomposition (short-term move plus inventory P&L) are +0.85 there. The same fluctuation
   pushes every simulated break-even below the predicted one (differences −0.007 to −0.036).
   A bias of the formula that grows with `λ_I` cannot be excluded from one seed; checking it
   needs a new experiment on a new seed.
2. This experiment was approved under delegation during an overnight run, not by Nick.

## What I learned

About the model:

- Adverse selection is paid for by the spread. At `h = 0.4` an informed trader in every step
  (`λ_I = 200`) takes the mean P&L from 52 to about 0; the same quote that earns from noise
  traders is exactly the quote the informed trader picks when it is wrong.
- The break-even half-spread rises roughly linearly with the informed arrival rate here: about
  0.07 at `π = 0.2`, 0.15 at 0.4, 0.31 at 0.8, 0.40 at 1.0 (simulated).
- The profit-maximising half-spread also widens with informed flow: 0.75 for `λ_I ≤ 40`, 1.0
  from `λ_I = 80` on (grid values).
- Spread capture is a misleading number on its own: it goes up with informed flow because
  informed traders trade often. The decomposition and the markout curve show the loss.
- Selection works both ways: noise fills earn slightly more than the half-spread after the
  fill, because a quote that no informed trader took is less likely to be wrong.

What depends on the assumptions: the informed horizon (50 steps here; the edge scales with
`σ·√(h_I·dt)`), informed traders who always trade when it pays, a market maker that never
reacts to being hit, and noise flow that does not depend on the spread history.
