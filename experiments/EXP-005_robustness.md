---
id: EXP-005
title: "Robustness: do the key conclusions keep their sign under other model assumptions?"
status: done             # draft | approved | done
approved_by: "delegation during an overnight run"  # Nick, 2026-11-09, delegated the build overnight; not reviewed by Nick before the run
approved_on: 2026-11-09
scenario: "baseline"
config_hash: "fbe6c4ea5f6c"
decision: "CONFIRMED"    # CONFIRMED | REJECTED | INCONCLUSIVE
kind: "robustness"
strategy: "fixed"
grid: {}
seed: 505
episodes: 1000
settings:
  variants:
    base: {}
    sigma_high: {"market.sigma": 4.0}
    k_high: {"flow.noise.k": 3.0}
    jumps: {"market.process": "jump_diffusion", "market.jump.intensity": 5.0, "market.jump.size": 1.0}
  spread_factor: 3.0
  informed: {"flow.informed.intensity": 120.0, "flow.informed.horizon_steps": 50, "engine.q_max": 200}
  narrow_half_spread: 0.1
  inventory: {"engine.liq_half_spread": 0.5, "engine.liq_impact": 0.05}
  as_gamma: 0.1
  skew_kappa: 0.05
  latency: {"engine.q_max": 200}
  slow_requote: 5
---

# EXP-005 — robustness of the key conclusions

Written and committed before the run. Approved under delegation during an overnight run, not by Nick.

## Hypothesis

The qualitative conclusions of EXP-001 to EXP-004 are not artefacts of the base parameters:
each keeps its sign when volatility is doubled, when the fill intensity decays twice as fast
with distance, and when the value jumps.

## The conclusions and their predicted signs

Each is a signed quantity with a 95% confidence interval, estimated under the base
configuration and under three variants (one change each):

| variant | change |
|---|---|
| base | none |
| sigma_high | `σ = 4` instead of 2 |
| k_high | `k = 3.0` instead of 1.5 |
| jumps | jumps of `±1.0` at rate 5 per unit time |

| conclusion | quantity | predicted sign | from |
|---|---|---|---|
| K1a | P&L(fixed at h\*) − P&L(fixed at h\*/3) | positive | EXP-001 |
| K1b | P&L(fixed at h\*) − P&L(fixed at 3·h\*) | positive | EXP-001 |
| K2 | mean P&L of fixed at h = 0.1 with informed flow (`λ_I = 120`, horizon 50) | negative | EXP-002 |
| K3a | std ratio − 1, Avellaneda–Stoikov `γ = 0.1` vs fixed at the same spread, liquidated P&L | negative | EXP-003 |
| K3b | std ratio − 1, skew `κ = 0.05` (half-spread h\*) vs fixed at the same spread | negative | EXP-003 |
| K4 | P&L(fixed at h\*, requote every 5) − P&L(requote every step) | negative | EXP-004 |

`h*` is the theoretical best half-spread for the variant's own noise-flow parameters
(`theory.optimal_fixed_half_spread`). K3 uses the liquidation cost `0.5 + 0.05·|q|`.
K4's base case has no jumps (diffusion alone), so the `jumps` variant adds them.

Reasoning behind the predictions (no simulation at seed 505 was looked at):

- K1: the interior optimum comes from the shape `δ·p(δ)`, which does not involve `σ` or
  jumps when the market maker requotes every step; with `k = 3` the optimum moves (to about
  half) but stays interior.
- K2: the closed form of EXP-002 is negative at `h = 0.1` for `λ_I = 120` in the base case
  (−22.9). Higher `σ` and jumps make the informed traders' edge larger. With `k = 3` noise
  traders fill a quote at 0.1 less often, which makes it worse.
- K3: inventory variance grows with `σ²` and with jumps, so there is more risk to remove.
  Avellaneda–Stoikov is given the true `σ` but does not know about jumps.
- K4: a stale quote is picked off whenever the value moves through it; every variant moves
  the value at least as much as the base case relative to the half-spread.

## Setup

- 4 variants × 10 runs (K1: 3, K2: 1, K3: 4, K4: 2) = 40 runs of 1000 episodes, root seed 505.
  Runs inside one variant share the seed, so differences are paired.
- CIs: paired t-interval for P&L differences and means; paired bootstrap (2000 resamples) for
  the std ratios.
- Seeds looked at while building this analysis: 5 (tests, 60 episodes, two variants).

## Numbers that confirm or reject

Implemented in `src/mm_sim/analysis/exp_robustness.py::verdict`. For each conclusion and
variant: **holds** if the CI is entirely on the predicted side of zero, **flipped** if it is
entirely on the other side, **unresolved** if it includes zero. A conclusion is **robust** if
it holds in all four variants, **fragile** if it flips in any, otherwise **unresolved**.

Decision rule: **CONFIRMED** if all six conclusions are robust. **REJECTED** if any is
fragile. **INCONCLUSIVE** otherwise. Fragile conclusions are labelled `fragile` in the
README and reports.

## Result

Run once on 2026-11-09: run id `20261109T220045Z-da3d7c`, git commit `c119b9766964`
(clean), config hash `fbe6c4ea5f6c`, seed 505, 1000 episodes per
run. Numbers from `reports/experiments/EXP-005/robustness.csv`; report:
`reports/experiments/EXP-005/report.md`.

Estimate [95% CI]:

| conclusion | predicted | base | sigma_high | k_high | jumps | label |
|---|---|---|---|---|---|---|
| K1a P&L(h\*) − P&L(h\*/3) | + | 21.99 [21.28, 22.69] | 21.53 [20.22, 22.83] | 10.55 [9.90, 11.21] | 23.09 [22.01, 24.18] | robust |
| K1b P&L(h\*) − P&L(3·h\*) | + | 39.42 [38.59, 40.25] | 39.39 [37.95, 40.84] | 19.76 [19.04, 20.49] | 39.85 [38.67, 41.02] | robust |
| K2 mean P&L, h = 0.1, informed flow | − | -21.64 [-23.89, -19.39] | -68.48 [-72.99, -63.97] | -27.68 [-30.13, -25.22] | -48.91 [-52.54, -45.29] | robust |
| K3a AS std ratio − 1 | − | -0.553 [-0.588, -0.513] | -0.687 [-0.712, -0.659] | -0.703 [-0.729, -0.674] | -0.647 [-0.672, -0.620] | robust |
| K3b skew std ratio − 1 | − | -0.473 [-0.512, -0.430] | -0.550 [-0.584, -0.513] | -0.667 [-0.697, -0.633] | -0.543 [-0.572, -0.512] | robust |
| K4 P&L(requote 5) − P&L(requote 1) | − | -2.62 [-3.08, -2.16] | -11.26 [-12.64, -9.88] | -5.55 [-6.23, -4.87] | -6.63 [-7.48, -5.77] | robust |

`h*` used: 0.749 (base, sigma_high, jumps), 0.374 (k_high).

## Decision

**CONFIRMED.** All six conclusions hold in all four variants; none is fragile and none is
unresolved.

What the verdict does not say: three single-parameter variants are a narrow test. Every
variant keeps the assumptions most likely to matter in a real market (exponential fill
intensity, one-lot orders, no competing market maker, a martingale value, informed traders
who do not hide). "Robust" here means "does not depend on σ, k or jumps inside this model".
Approved under delegation during an overnight run, not by Nick.

## What I learned

- The direction of every headline result survives the three changes; the sizes do not.
  Doubling volatility triples the loss of a narrow spread to informed traders (−21.6 to
  −68.5) and quadruples the cost of slow requoting (−2.6 to −11.3).
- With `k = 3` the best half-spread halves (0.749 to 0.374) and all P&L numbers shrink with
  it: `k` sets the scale of the whole spread business in this model.
- Inventory management removes more risk, relatively, when there is more risk: the std ratio
  falls from 0.45 to about 0.3 with higher volatility or faster decay.
- Latency costs something even without jumps (−2.6 in the base case, from diffusion alone).
