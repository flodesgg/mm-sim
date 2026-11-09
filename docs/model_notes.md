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
the spread.

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
