"""The fast engine: the same model as the reference engine, vectorised over episodes.

One Python loop over the N steps; every operation inside it acts on all episodes at once with
numpy. It draws each episode's random numbers from the same streams as the reference engine,
so for the same seed it produces the same fills and the same per-episode table (prices and
P&L equal to floating-point rounding; tested in tests/test_fast_engine.py).

The reference engine (engine/reference.py) remains the source of truth. This engine covers
the public-mid world with the `fixed`, `skew` and `avellaneda_stoikov` strategies, noise and
informed flow, jumps, requote latency, the inventory limit and fees. It does not cover the
two-point world or the kill switch: for those `supports` is False and callers use the
reference engine.

Order of events per step (identical to the reference engine):
  1. requote if t % requote_every == 0 (quotes rounded outwards to the tick grid)
  2. informed traders act, then noise traders on the sides not yet filled
  3. fills are accounted with their counterparty type
  4. the value moves
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from mm_sim.accounting.pnl import COUNTERPARTIES, METRICS, markout_columns
from mm_sim.config import Config
from mm_sim.engine.reference import episode_values
from mm_sim.seeds import component_rng
from mm_sim.strategies.base import REGISTRY

Array = NDArray[np.float64]
FAST_STRATEGIES = ("fixed", "skew", "avellaneda_stoikov")


def supports(cfg: Config, strategy: str) -> bool:
    return (
        cfg.market.world == "public_mid"
        and strategy in FAST_STRATEGIES
        and cfg.engine.kill_switch_loss is None
    )


def _raw_quotes(
    cfg: Config, strategy: str, params: dict[str, object], mid: Array, q: Array, time_left: float
) -> tuple[Array, Array]:
    """The strategies' quote formulas for all episodes at once (before the limit and the
    tick rounding). Must stay equal to strategies/fixed.py, skew.py, avellaneda_stoikov.py."""
    if strategy == "fixed":
        h = float(params["half_spread"])  # type: ignore[arg-type]
        return mid - h, mid + h
    if strategy == "skew":
        h, kappa = float(params["half_spread"]), float(params["kappa"])  # type: ignore[arg-type]
        center = mid - kappa * q
        return center - h, center + h
    gamma = float(params["gamma"])  # type: ignore[arg-type]
    sigma, k = cfg.market.sigma, cfg.flow.noise.k
    r = mid - q * gamma * sigma**2 * time_left
    half = (gamma * sigma**2 * time_left + (2 / gamma) * np.log(1 + gamma / k)) / 2
    return r - half, r + half


def _round_outwards(bid: Array, ask: Array, tick: float) -> tuple[Array, Array]:
    """Same rule as engine/ticks.py: bid down, ask up, snapping within 1e-9 ticks."""
    bid = np.round(np.floor(np.round(bid / tick, 9)) * tick, 10)
    ask = np.round(np.ceil(np.round(ask / tick, 9)) * tick, 10)
    return bid, ask


def _fill_probability(distance: Array, A: float, k: float, dt: float) -> Array:
    with np.errstate(invalid="ignore"):
        return 1.0 - np.exp(-A * np.exp(np.minimum(-k * distance, 700.0)) * dt)


def run_monte_carlo_fast(
    cfg: Config, strategy: str, overrides: dict[str, object] | None = None,
    episodes: Iterable[int] | None = None,
) -> pd.DataFrame:  # fmt: skip
    """Same output as analysis.montecarlo.run_monte_carlo, computed for all episodes at once."""
    if not supports(cfg, strategy):
        raise ValueError(f"the fast engine does not cover strategy {strategy!r} in this config")
    merged = {**cfg.strategies.get(strategy, {}), **(overrides or {})}
    params = REGISTRY[strategy].Params.model_validate(merged).model_dump()
    order = list(range(cfg.analysis.episodes) if episodes is None else episodes)
    m, eng, noise, inf = cfg.market, cfg.engine, cfg.flow.noise, cfg.flow.informed
    seed, n, n_ep = cfg.analysis.seed, m.n_steps, len(order)
    horizons = cfg.accounting.markout_curve_horizons
    h_acc = cfg.accounting.markout_horizon_steps

    # the same random inputs as the reference engine, one stream per (episode, component)
    values = np.stack([episode_values(cfg, e) for e in order])  # (episodes, N + 1)
    draws = np.stack([component_rng(seed, e, "noise_fills").random((n, 2)) for e in order])
    informed_on = inf.intensity > 0
    if informed_on:
        arrivals = np.stack([component_rng(seed, e, "informed_arrivals").random(n) for e in order])
    v_end = values[:, n]

    def zeros() -> Array:
        return np.zeros(n_ep)

    q, cash, fees = zeros(), zeros(), zeros()
    spread, adverse, holding = zeros(), zeros(), zeros()
    buys, sells, picked, picked_edge = zeros(), zeros(), zeros(), zeros()
    max_abs_q, sum_abs_q, at_limit = zeros(), zeros(), zeros()
    expected_capture, spread_sum, spread_count = zeros(), zeros(), zeros()
    fills_by = {c: zeros() for c in COUNTERPARTIES}
    markouts = {(c, h): zeros() for c in COUNTERPARTIES for h in horizons}
    bid = np.full(n_ep, np.nan)
    ask = np.full(n_ep, np.nan)
    quoted_at = 0

    def account(mask: NDArray[np.bool_], side: int, price: Array, t: int, who: str) -> None:
        """Book the fills `mask` (market-maker side +1 bought / -1 sold) at `price`."""
        nonlocal q, cash, fees, spread, adverse, holding, buys, sells, picked, picked_edge
        v = values[:, t]
        later = values[:, min(t + h_acc, n)]
        px = np.where(mask, price, 0.0)
        edge = np.where(mask, side * (v - px), 0.0)
        q = q + side * mask
        cash = cash - np.where(mask, side * px + eng.maker_fee, 0.0)
        fees = fees + mask * eng.maker_fee
        spread = spread + edge
        adverse = adverse + np.where(mask, side * (later - v), 0.0)
        holding = holding + np.where(mask, side * (v_end - later), 0.0)
        if side > 0:
            buys = buys + mask
        else:
            sells = sells + mask
        if t > quoted_at:  # a stale quote on the wrong side of the value
            off = mask & (edge < 0)
            picked = picked + off
            picked_edge = picked_edge + np.where(off, edge, 0.0)
        fills_by[who] = fills_by[who] + mask
        for h in horizons:
            future = values[:, min(t + h, n)]
            markouts[(who, h)] = markouts[(who, h)] + np.where(mask, side * (future - px), 0.0)

    for t in range(n):
        v = values[:, t]
        # 1. requote
        if t % eng.requote_every == 0:
            raw_bid, raw_ask = _raw_quotes(cfg, strategy, params, v, q, (n - t) * m.dt)
            bid, ask = _round_outwards(raw_bid, raw_ask, m.tick_size)
            if np.any(bid >= ask):
                raise ValueError("crossed quotes")
            bid = np.where(q < eng.q_max, bid, np.nan)  # the strategy pulls the side at the limit
            ask = np.where(q > -eng.q_max, ask, np.nan)
            quoted_at = t
        has_bid, has_ask = ~np.isnan(bid), ~np.isnan(ask)
        d_bid, d_ask = v - bid, ask - v
        p_bid = _fill_probability(d_bid, noise.A, noise.k, m.dt)
        p_ask = _fill_probability(d_ask, noise.A, noise.k, m.dt)
        expected_capture += np.where(has_bid, d_bid * p_bid, 0.0) + np.where(
            has_ask, d_ask * p_ask, 0.0
        )
        both = has_bid & has_ask
        spread_sum += np.where(both, ask - bid, 0.0)
        spread_count += both

        # 2.-3. a side at the inventory limit at the start of the step is closed for the step
        bid_open = has_bid & (q < eng.q_max)
        ask_open = has_ask & (q > -eng.q_max)
        if informed_on:
            here = arrivals[:, t] < inf.intensity * m.dt
            future = values[:, min(t + inf.horizon_steps, n)]
            with np.errstate(invalid="ignore"):
                lift = here & ask_open & (ask < future - inf.threshold)
                hit = here & ~lift & bid_open & (bid > future + inf.threshold)
            account(hit, +1, bid, t, "informed")
            account(lift, -1, ask, t, "informed")
            bid_open, ask_open = bid_open & ~hit, ask_open & ~lift
        hit = bid_open & (draws[:, t, 0] < p_bid)
        lift = ask_open & (draws[:, t, 1] < p_ask)
        account(hit, +1, bid, t, "noise")
        account(lift, -1, ask, t, "noise")

        # 4. the value moves (the paths were drawn beforehand)
        abs_q = np.abs(q)
        max_abs_q = np.maximum(max_abs_q, abs_q)
        sum_abs_q += abs_q
        at_limit += abs_q >= eng.q_max

    pnl_mtm = cash + q * v_end
    liquidation = np.abs(q) * (eng.liq_half_spread + eng.liq_impact * np.abs(q))
    with np.errstate(invalid="ignore", divide="ignore"):
        quoted_spread = np.where(spread_count > 0, spread_sum / spread_count, np.nan)
    columns: dict[str, Array] = {
        "pnl_mtm": pnl_mtm,
        "pnl_liquidated": pnl_mtm - liquidation,
        "spread_capture": spread,
        "adverse_selection": adverse,
        "inventory_pnl": holding,
        "fees": fees,
        "buys": buys,
        "sells": sells,
        "volume": buys + sells,
        "max_abs_q": max_abs_q,
        "mean_abs_q": sum_abs_q / n,
        "terminal_q": q,
        "share_at_limit": at_limit / n,
        "noise_capture_expected": expected_capture,
        "mean_quoted_spread": quoted_spread,
        "picked_off": picked,
        "picked_off_edge": picked_edge,
    }
    for c in COUNTERPARTIES:
        columns[f"fills_{c}"] = fills_by[c]
    for (c, h), total in markouts.items():
        columns[f"markout_{c}_{h}"] = total
    names = [*METRICS, *markout_columns(cfg)]
    return pd.DataFrame(columns, index=pd.Index(order, name="episode"))[names]
