---
id: EXP-004
title: "Stale quotes: mean P&L and pick-offs against the requote interval, with jumps"
status: done             # draft | approved | done
approved_by: "delegation during an overnight run"  # Nick, 2026-11-09, delegated the build overnight; not reviewed by Nick before the run
approved_on: 2026-11-09
scenario: "jumpy"
config_hash: "d1c8fe6df97e"
decision: "CONFIRMED"    # CONFIRMED | REJECTED | INCONCLUSIVE
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

Run once on 2026-11-09: run id `20261109T214608Z-0497ff`, git commit `741ba8fd1ee7`, config
hash `d1c8fe6df97e`, seed 404, 1000 episodes per grid point. The run metadata says
"uncommitted changes": EXP-003 and EXP-004 were started one after the other, and EXP-003's
output files were not yet committed when EXP-004 began. The code was the committed code.
Numbers from `reports/experiments/EXP-004/latency.csv`; report:
`reports/experiments/EXP-004/report.md`.

| requote every | mean P&L [95% CI] | predicted | z | std | pick-offs [95% CI] | predicted | z | edge per pick-off [95% CI] |
|---|---|---|---|---|---|---|---|---|
| 1 | 61.30 [60.23, 62.38] | 60.98 | 0.58 | 17.30 | 0.00 | 0.00 | – | – |
| 2 | 59.75 [58.66, 60.85] | 59.42 | 0.60 | 17.65 | 1.55 [1.47, 1.63] | 1.54 | 0.21 | -0.275 [-0.282, -0.269] |
| 3 | 58.22 [57.11, 59.34] | 57.85 | 0.67 | 17.95 | 2.84 [2.71, 2.96] | 2.94 | -1.63 | -0.307 [-0.315, -0.300] |
| 5 | 54.70 [53.47, 55.93] | 54.59 | 0.17 | 19.82 | 5.66 [5.44, 5.89] | 5.73 | -0.59 | -0.346 [-0.355, -0.338] |
| 10 | 46.56 [44.85, 48.27] | 46.31 | 0.29 | 27.61 | 13.40 [12.96, 13.84] | 13.57 | -0.76 | -0.426 [-0.437, -0.415] |
| 20 | 30.07 [27.16, 32.97] | 29.73 | 0.23 | 46.78 | 29.46 [28.64, 30.28] | 29.44 | 0.04 | -0.540 [-0.554, -0.526] |

- C1 PASS: largest `|z|` for the mean is 0.67.
- C2 PASS: mean P&L falls at every step of the grid, from 61.30 to 30.07.
- C3 PASS: largest `|z|` for pick-offs is 1.63.
- C4 PASS: the edge per pick-off is negative with a CI below 0 at every `m > 1`.
- Share of steps at the inventory limit: 0 at every grid point.

## Decision

**CONFIRMED.** All four pre-registered criteria hold.

What the verdict does not say: the six grid points share one seed (the z-scores for the mean
are all slightly positive for that reason); and "who picks off" in this model is the ordinary
noise flow reacting to price, not a fast informed trader, so the pick-off is almost but not
quite certain. Approved under delegation during an overnight run, not by Nick.

## What I learned

About the model:

- Latency has a price that can be read off the table: requoting every 5 steps instead of every
  step costs 6.6 of 61.3 mean P&L (11%); every 20 steps costs half.
- The loss is concentrated in a few fills. At `m = 5` about 5.7 of 85 fills per episode are
  pick-offs, each losing 0.35 on average at the moment of the fill, while an ordinary fill
  earns the half-spread 0.75.
- Slow requoting gets *more* fills (80.6 at `m = 1`, 100.6 at `m = 20`), and the extra ones
  are the bad ones. Fill count is not a measure of success.
- P&L std rises from 17 to 47: stale quotes accumulate inventory in the direction of the
  move, the worst time to hold it.
- Without jumps the same formula gives 58.4 at `m = 5`: at short intervals jumps cause most of
  the damage; at long intervals diffusion alone moves the value through the quote.

What depends on the assumptions: the jump size and rate (invented), a market maker that
requotes on a clock instead of cancelling on a signal, and noise flow as the only "sniper".
