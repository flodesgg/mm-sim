# Model notes

The model in my own words, the fixed order of events, and the sources. Derivations and their
numerical tests are added in the stage that implements each formula; until then a formula
listed here is a specification, not a tested result.

Everything below describes a **model**. Nothing here is a statement about real markets.

## 1. Time and the true value

Time runs in steps `t = 0 .. N−1` of length `dt`; the horizon is `T = N·dt`. The asset has a
true value `V_t` that the market maker may or may not see (section 2). Three value processes:

| `market.process` | Rule | Stage |
|---|---|---|
| `random_walk` | `V_{t+1} = V_t + σ·√dt·Z`, `Z ~ N(0,1)` | A |
| `jump_diffusion` | the random walk, plus with probability `λ_J·dt` per step a jump `±J` (or `N(0, J²)`) | C |
| `two_point` | `V = V_H` with probability `p`, else `V_L`; drawn once, constant, revealed at the end | B |

## 2. What the market maker sees

A strategy receives an `Observation`: the step, the time left, its own inventory and cash, its
own past quotes and the public trade tape (time, price, side). In the `public_mid` world it
also sees the reference price `s_t = V_t`. In the `trades_only` world (used with `two_point`)
it sees no reference price and must infer the value from trades.

A strategy never receives the true value, a future value, a random generator or the engine.
This is enforced by the type of the observation and proved by the future-scramble test.

## 3. Order flow

The market maker has one bid `b_t` and one ask `a_t`, one lot each; it may pull a side. Each
side fills at most once per step.

- **Noise traders (`public_mid`).** With `δ_a = a_t − s_t` and `δ_b = s_t − b_t`, the ask is
  lifted with probability `1 − exp(−A·exp(−k·δ_a)·dt)` and, independently, the bid is hit with
  the same formula in `δ_b`. Distances use the current `s_t`, so a stale quote is measured
  against the price that has moved.
- **Informed traders (`public_mid`).** One arrives with probability `λ_I·dt` per step. It knows
  `V_{t+h_I}` and buys if `a_t < V_{t+h_I} − c_I`, sells if `b_t > V_{t+h_I} + c_I`.
- **Glosten–Milgrom flow (`two_point`).** One trader arrives per step. With probability `μ` it
  is informed: it buys if `V = V_H` and sells if `V = V_L`, and only at a profit (decision in
  `decisions.md`). Otherwise it is a noise trader who buys or sells with probability 1/2 at
  whatever the quote is.
- A maker fee per lot (negative = rebate) is charged on every fill.

## 4. The order of events in one step (fixed)

1. If `t % requote_every == 0`, the strategy receives the observation for step `t` and posts
   new quotes. Otherwise the previous quotes stay: this is the latency knob.
2. Informed traders act first (they are faster). Noise traders then act on any side that has
   not been filled in this step.
3. Fills are recorded with the counterparty type. The engine knows the type; the strategy
   never does.
4. The value moves to `V_{t+1}`.

Quotes are rounded to the tick grid outwards (bid down, ask up), so rounding never narrows
the spread. A price within 1e-9 ticks of a grid point counts as on the grid.

Details fixed by the reference engine (`src/mm_sim/engine/reference.py`) and pinned by the
hand-computed test `tests/test_engine_steps.py`:

- A fill at step `t` happens at the quote standing in step `t`, while the value is `V_t`.
- A side at the inventory limit at the start of a step is closed for the whole step.
- The kill switch is checked at the start of a step, on `cash + q·V_t`.
- The trade tape records the trader's side: `+1` the trader bought (ask lifted), `−1` sold.
- Noise fills use one uniform draw per step and side, drawn before the episode. The draws do
  not depend on the quotes, so two strategies on one seed face the same traders.

## 5. Positions, limits, end of episode

- The engine never lets a fill take `|q|` above `q_max`.
- Optional kill switch: quoting stops when mark-to-market P&L falls below `−L`.
- At `T`: mark-to-market P&L `= cash + q_T·V_T`. Liquidated P&L closes `q_T` at
  `V_T ∓ (liq_half_spread + liq_impact·|q_T|)` per lot. Both are reported.

## 6. P&L decomposition

For fill `i` with market-maker side `d_i` (+1 bought, −1 sold), price `p_i`, time `t_i` and
horizon `h` (`accounting.markout_horizon_steps`, with `t_i + h` clipped to `T`):

```
d_i·(V_T − p_i) =  d_i·(V_{t_i} − p_i)          spread capture
                 + d_i·(V_{t_i+h} − V_{t_i})     short-term move (negative = adverse selection)
                 + d_i·(V_T − V_{t_i+h})         inventory / holding P&L
```

This is an algebraic identity (the right-hand side telescopes), so the three parts plus fees
add up to the mark-to-market P&L exactly. It is tested in Stage A.

## 7. Strategies (specification; each is derived and tested in its stage)

- `fixed`: `bid = s − h`, `ask = s + h`.
- `skew`: `fixed` with both quotes shifted by `−κ·q`.
- `avellaneda_stoikov`: reservation price `r = s − q·γ·σ²·(T−t)`, total spread
  `γ·σ²·(T−t) + (2/γ)·ln(1 + γ/k)`, quotes `r ± spread/2`. Source and status: section 8.
- `glosten_milgrom`: Bayesian posterior on `V = V_H` from the trade tape; the ask is the
  expected value given that the next trade is a buy, the bid given a sell.
- `clairvoyant`: test-only negative control that sees the future through a test hook.

## 9. Fixed spread against noise flow: mean and std of P&L (derived here, tested)

Assumptions: `fixed` strategy with half-spread `h`, noise traders only, requote every step, no
fees, inventory limit not binding.

**Mean.** In one step the ask at distance `δ` is lifted with probability
`p(δ) = 1 − exp(−A·exp(−k·δ)·dt)` and then earns `δ` against the current value; the same for
the bid. The value is a martingale and its moves are independent of the fills, so inventory
earns zero on average. Summing `N` steps and two sides:

```
E[P&L] = N · 2 · δ · p(δ)
```

Outward rounding from a continuous mid makes `δ = h + U` with `U` roughly uniform on
`[0, tick)`, so the prediction averages over `U`. For `A·dt → 0`, `p(δ) ≈ A·exp(−k·δ)·dt` and
`δ·exp(−k·δ)` is maximal at `δ = 1/k`. For the baseline `A·dt = 0.7` the exact maximiser is
wider than `1/k`.

**Variance.** Write the P&L as spread capture plus the P&L of carried inventory:

- Spread capture is a sum of `2N` independent terms `δ·Bernoulli(p)`:
  variance `N·2·δ²·p·(1−p)`.
- Inventory after the fills of step `t` is `Q_t`, a sum of `t+1` independent net fills
  (`+1` with probability `p`, `−1` with probability `p`, both possible), each with variance
  `2p(1−p)`. It then earns `Q_t·(V_{t+1} − V_t)`. The value steps are independent with
  variance `σ²·dt`, so the variance is `σ²·dt · Σ_t E[Q_t²] = σ²·dt·2p(1−p)·N(N+1)/2`.
- The two parts are uncorrelated (value steps have mean zero and are independent of fills).

Code: `src/mm_sim/analysis/theory.py`. Tests: `tests/test_montecarlo.py`
(`test_simulated_mean_and_std_match_the_closed_form`, `test_theory_closed_form_without_tick`,
`test_optimal_half_spread_tends_to_one_over_k_for_small_dt`). The full check is EXP-001.

## 10. Fixed spread against noise and informed flow (derived here, tested)

Assumptions as in section 9, plus informed traders with arrival probability `π = λ_I·dt` per
step, horizon `h_I`, threshold `c_I`.

Look at the ask at distance `d` in step `t`. Let `M = V_{t+h_I} − V_t`, normal with mean 0 and
std `s_t = σ·√(dt·min(h_I, N − t))`. Write `z = (d + c_I)/s_t`, `Q = 1 − Φ`.

- **Informed fill.** With probability `π` an informed trader is there; it lifts the ask if
  `M > d + c_I`. The market maker sold at `V_t + d` something worth `V_t + M` at the informed
  horizon (and, the value being a martingale, on average afterwards). Expected loss:
  `π·E[(M − d); M > d + c_I] = π·(s_t·φ(z) − d·Q(z))`, using `E[M; M > a] = s·φ(a/s)`.
- **Noise fill.** Noise can lift the ask only if no informed trader took it: probability
  `1 − π·Q(z)`, then `p(d)`. It pays `d`. But "no informed trader took it" also selects the
  steps without a large upward move, so the move after a noise fill is favourable on average:
  `E[−M; ask free] = π·E[M; M > d + c_I] = π·s_t·φ(z)`.
  Expected gain: `p(d)·(d·(1 − π·Q(z)) + π·s_t·φ(z))`.

Per step and per side, expected P&L = noise gain − informed loss; the episode value sums over
steps and doubles for the two sides. The break-even half-spread is the smallest `h` where this
is zero. Code: `theory.fixed_mean_pnl_with_informed`, `theory.break_even_half_spread`. Tests:
`tests/test_informed_and_gm.py`. The full check is EXP-002.

The first version of this derivation left out the selection term `π·s_t·φ(z)`; a smoke run
disagreed with it by 14 standard errors, which is how the mistake was found (before EXP-002
was written).

## 11. Glosten–Milgrom quotes in the two-point world (derived here, tested)

`V ∈ {V_H, V_L}`, prior `P(V_H) = p`. Each step one trader arrives: informed with probability
`μ` (buys if `V = V_H`, sells if `V = V_L`), otherwise noise (buys or sells with probability
1/2). So

```
P(buy | V_H) = μ + (1−μ)/2        P(buy | V_L) = (1−μ)/2
```

and the sell probabilities are the same two, swapped. With posterior `π = P(V_H | trades)`,
Bayes' rule gives `P(V_H | buy) = π·P(buy|V_H) / (π·P(buy|V_H) + (1−π)·P(buy|V_L))`, and the
zero-expected-profit quotes are the expected value given the direction of the next trade:

```
ask = E[V | buy]  = V_L + (V_H − V_L)·P(V_H | buy)
bid = E[V | sell] = V_L + (V_H − V_L)·P(V_H | sell)
```

At `π = 1/2`: `P(V_H | buy) = (1+μ)/2` and `P(V_H | sell) = (1−μ)/2`, so
**`ask − bid = μ·(V_H − V_L)`**: the spread is the informed share times what the informed
know. After each trade `π` moves to the posterior, the quotes follow, and the spread shrinks
as the market maker learns the value.

A fixed quote `E[V] ± h` (prior 1/2) earns `h − μ·(V_H − V_L)/2` per trade on average: it
loses `(V_H − V_L)/2 − h` to an informed trader and earns `h` on average from a noise trader.
It breaks even exactly at the first Glosten–Milgrom half-spread.

Source: the model is that of Glosten & Milgrom (1985). The formulas above are derived here
from Bayes' rule; the paper's full text was not read, so that it states them in this form is
`from memory, unverified`. Code: `src/mm_sim/strategies/glosten_milgrom.py`. Tests:
`tests/test_informed_and_gm.py` (closed form, posterior after three trades by hand, zero mean
P&L, losing narrower fixed spread).

Two modelling details: the informed trader trades only at a profit, and the inventory limit in
the `two_point` scenario is above the number of steps, because a side closed by the limit
would make "no trade" informative, which the Bayes update above ignores.

## 12. The future-scramble test

`tests/test_lookahead.py`. An episode is rerun with the value path after step `t` replaced by
a different random path; all quotes up to and including `t` must be identical. Informed
traders keep their knowledge of the original path in the rerun, so their trades up to `t` do
not change and a difference can only come from the strategy. Every registered strategy is
tested in every world it runs in. The `clairvoyant` strategy, which reads the future through
`simulate_episode`'s test-only hook, fails the test, as it must.

## 13. Stale quotes: fixed spread with slow requoting (derived here, tested)

Assumptions: `fixed` strategy, noise traders only, inventory limit not binding, requote every
`m` steps. A quote posted at step `t0` from the value `V_{t0}` is still there at step
`t0 + j` (`j = 0 .. m−1`). Let `D_j = V_{t0+j} − V_{t0}`. The ask is now at distance
`d − D_j` from the current value and the bid at `d + D_j`. Noise traders fill a quote at
distance `x` with probability `p(x)`, which is close to 1 when `x` is very negative (the quote
is through the value), and such a fill earns `x` against the current value. After the fill
the value is a martingale. With `D_j` symmetric:

```
E[P&L]       = Σ_steps 2·E[g(d − D_age)],  g(x) = x·p(x)
E[pick-offs] = Σ_steps with age > 0  2·E[p(d − D_age); D_age > d]
```

`D_j` is a mixture: `N(0, σ²·j·dt)` from the diffusion plus `K` jumps of `±J`,
`K ~ Binomial(j, λ_J·dt)`. The expectations are computed by numerical integration over each
mixture component. Code: `theory.latency_mean_pnl`, `theory.latency_pick_offs`. Tests:
`tests/test_inventory_and_latency.py`. The full check is EXP-004.

A pick-off is defined in the accounting as a fill on a quote posted at an earlier step whose
edge at the fill is negative.

## 14. Avellaneda–Stoikov and skew (formulas from the paper, tested)

`avellaneda_stoikov` uses the paper's eq. (29) and (30) as quoted in section 8. Tests
(`tests/test_inventory_and_latency.py`): the spread for `γ = 0.1, σ = 2, k = 1.5, T − t = 1`
is `0.4 + 20·ln(1.0667) = 1.6908` by hand; the reservation price equals the mid at `q = 0`
and moves against the inventory symmetrically; the spread tends to `2/k` as `γ → 0`; the risk
part `γ·σ²·(T − t)` shrinks linearly to zero at `T`. Averaged over an episode the quoted spread
is `γ·σ²·T/2·(N+1)/N + (2/γ)·ln(1 + γ/k) = 1.49`, the value the paper reports for `γ = 0.1`.

`skew` shifts both `fixed` quotes by `−κ·q`; with `κ = 0` its fills are identical to `fixed`.
All three public-mid strategies pull the side that would breach the inventory limit.

## 8. References and what was checked

Checked on 2026-11-09 by opening the pages listed. "Metadata" means the bibliographic record
was seen, not the full text; nothing is cited from such a paper beyond its existence and topic.

| # | Reference | Status |
|---|---|---|
| 1 | Glosten, L. R. & Milgrom, P. R. (1985). Bid, ask and transaction prices in a specialist market with heterogeneously informed traders. *Journal of Financial Economics* 14(1), 71–100. doi:10.1016/0304-405X(85)90044-3 | Citation verified (metadata: IDEAS/RePEc, Crossref). Full text not read; formulas used in Stage B are derived here from Bayes' rule and labelled accordingly. |
| 2 | Kyle, A. S. (1985). Continuous auctions and insider trading. *Econometrica* 53(6), 1315–1335. doi:10.2307/1913210 | Citation verified (metadata: IDEAS/RePEc, Crossref). Full text not read. Background only; no formula used. |
| 3 | Ho, T. & Stoll, H. R. (1981). Optimal dealer pricing under transactions and return uncertainty. *Journal of Financial Economics* 9(1), 47–73. doi:10.1016/0304-405X(81)90020-9 | Citation verified (metadata: IDEAS/RePEc, Crossref). Full text not read. Background only; no formula used. |
| 4 | Avellaneda, M. & Stoikov, S. (2008). High-frequency trading in a limit order book. *Quantitative Finance* 8(3), 217–224. doi:10.1080/14697680701381228 | **Full text read** (journal PDF hosted at math.nyu.edu/~avellane/HighFrequencyTrading.pdf). See below. |
| 5 | Guéant, O., Lehalle, C.-A. & Fernandez-Tapia, J. (2013). Dealing with the inventory risk: a solution to the market making problem. *Mathematics and Financial Economics* 7(4), 477–507. doi:10.1007/s11579-012-0087-0. arXiv:1105.3115 | Citation verified (Crossref, arXiv). arXiv v5 read in part (pp. 1–10). No formula from it is used yet. |
| 6 | Cartea, Á., Jaimungal, S. & Penalva, J. (2015). *Algorithmic and High-Frequency Trading*. Cambridge University Press. | **Unverified.** The publisher's page could not be opened; authors, title, publisher and year are from the build prompt and search snippets only. No ISBN is given for that reason. |

### Avellaneda & Stoikov (2008): what the paper says

Read in the full text:

- Reservation price, eq. (8) and again eq. (29): `r(s, q, t) = s − q·γ·σ²·(T − t)`.
- Spread, eq. (30): `δ_a + δ_b = γ·σ²·(T − t) + (2/γ)·ln(1 + γ/k)`, set around the reservation
  price. The paper calls this an **approximate** solution (it comes from an expansion in the
  inventory `q`), not the exact optimum. Reports must say "the Avellaneda–Stoikov
  approximation", not "the optimal quotes".
- Arrival intensity, eq. (12) and (20): `λ(δ) = A·exp(−k·δ)`, the same on both sides.
- Simulation parameters, section 3.3: `s = 100, T = 1, σ = 2, dt = 0.005, q = 0, γ = 0.1,
  k = 1.5, A = 140`, 1000 simulations; also `γ = 0.01` and `γ = 1`. `config.yaml` uses these as
  the base values.

Where this simulator **differs** from the paper's simulation (so its tables are not a
regression target, and none of its table numbers are quoted here):

- The paper moves the mid by `±σ·√dt` (a binomial step); here the step is Gaussian.
- The paper fills with probability `λ(δ)·dt`; here it is `1 − exp(−λ(δ)·dt)`, which is the
  probability of at least one arrival in the step and can never exceed 1.
- Here quotes are rounded outwards to a tick grid and inventory is capped at `q_max`.

Guéant, Lehalle & Fernandez-Tapia treat the same model with an inventory bound and obtain
quotes that are nearly independent of time far from `T`; this is noted as a possible later
comparison, not implemented.
