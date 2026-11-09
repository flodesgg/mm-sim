"""Stage B: informed flow, markouts, the two-point world and Glosten-Milgrom quotes."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
import pytest
from helpers import make_cfg
from hypothesis import given, settings
from hypothesis import strategies as st

from mm_sim.accounting.pnl import markout_sums
from mm_sim.analysis import theory
from mm_sim.analysis.markouts import markout_curve, ratio_ci
from mm_sim.analysis.montecarlo import run_monte_carlo, with_run_settings
from mm_sim.config import Config
from mm_sim.engine.reference import simulate_episode
from mm_sim.flow.glosten_milgrom import GMInformedFlow, GMNoiseFlow
from mm_sim.flow.informed import InformedFlow
from mm_sim.strategies import Observation, Trade, build_strategy
from mm_sim.strategies.clairvoyant import Clairvoyant
from mm_sim.strategies.glosten_milgrom import gm_quotes, posterior_after

TWO_POINT: dict[str, Any] = {
    "market": {"process": "two_point", "world": "trades_only", "n_steps": 100, "tick_size": 1e-6},
    "engine": {"q_max": 1000},
}


def _toxic(intensity: float = 40.0, **analysis: Any) -> Config:
    return make_cfg(
        flow={"informed": {"intensity": intensity, "horizon_steps": 50}},
        engine={"q_max": 200},
        accounting={"markout_horizon_steps": 50},
        analysis=analysis,
    )


# ---------------------------------------------------------------- informed flow


def test_informed_trader_decisions_by_hand() -> None:
    """Known path 100, 100, 103, 97; horizon 2; threshold 0.5; arrival probability 0.5.
    t=0 (draw 0.1, arrives; knows V_2 = 103): ask 101 < 103 - 0.5 -> buys.
    t=0 with ask 102.6: 102.6 < 102.5 is false; bid 99 > 103.5 false -> nothing.
    t=1 (draw 0.1; knows V_3 = 97): bid 99 > 97 + 0.5 -> sells; with bid 97.4 -> nothing.
    t=2 (draw 0.9 >= 0.5): no arrival. Horizon is clipped at the end: t=2 would know V_3."""
    cfg = make_cfg(
        flow={"informed": {"intensity": 100.0, "horizon_steps": 2, "threshold": 0.5}}
    ).flow.informed
    known = np.array([100.0, 100.0, 103.0, 97.0])
    flow = InformedFlow(cfg, 0.005, known, np.array([0.1, 0.1, 0.9]))
    assert flow.act(0, 99.0, 101.0) == (False, True)
    assert flow.act(0, 99.0, 102.6) == (False, False)
    assert flow.act(0, 99.0, None) == (False, False)  # a pulled ask cannot be lifted
    assert flow.act(1, 99.0, 101.0) == (True, False)
    assert flow.act(1, 97.4, 101.0) == (False, False)
    assert flow.act(2, 99.0, 101.0) == (False, False)
    clipped = InformedFlow(cfg, 0.005, known, np.array([0.1, 0.1, 0.1]))
    assert clipped.act(2, 97.6, 101.0) == (True, False)  # knows V_3 = 97, not beyond the end


@settings(max_examples=25, deadline=None)
@given(
    seed=st.integers(0, 10_000),
    half_spread=st.floats(0.02, 1.5),
    horizon=st.integers(1, 80),
    threshold=st.floats(0.0, 0.5),
    requote_every=st.integers(1, 4),
)
def test_informed_traders_never_trade_at_a_loss(
    seed: int, half_spread: float, horizon: int, threshold: float, requote_every: int
) -> None:
    """Every informed fill is profitable for the trader against V_{t+h} by more than c_I,
    i.e. the market maker's markout at the informed horizon is below -c_I."""
    cfg = make_cfg(
        market={"n_steps": 60},
        flow={"informed": {"intensity": 150.0, "horizon_steps": horizon, "threshold": threshold}},
        engine={"requote_every": requote_every},
        analysis={"seed": seed},
        strategies={"fixed": {"half_spread": half_spread}},
    )
    strategy, _ = build_strategy(cfg, "fixed")
    res = simulate_episode(cfg, strategy, 0)
    informed = [f for f in res.fills if f.counterparty == "informed"]
    for f in informed:
        future = float(res.values[min(f.t + horizon, cfg.market.n_steps)])
        assert f.side * (future - f.price) < -threshold + 1e-12
    assert all(f.counterparty in ("noise", "informed") for f in res.fills)


def test_simulated_mean_matches_theory_with_informed_flow() -> None:
    """Fixed strategy against noise + informed flow: mean P&L within 4 standard errors of
    theory.fixed_mean_pnl_with_informed (400 episodes, fixed seed), for a losing and a
    winning half-spread (theory: about -32 and +33 per episode at lambda_I = 120)."""
    cfg = with_run_settings(_toxic(intensity=120.0), 31, 400)
    means = {}
    for h in (0.05, 0.6):
        strategy, _ = build_strategy(cfg, "fixed", {"half_spread": h})
        pnl = run_monte_carlo(cfg, strategy)["pnl_mtm"]
        se = pnl.std(ddof=1) / math.sqrt(len(pnl))
        assert abs(pnl.mean() - theory.fixed_mean_pnl_with_informed(cfg, h)) < 4 * se
        means[h] = (pnl.mean(), se)
    assert means[0.05][0] + 4 * means[0.05][1] < 0  # too narrow: loses to informed flow
    assert means[0.6][0] - 4 * means[0.6][1] > 0


def test_theory_with_no_informed_traders_reduces_to_noise_only() -> None:
    cfg = make_cfg()
    assert theory.fixed_mean_pnl_with_informed(cfg, 0.5) == pytest.approx(
        theory.fixed_noise_mean_pnl(cfg, 0.5 + cfg.market.tick_size / 2, tick=0.0)
    )
    assert theory.break_even_half_spread(cfg) == 0.0


def test_break_even_half_spread_rises_with_informed_intensity() -> None:
    values = []
    for lam in (20.0, 80.0, 200.0):
        cfg = make_cfg(flow={"informed": {"intensity": lam, "horizon_steps": 50}})
        be = theory.break_even_half_spread(cfg)
        assert theory.fixed_mean_pnl_with_informed(cfg, be) == pytest.approx(0.0, abs=1e-6)
        assert theory.fixed_mean_pnl_with_informed(cfg, be / 2) < 0
        values.append(be)
    assert values == sorted(values) and values[0] > 0


# ---------------------------------------------------------------- markouts


def test_noise_markout_at_zero_equals_the_quoted_half_spread() -> None:
    """sigma = 0, mid 100 on the grid, h = 0.75: every noise fill is 0.75 from the value, at
    every horizon. With sigma > 0 the h=0 markout of a fill is its quote's rounded distance
    from the mid, between h and h + tick."""
    flat = with_run_settings(make_cfg(market={"sigma": 0.0}), 5, 20)
    strategy, _ = build_strategy(flat, "fixed", {"half_spread": 0.75})
    curve = markout_curve(flat, run_monte_carlo(flat, strategy))
    noise = curve[curve["counterparty"] == "noise"]
    assert noise["fills"].iloc[0] > 100
    np.testing.assert_allclose(noise["markout"], 0.75, atol=1e-12)

    cfg = with_run_settings(make_cfg(), 5, 1)
    tick = cfg.market.tick_size
    res = simulate_episode(cfg, strategy, 0)
    assert res.fills
    for f in res.fills:
        edge = f.side * (float(res.values[f.t]) - f.price)  # the h = 0 markout
        quoted = abs(f.price - float(res.values[f.t]))  # quote distance after rounding
        assert edge == pytest.approx(quoted, abs=1e-12)
        assert 0.75 - 1e-9 <= edge < 0.75 + tick + 1e-9


def test_markout_sums_by_hand() -> None:
    """The scripted episode of test_engine_steps, horizons 0 and 2, V_T = 103.
    Noise fills (d, price; V_t, V_{t+2}):       h=0    h=2
      t0 +1  99.0; 100, 101                     +1.0   +2.0
      t1 +1  99.0; 100, 101                     +1.0   +2.0
      t6 -1 100.5; 100, 100                     +0.5   +0.5
      t7 +1  99.5; 100, 100                     +0.5   +0.5
      t9 -1 100.5; 100, clipped 103             +0.5   -2.5      sums 3.5 and 2.5, 5 fills
    Informed fills:
      t1 -1 101.0; 100, 101                     +1.0    0.0
      t2 +1 100.5; 101, 102                     +0.5   +1.5
      t7 -1 100.5; 100, 100                     +0.5   +0.5      sums 2.0 and 2.0, 3 fills
    The h=0 sums add up to the spread capture 5.5."""
    from test_engine_steps import _run

    cfg, _, _, _, res = _run()
    m = markout_sums(cfg, res)
    assert (m["fills_noise"], m["fills_informed"]) == (5, 3)
    assert (m["markout_noise_0"], m["markout_noise_2"]) == pytest.approx((3.5, 2.5))
    assert (m["markout_informed_0"], m["markout_informed_2"]) == pytest.approx((2.0, 2.0))


def test_ratio_ci_by_hand() -> None:
    """Episodes with (sum, fills) = (2, 1), (2, 2), (5, 2): ratio 9/5 = 1.8.
    Residuals sum - 1.8*fills = 0.2, -1.6, 1.4: sample std sqrt(4.56/2) = 1.50997; mean fills
    5/3; se = 1.50997 / (sqrt(3) * 5/3) = 0.52307; t(0.975, 2) = 4.30265 -> half width 2.2506."""
    ratio, lo, hi = ratio_ci(pd.Series([2.0, 2.0, 5.0]), pd.Series([1.0, 2.0, 2.0]), 0.95)
    assert ratio == pytest.approx(1.8)
    assert (hi - lo) / 2 == pytest.approx(2.2506, abs=1e-3)
    assert math.isnan(ratio_ci(pd.Series([0.0]), pd.Series([0.0]), 0.95)[0])


def test_informed_markouts_turn_negative_and_noise_markouts_do_not() -> None:
    cfg = with_run_settings(_toxic(), 8, 200)
    strategy, _ = build_strategy(cfg, "fixed", {"half_spread": 0.4})
    curve = markout_curve(cfg, run_monte_carlo(cfg, strategy)).set_index(
        ["counterparty", "horizon"]
    )
    assert curve.loc[("informed", 0), "markout"] == pytest.approx(0.405, abs=0.005)
    assert curve.loc[("informed", 50), "ci_high"] < 0  # toxic at the informed horizon
    assert curve.loc[("noise", 50), "ci_low"] > 0.4


# ---------------------------------------------------------------- Glosten-Milgrom


def test_gm_first_spread_is_mu_times_value_range() -> None:
    """Prior 1/2: ask - bid = mu * (V_H - V_L) (derived in docs/model_notes.md, section 11).
    mu = 0.3, V = 99/101: bid 99.7, ask 100.3."""
    for mu, v_high, v_low in ((0.3, 101.0, 99.0), (0.8, 110.0, 90.0), (0.05, 100.5, 100.0)):
        bid, ask = gm_quotes(0.5, mu, v_high, v_low)
        assert ask - bid == pytest.approx(mu * (v_high - v_low))
        assert (ask + bid) / 2 == pytest.approx((v_high + v_low) / 2)
    assert gm_quotes(0.5, 0.3, 101.0, 99.0) == pytest.approx((99.7, 100.3))


def _obs(tape: tuple[Trade, ...]) -> Observation:
    return Observation(
        t=len(tape), time_left=1.0, inventory=0, cash=0.0, q_max=1000, mid=None,
        past_quotes=(), tape=tape,
    )  # fmt: skip


def test_gm_posterior_after_three_trades_by_hand() -> None:
    """mu = 0.3: P(buy|V_H) = 0.65, P(buy|V_L) = 0.35, prior 0.5.
    buy:  0.5*0.65 / (0.5*0.65 + 0.5*0.35) = 0.65
    buy:  0.65*0.65 / (0.65*0.65 + 0.35*0.35) = 0.4225 / 0.5450 = 0.775229
    sell: 0.775229*0.35 / (0.775229*0.35 + 0.224771*0.65) = 0.271330 / 0.417431 = 0.65
    Quotes at pi = 0.65: after a buy pi = 0.775229 -> ask = 99 + 2*0.775229 = 100.550459;
    after a sell pi = 0.65*0.35/(0.65*0.35 + 0.35*0.65) = 0.5 -> bid = 100.0."""
    assert posterior_after(0.5, +1, 0.3) == pytest.approx(0.65)
    assert posterior_after(0.65, +1, 0.3) == pytest.approx(0.775229, abs=1e-6)
    assert posterior_after(0.775229, -1, 0.3) == pytest.approx(0.65, abs=1e-6)

    cfg = make_cfg(**TWO_POINT)
    strategy, _ = build_strategy(cfg, "glosten_milgrom")
    tape = (Trade(0, 100.3, +1), Trade(1, 100.55, +1), Trade(2, 100.3, -1))
    quotes = strategy.quote(_obs(tape))
    assert (quotes.bid, quotes.ask) == pytest.approx((100.0, 100.550459), abs=1e-6)
    # the tape is processed incrementally and reset() forgets it
    assert strategy.quote(_obs(tape)) == quotes
    strategy.reset()
    first = strategy.quote(_obs(()))
    assert (first.bid, first.ask) == pytest.approx((99.7, 100.3))


def test_gm_flow_one_trader_per_step_and_informed_only_at_a_profit() -> None:
    known = np.full(4, 101.0)
    types = np.array([0.1, 0.9, 0.9])  # mu = 0.3: informed, noise, noise
    sides = np.array([0.9, 0.2, 0.7])  # noise: buy at t=1, sell at t=2
    informed, noise = GMInformedFlow(0.3, known, types), GMNoiseFlow(0.3, types, sides)
    assert informed.act(0, 99.7, 100.3) == (False, True)  # V = 101 > ask: buys
    assert noise.act(0, 99.7, 100.3) == (False, False)
    assert informed.act(0, 99.7, 101.0) == (False, False)  # ask = V: no profit, no trade
    assert informed.act(0, 101.5, 102.0) == (True, False)  # bid above V: sells to it
    assert informed.act(1, 99.7, 100.3) == (False, False)
    assert noise.act(1, 99.7, 100.3) == (False, True)
    assert noise.act(2, 99.7, 100.3) == (True, False)
    assert noise.act(2, None, 100.3) == (False, False)  # a pulled side cannot trade


def test_gm_market_maker_breaks_even_and_a_narrower_fixed_spread_loses() -> None:
    """600 episodes of 100 trades, fixed seed. Glosten-Milgrom: |mean P&L| < 4 se.
    Fixed quotes around the prior mean with h = 0.1 (GM's first half-spread is 0.3): each
    trade earns h - mu*(V_H - V_L)/2 = 0.1 - 0.3 on average -> -20 per episode, CI below 0.
    At h = 0.3 the fixed quotes break even as well."""
    cfg = with_run_settings(make_cfg(**TWO_POINT), 17, 600)

    def pnl(name: str, **params: float) -> tuple[float, float]:
        strategy, _ = build_strategy(cfg, name, params or None)
        x = run_monte_carlo(cfg, strategy)["pnl_mtm"]
        return float(x.mean()), float(x.std(ddof=1)) / math.sqrt(len(x))

    gm_mean, gm_se = pnl("glosten_milgrom")
    assert abs(gm_mean) < 4 * gm_se
    narrow_mean, narrow_se = pnl("fixed_prior", half_spread=0.1)
    assert narrow_mean + 4 * narrow_se < 0
    assert narrow_mean == pytest.approx(-20.0, abs=4 * narrow_se)
    even_mean, even_se = pnl("fixed_prior", half_spread=0.3)
    assert abs(even_mean) < 4 * even_se


def test_gm_quotes_stay_inside_the_value_range_and_converge() -> None:
    cfg = with_run_settings(make_cfg(**TWO_POINT), 3, 1)
    strategy, _ = build_strategy(cfg, "glosten_milgrom")
    res = simulate_episode(cfg, strategy, 0)
    v = float(res.values[0])
    assert (res.bids >= 99.0).all() and (res.asks <= 101.0 + 1e-6).all()
    assert (res.asks - res.bids)[-1] < (res.asks - res.bids)[0]  # the spread narrows
    assert abs((res.bids[-1] + res.asks[-1]) / 2 - v) < 0.1  # and the quotes find the value


# ---------------------------------------------------------------- clairvoyant (negative control)


def test_clairvoyant_is_not_registered_and_beats_the_fixed_strategy() -> None:
    from mm_sim.strategies import REGISTRY

    assert "clairvoyant" not in REGISTRY
    cfg = with_run_settings(make_cfg(), 21, 100)
    fixed, _ = build_strategy(cfg, "fixed", {"half_spread": 0.75})
    honest = run_monte_carlo(cfg, fixed)["pnl_mtm"]
    cheat = run_monte_carlo(cfg, Clairvoyant(half_spread=0.75, lookahead_steps=20))["pnl_mtm"]
    diff = cheat - honest  # paired on common random numbers
    assert diff.mean() - 4 * diff.std(ddof=1) / math.sqrt(len(diff)) > 0
