---
id: EXP-002
title: "Fixed half-spread against informed flow: mean P&L heatmap and break-even line"
status: approved         # draft | approved | done
approved_by: "delegation during an overnight run"  # Nick, 2026-11-09, delegated the build overnight; not reviewed by Nick before the run
approved_on: 2026-11-09
scenario: "toxic"
config_hash: "92ddd4ad4197"
decision: null           # CONFIRMED | REJECTED | INCONCLUSIVE
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

Not run yet.

## Decision

Not run yet.

## What I learned

Not run yet.
