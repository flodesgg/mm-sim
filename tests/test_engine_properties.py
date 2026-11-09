"""Exact and property-based tests of the engine, the flow and the accounting."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pytest
from helpers import make_cfg
from hypothesis import given, settings
from hypothesis import strategies as st

from mm_sim.accounting.pnl import episode_metrics
from mm_sim.config import Config
from mm_sim.engine.reference import simulate_episode
from mm_sim.engine.ticks import round_ask, round_bid
from mm_sim.flow.noise import NoiseFlow, fill_probability
from mm_sim.strategies import build_strategy


def _cfg(seed: int, half_spread: float, **overrides: Any) -> Config:
    base: dict[str, Any] = {
        "market": {"n_steps": 40},
        "analysis": {"seed": seed},
        "strategies": {"fixed": {"half_spread": half_spread}},
    }
    for section, values in overrides.items():
        base[section] = {**base.get(section, {}), **values}
    return make_cfg(**base)


def _episode(cfg: Config, episode: int = 0) -> tuple[Any, dict[str, float]]:
    strategy, _ = build_strategy(cfg, "fixed")
    res = simulate_episode(cfg, strategy, episode)
    return res, episode_metrics(cfg, res)


def test_zero_volatility_pnl_is_fills_times_half_spread() -> None:
    """sigma = 0, no informed traders, no fees: the value stays at 100, quotes are
    99.25 / 100.75 (h = 0.75 is on the 0.01 grid), so every fill earns exactly 0.75 and
    P&L = number of fills * 0.75. Example: 3 buys and 2 sells -> cash = 2*100.75 - 3*99.25
    = -96.25, inventory +1 marked at 100 -> P&L = 3.75 = 5 * 0.75."""
    cfg = _cfg(3, 0.75, market={"sigma": 0.0, "n_steps": 200})
    res, m = _episode(cfg)
    assert m["volume"] > 20  # the test is not vacuous
    assert {f.price for f in res.fills} == {99.25, 100.75}
    assert m["pnl_mtm"] == pytest.approx(m["volume"] * 0.75, abs=1e-9)
    assert m["spread_capture"] == pytest.approx(m["volume"] * 0.75, abs=1e-9)
    assert m["adverse_selection"] == 0.0 and m["inventory_pnl"] == 0.0


@settings(max_examples=60, deadline=None)
@given(
    seed=st.integers(0, 10_000),
    sigma=st.floats(0.0, 10.0),
    half_spread=st.floats(0.01, 3.0),
    tick=st.sampled_from([0.01, 0.05, 0.25, 1.0]),
    fee=st.floats(-0.05, 0.2),
    horizon=st.integers(1, 60),
    q_max=st.integers(1, 30),
    requote_every=st.integers(1, 5),
)
def test_decomposition_identity_and_inventory_limit(
    seed: int,
    sigma: float,
    half_spread: float,
    tick: float,
    fee: float,
    horizon: int,
    q_max: int,
    requote_every: int,
) -> None:
    cfg = _cfg(
        seed,
        half_spread,
        market={"sigma": sigma, "tick_size": tick},
        engine={"maker_fee": fee, "q_max": q_max, "requote_every": requote_every},
        accounting={"markout_horizon_steps": horizon},
    )
    res, m = _episode(cfg)
    parts = m["spread_capture"] + m["adverse_selection"] + m["inventory_pnl"] - m["fees"]
    assert parts == pytest.approx(m["pnl_mtm"], abs=1e-9)
    assert m["fees"] == pytest.approx(fee * m["volume"], abs=1e-9)
    assert np.abs(res.inventory).max() <= q_max
    assert m["max_abs_q"] <= q_max


@given(
    price=st.floats(1.0, 1000.0),
    half=st.floats(0.0, 10.0),
    tick=st.sampled_from([0.01, 0.05, 0.125, 0.25, 1.0]),
)
def test_outward_rounding_never_narrows_the_spread(price: float, half: float, tick: float) -> None:
    bid, ask = price - half, price + half
    rb, ra = round_bid(bid, tick), round_ask(ask, tick)
    snap = 1e-8 * tick  # a price within 1e-9 ticks of the grid counts as on the grid
    assert rb <= bid + snap and ra >= ask - snap
    assert ra - rb >= (ask - bid) - 2 * snap
    assert bid - rb < tick + snap and ra - ask < tick + snap  # and moves less than one tick
    for r in (rb, ra):  # the result is on the grid
        assert abs(r / tick - round(r / tick)) < 1e-6


def test_rounding_keeps_grid_prices() -> None:
    assert round_bid(99.25, 0.01) == 99.25
    assert round_ask(100.75, 0.01) == 100.75
    assert round_bid(99.254, 0.01) == 99.25
    assert round_ask(100.751, 0.01) == 100.76


@settings(max_examples=30, deadline=None)
@given(seed=st.integers(0, 10_000), fee=st.floats(0.0, 0.5), half_spread=st.floats(0.05, 2.0))
def test_positive_fees_never_improve_pnl(seed: int, fee: float, half_spread: float) -> None:
    _, free = _episode(_cfg(seed, half_spread))
    _, paid = _episode(_cfg(seed, half_spread, engine={"maker_fee": fee}))
    assert paid["volume"] == free["volume"]  # fees do not change who trades
    assert paid["pnl_mtm"] <= free["pnl_mtm"] + 1e-9
    assert paid["pnl_mtm"] == pytest.approx(free["pnl_mtm"] - fee * free["volume"], abs=1e-9)


@settings(max_examples=30, deadline=None)
@given(
    seed=st.integers(0, 10_000),
    narrow=st.floats(0.01, 2.0),
    extra=st.floats(0.0, 2.0),
)
def test_wider_spread_never_gets_more_fills(seed: int, narrow: float, extra: float) -> None:
    """Noise flow only, common random numbers, inventory limit not binding."""
    limit = {"q_max": 1000}
    res_n, m_n = _episode(_cfg(seed, narrow, engine=limit))
    res_w, m_w = _episode(_cfg(seed, narrow + extra, engine=limit))
    assert m_w["volume"] <= m_n["volume"]
    # stronger: every fill of the wide quote is also a fill of the narrow quote
    assert {(f.t, f.side) for f in res_w.fills} <= {(f.t, f.side) for f in res_n.fills}


@pytest.mark.parametrize(("bid_distance", "ask_distance"), [(0.5, 1.0), (0.0, 2.0)])
def test_empirical_fill_probability_matches_formula(
    bid_distance: float, ask_distance: float
) -> None:
    """10^5 steps at fixed distances; the fill frequency must be within 4 standard errors of
    p = 1 - exp(-A * exp(-k * distance) * dt)."""
    cfg = make_cfg()
    c, dt, n = cfg.flow.noise, cfg.market.dt, 100_000
    mids = np.full(n + 1, 100.0)
    flow = NoiseFlow.from_rng(c, dt, mids, np.random.default_rng(2024))
    hits = lifts = 0
    for t in range(n):
        hit, lift = flow.act(t, 100.0 - bid_distance, 100.0 + ask_distance)
        hits += hit
        lifts += lift
    for count, distance in ((hits, bid_distance), (lifts, ask_distance)):
        p = fill_probability(distance, c.A, c.k, dt)
        assert p == pytest.approx(1 - math.exp(-c.A * math.exp(-c.k * distance) * dt))
        assert abs(count / n - p) < 4 * math.sqrt(p * (1 - p) / n)


def test_noise_flow_measures_distance_from_the_current_mid() -> None:
    """A stale ask at 101 is 1.0 from a mid of 100 but 3.0 *inside* a mid of 104: the fill
    probability must use the current mid (draw 0.9 fills only in the second case)."""
    cfg = make_cfg()
    c, dt = cfg.flow.noise, cfg.market.dt
    flow = NoiseFlow(c, dt, np.array([100.0, 104.0, 104.0]), np.full((2, 2), 0.9))
    assert fill_probability(1.0, c.A, c.k, dt) < 0.9 < fill_probability(-3.0, c.A, c.k, dt)
    assert flow.act(0, None, 101.0) == (False, False)
    assert flow.act(1, None, 101.0) == (False, True)
    assert flow.act(1, None, None) == (False, False)  # a pulled side cannot trade
