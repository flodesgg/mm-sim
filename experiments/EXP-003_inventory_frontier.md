---
id: EXP-003
title: "Inventory management: Avellaneda-Stoikov and skew against fixed quotes at the same spread"
status: approved         # draft | approved | done
approved_by: "delegation during an overnight run"  # Nick, 2026-11-09, delegated the build overnight; not reviewed by Nick before the run
approved_on: 2026-11-09
scenario: "inventory"
config_hash: "462cf8b0d9ce"
decision: null           # CONFIRMED | REJECTED | INCONCLUSIVE
kind: "inventory_frontier"
strategy: "avellaneda_stoikov"
grid:
  gamma: [0.01, 0.05, 0.1, 0.2, 0.5, 1.0]
  kappa: [0.01, 0.02, 0.05, 0.1, 0.2]
seed: 303
episodes: 1000
---

# EXP-003 — risk–return frontier of inventory management

Written and committed before the run. The build prompt says Nick sets the hypothesis numbers
of this experiment; he delegated the build overnight, so **the numbers below were set under that
delegation, not by Nick**.

## Hypothesis

Managing inventory (skewing quotes against the position) lowers the risk of P&L a lot and
costs little mean P&L, compared with fixed quotes of the same average spread. On the
risk-adjusted objective that Avellaneda–Stoikov optimise (the CARA certainty equivalent) the
inventory strategy is better.

## Prediction and where the numbers come from

There is no closed form here, so the numbers come from the source paper and from the
mechanics of the model:

- Avellaneda & Stoikov (2008), section 3.3, simulate `γ = 0.1` with the parameters this lab
  uses as its base and report a profit std for the inventory strategy of roughly half that of
  the symmetric strategy with the same spread, with a slightly lower mean profit (read in the
  paper's Table 1; see `docs/model_notes.md`, section 8). This simulator differs from theirs
  (Gaussian steps, fill probability `1 − exp(−λ·dt)`, a tick grid, a liquidation cost), so the
  paper's numbers are a guide, not a target. The thresholds below are deliberately looser.
- Mechanics: the value is a martingale, so inventory adds variance and no mean. Skewing gives
  up some edge per fill to shrink inventory. Larger `γ` or `κ` should shrink risk further and
  cost more mean.

Scenario `inventory`: the baseline (noise traders only) plus a liquidation cost of
`0.5 + 0.05·|q|` per lot on the final inventory, so that ending with a large position is
penalised. **This cost is an invented number, chosen under the overnight delegation, not by Nick.**

## Setup

- Variants: `avellaneda_stoikov` with `γ ∈ {0.01, 0.05, 0.1, 0.2, 0.5, 1.0}`; `skew` with
  half-spread 0.75 and `κ ∈ {0.01, 0.02, 0.05, 0.1, 0.2}`.
- Benchmark for each variant: `fixed` with half the variant's average quoted spread (measured
  in the variant's own run), on the same seed. 11 variants + 11 benchmarks = 22 runs.
- 1000 episodes of 200 steps, root seed 303 everywhere (common random numbers).
- Judged on **liquidated** P&L. CE with risk aversion 0.1. CIs of the std ratio and of the CE
  difference by paired bootstrap over episodes (2000 resamples, fixed bootstrap seed).
- Seeds looked at while building Stage C and not used here: 4242 (one 300-episode smoke run of
  fixed, skew `κ = 0.05` and AS `γ = 0.1`: liquidated P&L std 13.3, 7.2 and 6.5), 3, 9, 13
  (tests). The thresholds below were chosen from the paper before that smoke run; it is
  disclosed because it was seen before this file was committed.

## Numbers that confirm or reject

Implemented in `src/mm_sim/analysis/exp_frontier.py::verdict`:

- **H1 (risk falls):** for every AS `γ ≥ 0.1` and every skew `κ ≥ 0.05`, the ratio
  std(variant) / std(benchmark) of liquidated P&L has a 95% bootstrap CI entirely below 1.
- **H2 (by how much):** for AS `γ = 0.1` the upper end of that CI is below 0.75 (the std is cut
  by at least 25%).
- **H3 (what it costs):** for AS `γ = 0.1` the mean liquidated P&L is at most 15% below the
  benchmark's: the lower end of the paired 95% CI of the mean difference is above
  `−0.15 × benchmark mean`.
- **H4 (risk-adjusted):** for AS `γ = 0.1` the CE difference (variant − benchmark) has a 95%
  bootstrap CI entirely above 0.

Decision rule: **CONFIRMED** if all four hold. **REJECTED** if H1 or H2 fails.
**INCONCLUSIVE** if only H3 or H4 fails.

Small `γ` (0.01, 0.05) and small `κ` (0.01, 0.02) are in the grid to draw the frontier; no
criterion depends on them.

## Result

Not run yet.

## Decision

Not run yet.

## What I learned

Not run yet.
