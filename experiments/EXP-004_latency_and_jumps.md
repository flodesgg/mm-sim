---
id: EXP-004
title: "Stale quotes: mean P&L and pick-offs against the requote interval, with jumps"
status: approved         # draft | approved | done
approved_by: "delegation during an overnight run"  # Nick, 2026-11-09, delegated the build overnight; not reviewed by Nick before the run
approved_on: 2026-11-09
scenario: "jumpy"
config_hash: "d1c8fe6df97e"
decision: null           # CONFIRMED | REJECTED | INCONCLUSIVE
kind: "latency_sweep"
strategy: "fixed"
grid: {}
config_grid:
  engine.requote_every: [1, 2, 3, 5, 10, 20]
seed: 404
episodes: 1000
---

# EXP-004 — latency and jumps

Written and committed before the run. Nothing here comes from a simulation at seed 404: the
predictions are computed from `src/mm_sim/analysis/theory.py` (`latency_mean_pnl`,
`latency_pick_offs`; derived in `docs/model_notes.md`, section 13).

## Hypothesis

A market maker that requotes only every `m` steps leaves stale quotes in the market. After the
value moves through a stale quote, the quote is filled at a loss (picked off). Mean P&L falls
and the number of pick-offs rises as `m` grows, both following the closed form.

## Prediction from theory

A quote of age `j` steps stands at distance `d − D_j` from the current value on one side and
`d + D_j` on the other, where `D_j` is the value move since it was posted (diffusion plus
jumps) and `d` is the quoted distance. A fill at distance `x` earns `x`, which is negative
when the value has moved through the quote, and the fill probability `p(x)` is then close to 1:

```
E[P&L]       = Σ_steps 2·E[(d − D_age)·p(d − D_age)]
E[pick-offs] = Σ_steps with age > 0  2·E[p(d − D_age); D_age > d]
```

Scenario `jumpy`: the baseline plus jumps of `±1.0` with probability 0.025 per step (about
five per episode), noise traders only, `fixed` with half-spread 0.75, `q_max = 200`.
**The jump size and rate are invented numbers, chosen under the overnight delegation, not by Nick**: a jump of 1.0 is larger than
the half-spread, so one jump puts a stale quote 0.25 through the value.

| requote every | predicted mean P&L | predicted pick-offs per episode |
|---|---|---|
| 1 | 60.98 | 0.00 |
| 2 | 59.42 | 1.54 |
| 3 | 57.85 | 2.94 |
| 5 | 54.59 | 5.73 |
| 10 | 46.31 | 13.57 |
| 20 | 29.73 | 29.44 |

For comparison, the same formula without jumps gives 58.43 at `m = 5` and 47.61 at `m = 20`:
at short intervals the jumps do most of the damage, at long intervals ordinary diffusion
moves the value through the quote as well.

## Setup

- Scenario `jumpy`, strategy `fixed` (half-spread 0.75 from the config), six requote
  intervals, 1000 episodes of 200 steps, root seed 404 at every grid point.
- Seeds looked at while building Stage C and not used here: 4242 (smoke runs against the
  theory at `m = 1, 5, 20`), 5, 23 (tests).

## Numbers that confirm or reject

Implemented in `src/mm_sim/analysis/exp_latency.py::verdict`:

- **C1 (mean):** at every grid point `|simulated mean P&L − predicted| ≤ 4.0` standard errors.
- **C2 (direction):** the simulated mean P&L falls strictly as `m` grows.
- **C3 (pick-offs):** for every `m > 1`, `|simulated pick-offs − predicted| ≤ 4.0` standard
  errors.
- **C4 (they lose money):** for every `m > 1` the average edge of the pick-off fills at the
  moment of the fill has a 95% CI entirely below 0.

Decision rule: **CONFIRMED** if all four hold. **REJECTED** if C1 or C3 fails.
**INCONCLUSIVE** if only C2 or C4 fails.

Precondition reported with the result: the share of steps at the inventory limit.

## Result

Not run yet.

## Decision

Not run yet.

## What I learned

Not run yet.
