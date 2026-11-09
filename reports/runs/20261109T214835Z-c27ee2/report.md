# Run report: `fixed` in scenario `inventory`

## Limitations (read first)

Everything below is a statement about a **model**, not about real markets.

- Fill probability is an assumed exponential function of the quote's distance from the mid.
- Orders are one lot. There is no order book, no queue position and no competing market maker.
- The market maker sees the true value as a public mid price (in the `public_mid` world).
- Strategies that use the volatility `sigma` or the flow parameter `k` are given the true values.
- Informed traders' horizon and threshold are invented parameters, not calibrated to data.
- No hedging, no correlated instruments. Latency exists only through `requote_every`.
- Parameters are not calibrated to any market; P&L units are arbitrary.

## Setup

- scenario: `inventory`, config hash `462cf8b0d9ce`
- run id `20261109T214835Z-c27ee2`, git commit `f6443b837a70` (uncommitted changes)
- root seed 1, 1000 episodes
- variants tried so far in this repository (lines in `experiments/trial_log.csv`): 115
- strategy `fixed`, parameters `{"half_spread": 0.75}`
- 200 steps of dt = 0.005 per episode, decomposition horizon h = 10 steps

## Results (per episode)

| P&L | mean | 95% CI | std | Sharpe (per episode, not annualised) | 5% quantile | ES 5% | P(P&L<0) | CE (CARA) |
|---|---|---|---|---|---|---|---|---|
| mark-to-market | 60.717 | [59.917, 61.516] | 12.885 | 4.712 | 40.344 | 33.053 | 0.000 | 50.753 |
| liquidated | 54.039 | [53.106, 54.972] | 15.041 | 3.593 | 26.100 | 13.442 | 0.007 | 32.857 |

CE uses risk aversion gamma = 0.1.

## P&L decomposition (mean per episode)

| part | mean | 95% CI |
|---|---|---|
| spread capture | 60.825 | [60.431, 61.220] |
| short-term move after fills (negative = adverse selection) | -0.075 | [-0.297, 0.146] |
| inventory / holding P&L | -0.033 | [-0.728, 0.661] |
| fees paid (subtracted) | 0.000 | [0.000, 0.000] |
| **total: mark-to-market P&L** | 60.717 | [59.917, 61.516] |

Identity check: the largest per-episode error of `spread + short-term + inventory - fees = P&L` is 1.76e-12.

## Activity (mean per episode)

| metric | mean | 95% CI |
|---|---|---|
| buys | 40.306 | [39.942, 40.670] |
| sells | 40.261 | [39.893, 40.629] |
| volume | 80.567 | [80.045, 81.089] |
| max_abs_q | 9.666 | [9.390, 9.942] |
| mean_abs_q | 4.346 | [4.181, 4.511] |
| terminal_q | 0.045 | [-0.469, 0.559] |
| share_at_limit | 0.000 | [0.000, 0.000] |

## Markouts by counterparty (mean per fill)

Markout at horizon h = side * (V at h steps after the fill - fill price). At h = 0 it is the edge at the fill; a curve that falls with h means the flow was informed. The market maker cannot see the counterparty type; the analysis can.

| counterparty | fills | h | markout | 95% CI |
|---|---|---|---|---|
| noise | 80567 | 0 | 0.7550 | [0.7549, 0.7550] |
| noise | 80567 | 1 | 0.7537 | [0.7528, 0.7546] |
| noise | 80567 | 2 | 0.7542 | [0.7529, 0.7554] |
| noise | 80567 | 5 | 0.7542 | [0.7522, 0.7562] |
| noise | 80567 | 10 | 0.7540 | [0.7513, 0.7568] |
| noise | 80567 | 20 | 0.7545 | [0.7507, 0.7583] |
| noise | 80567 | 50 | 0.7539 | [0.7482, 0.7596] |

![markout curves](markouts.png)

## Example episode

![example episode](example_episode.png)

Episode 0 of this run. One episode is an illustration, not evidence.

## Files

`summary.json` (all numbers above), `episodes.csv` (one row per episode).
