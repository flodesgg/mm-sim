---
id: EXP-003
title: "Inventory management: Avellaneda-Stoikov and skew against fixed quotes at the same spread"
status: done             # draft | approved | done
approved_by: "delegation during an overnight run"  # Nick, 2026-11-09, delegated the build overnight; not reviewed by Nick before the run
approved_on: 2026-11-09
scenario: "inventory"
config_hash: "462cf8b0d9ce"
decision: "CONFIRMED"    # CONFIRMED | REJECTED | INCONCLUSIVE
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

Run once on 2026-11-09: run id `20261109T214532Z-6561a4`, git commit `741ba8fd1ee7` (clean),
config hash `462cf8b0d9ce`, seed 303, 1000 episodes per run. Numbers from
`reports/experiments/EXP-003/frontier.csv`; report with the frontier and inventory figures:
`reports/experiments/EXP-003/report.md`.

Liquidated P&L per episode; "fixed" is the benchmark at the same average quoted spread:

| strategy | value | avg spread | mean [95% CI] | std | fixed: mean | fixed: std | std ratio [95% CI] | mean diff [95% CI] |
|---|---|---|---|---|---|---|---|---|
| AS γ | 0.01 | 1.359 | 56.81 [56.20, 57.42] | 9.78 | 53.74 | 16.14 | 0.606 [0.568, 0.650] | 3.08 [2.48, 3.67] |
| AS γ | 0.05 | 1.422 | 56.86 [56.42, 57.30] | 7.08 | 54.11 | 15.76 | 0.449 [0.407, 0.496] | 2.75 [1.92, 3.58] |
| **AS γ** | **0.1** | 1.502 | 55.53 [55.13, 55.93] | 6.46 | 54.13 | 15.49 | **0.417 [0.374, 0.464]** | 1.40 [0.54, 2.26] |
| AS γ | 0.2 | 1.664 | 52.36 [51.98, 52.74] | 6.15 | 54.22 | 14.73 | 0.417 [0.377, 0.459] | -1.85 [-2.69, -1.02] |
| AS γ | 0.5 | 2.166 | 41.98 [41.63, 42.33] | 5.69 | 50.80 | 13.11 | 0.434 [0.398, 0.470] | -8.82 [-9.56, -8.08] |
| AS γ | 1.0 | 3.042 | 27.55 [27.26, 27.83] | 4.59 | 38.52 | 11.07 | 0.414 [0.384, 0.445] | -10.98 [-11.59, -10.36] |
| skew κ | 0.01 | 1.510 | 57.27 [56.58, 57.95] | 11.01 | 54.14 | 15.48 | 0.711 [0.673, 0.752] | 3.12 [2.70, 3.55] |
| skew κ | 0.02 | 1.510 | 58.24 [57.66, 58.82] | 9.36 | 54.14 | 15.48 | 0.605 [0.564, 0.649] | 4.10 [3.52, 4.68] |
| skew κ | 0.05 | 1.510 | 58.79 [58.33, 59.26] | 7.53 | 54.14 | 15.48 | 0.486 [0.440, 0.536] | 4.65 [3.88, 5.42] |
| skew κ | 0.1 | 1.510 | 58.20 [57.79, 58.61] | 6.64 | 54.14 | 15.48 | 0.429 [0.385, 0.477] | 4.06 [3.21, 4.90] |
| skew κ | 0.2 | 1.510 | 56.50 [56.13, 56.88] | 6.04 | 54.14 | 15.48 | 0.390 [0.350, 0.435] | 2.36 [1.48, 3.24] |

- H1 PASS: every std-ratio CI for AS `γ ≥ 0.1` and skew `κ ≥ 0.05` is below 1 (the largest
  upper end is 0.536).
- H2 PASS: AS `γ = 0.1` std ratio 0.417, CI [0.374, 0.464], below 0.75. The std of liquidated
  P&L is cut by 58% (CI 54% to 63%).
- H3 PASS: AS `γ = 0.1` mean liquidated P&L is 1.40 **higher** than the benchmark's
  (CI [0.54, 2.26]); the limit was −0.15 × 54.13 = −8.12.
- H4 PASS: CE 53.52 against −18.84 for the benchmark; difference CI [20.2, 83.5].
- Share of steps at the inventory limit: 0 in every run. Std of terminal inventory for AS
  `γ = 0.1`: 2.99 lots against 8.11 for its benchmark.

## Decision

**CONFIRMED.** All four pre-registered criteria hold.

What the verdict does not say:

1. **H3 passed for a reason the hypothesis did not anticipate.** On liquidated P&L the
   inventory strategy does not cost mean P&L at all: it earns more, because the fixed
   benchmark pays about 6.5 per episode to close its larger final inventory (mark-to-market
   60.64, liquidated 54.13). On mark-to-market P&L, which is what the paper reports, AS
   `γ = 0.1` does cost: 57.16 against 60.64, about 5.7% of the mean. Both statements depend on
   the invented liquidation cost `0.5 + 0.05·|q|`.
2. **The benchmark's certainty equivalent is driven by a few episodes.** A CE of −18.8 for a
   P&L with mean 54 and std 15.5 comes from the worst episodes, where a large final inventory
   meets the quadratic liquidation cost; across the eleven benchmarks it ranges from −18.8 to
   +29.3. H4's direction is clear, its size is not a stable number. The CE difference CI is
   correspondingly wide.
3. **Simple skew is at least as good as Avellaneda–Stoikov here.** Skew `κ = 0.05`: mean 58.79,
   std 7.53; AS `γ = 0.1`: mean 55.53, std 6.46; skew `κ = 0.1`: mean 58.20, std 6.64. On this
   frontier the skew points lie above the AS points. Likely reasons, not tested: AS is derived
   for mark-to-market wealth without a liquidation cost; its skew `γ·σ²·(T−t)` per lot is 0.4
   at the start (eight times `κ = 0.05`) and zero at the end, so it gives up edge early and
   stops controlling inventory exactly when liquidation is near; and it widens the spread
   early. This is an observation from one run with one liquidation cost, not a pre-registered
   comparison.
4. The 22 runs share one seed. The eleven benchmark rows are not independent.
5. Approved under delegation during an overnight run, not by Nick; the hypothesis numbers
   were set under the same delegation.

## What I learned

About the model (noise traders only, martingale value):

- Inventory is where the risk is. Skewing quotes against the position cuts the std of
  terminal inventory from about 8 lots to 2 to 3, and the std of P&L by more than half.
- The price of that, measured mark-to-market, is a few percent of mean P&L at moderate
  settings (AS `γ = 0.1`: 5.7%; skew `κ = 0.05`: 60.09 against 60.65, under 1%), and grows
  quickly when risk aversion is high (AS `γ = 1`: 28.3 against 41.9 for fixed quotes at the
  same spread).
- Once closing the position costs something, managing inventory raises the mean as well.
- Pairing on common random numbers made the CI of the mean difference 0.36 to 0.86 times as
  wide as an unpaired comparison. The gain is large when the two strategies are similar
  (skew `κ = 0.01` against fixed: 0.36) and small when they behave differently.
- A model-derived strategy is optimal for the model's objective, not for mine: change the
  objective (add a liquidation cost) and a simple rule can beat it.

What depends on the assumptions: no informed flow (skewing toward the mid would be exploited),
a martingale value, the true `σ` and `k` handed to AS, and the invented liquidation cost.
