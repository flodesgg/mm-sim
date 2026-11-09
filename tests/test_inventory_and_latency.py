"""Stage C: skew, Avellaneda-Stoikov, jumps, stale quotes, paired comparisons."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
import pytest
from helpers import make_cfg

from mm_sim.analysis import theory
from mm_sim.analysis.montecarlo import run_monte_carlo, with_run_settings
from mm_sim.analysis.stats import bootstrap_ci, paired_comparison
from mm_sim.config import Config
from mm_sim.engine.reference import episode_values, simulate_episode
from mm_sim.market.value import jump_increments, random_walk_path
from mm_sim.seeds import component_rng
from mm_sim.strategies import Observation, Quotes, build_strategy
from mm_sim.strategies.avellaneda_stoikov import reservation_price, total_spread

JUMPY: dict[str, Any] = {
    "market": {"process": "jump_diffusion", "jump": {"intensity": 5.0, "size": 1.0}},
    "engine": {"requote_every": 5, "q_max": 200},
}


def _obs(q: int = 0, mid: float = 100.0, time_left: float = 1.0, q_max: int = 50) -> Observation:
    return Observation(
        t=0, time_left=time_left, inventory=q, cash=0.0, q_max=q_max, mid=mid,
        past_quotes=(), tape=(),
    )  # fmt: skip


def _mc(cfg: Config, name: str, **params: float) -> pd.DataFrame:
    strategy, _ = build_strategy(cfg, name, params or None)
    return run_monte_carlo(cfg, strategy)


# ---------------------------------------------------------------- Avellaneda-Stoikov


def test_as_spread_by_hand() -> None:
    """gamma = 0.1, sigma = 2, k = 1.5, T - t = 1:
    risk part  gamma*sigma^2*(T-t) = 0.1*4*1 = 0.4
    flow part  (2/gamma)*ln(1 + gamma/k) = 20*ln(1.0666667) = 20*0.0645385 = 1.290770
    total 1.690770. With q = 3: r = 100 - 3*0.1*4*1 = 98.8."""
    assert total_spread(0.1, 2.0, 1.5, 1.0) == pytest.approx(1.690770, abs=1e-6)
    assert reservation_price(100.0, 3, 0.1, 2.0, 1.0) == pytest.approx(98.8)
    strategy, _ = build_strategy(make_cfg(), "avellaneda_stoikov", {"gamma": 0.1})
    quotes = strategy.quote(_obs(q=3))
    assert (quotes.bid, quotes.ask) == pytest.approx((98.8 - 0.845385, 98.8 + 0.845385), abs=1e-6)


def test_as_reservation_price_and_inventory_direction() -> None:
    strategy, _ = build_strategy(make_cfg(), "avellaneda_stoikov", {"gamma": 0.1})
    flat, long, short = (strategy.quote(_obs(q=q)) for q in (0, 5, -5))
    assert flat.bid is not None and flat.ask is not None
    assert (flat.bid + flat.ask) / 2 == pytest.approx(100.0)  # q = 0: centred on the mid
    assert long.bid < flat.bid and long.ask < flat.ask  # long: both quotes lower
    assert short.bid > flat.bid and short.ask > flat.ask  # short: both higher
    assert flat.bid - long.bid == pytest.approx(short.bid - flat.bid)  # symmetric
    assert long.ask - long.bid == pytest.approx(flat.ask - flat.bid)  # the spread ignores q


def test_as_limits_small_gamma_and_end_of_horizon() -> None:
    assert total_spread(1e-6, 2.0, 1.5, 1.0) == pytest.approx(2 / 1.5, abs=1e-5)  # -> 2/k
    risk_parts = [
        total_spread(0.1, 2.0, 1.5, tl) - total_spread(0.1, 2.0, 1.5, 0.0)
        for tl in (1.0, 0.5, 0.1, 0.0)
    ]
    assert risk_parts == pytest.approx([0.4, 0.2, 0.04, 0.0])  # gamma*sigma^2*(T-t) shrinks
    assert reservation_price(100.0, 5, 0.1, 2.0, 0.0) == 100.0  # no skew left at T


def test_as_average_spread_matches_the_formula() -> None:
    """Averaged over the episode the risk part is gamma*sigma^2 * mean(T - t) with
    mean(T - t) = dt*(N + 1)/2 = 0.5025, so the spread is 0.201 + 1.29077 = 1.4918, plus
    about one tick (0.01) of outward rounding."""
    cfg = with_run_settings(make_cfg(), 3, 5)
    spread = _mc(cfg, "avellaneda_stoikov", gamma=0.1)["mean_quoted_spread"].mean()
    assert spread == pytest.approx(1.4918 + 0.01, abs=0.003)


# ---------------------------------------------------------------- skew and the limit


def test_skew_with_zero_kappa_is_the_fixed_strategy() -> None:
    cfg = with_run_settings(make_cfg(), 9, 1)
    fixed, _ = build_strategy(cfg, "fixed", {"half_spread": 0.6})
    skew, _ = build_strategy(cfg, "skew", {"half_spread": 0.6, "kappa": 0.0})
    for episode in range(3):
        a, b = simulate_episode(cfg, fixed, episode), simulate_episode(cfg, skew, episode)
        assert a.fills == b.fills and len(a.fills) > 0
        np.testing.assert_array_equal(a.bids, b.bids)
        np.testing.assert_array_equal(a.asks, b.asks)


def test_skew_shifts_both_quotes_against_the_inventory() -> None:
    strategy, _ = build_strategy(make_cfg(), "skew", {"half_spread": 0.5, "kappa": 0.1})
    assert strategy.quote(_obs(q=0)) == Quotes(99.5, 100.5)
    assert strategy.quote(_obs(q=4)) == Quotes(99.1, 100.1)  # long 4: 0.4 lower
    assert strategy.quote(_obs(q=-4)) == Quotes(99.9, 100.9)


@pytest.mark.parametrize("name", ["fixed", "skew", "avellaneda_stoikov"])
def test_strategies_pull_the_side_at_the_inventory_limit(name: str) -> None:
    strategy, _ = build_strategy(make_cfg(), name)
    at_long_limit = strategy.quote(_obs(q=50, q_max=50))
    assert at_long_limit.bid is None and at_long_limit.ask is not None
    at_short_limit = strategy.quote(_obs(q=-50, q_max=50))
    assert at_short_limit.ask is None and at_short_limit.bid is not None


def test_inventory_management_cuts_risk_on_common_random_numbers() -> None:
    """Skew and Avellaneda-Stoikov against fixed quotes, same seed, 300 episodes: smaller
    terminal inventory and smaller P&L std."""
    cfg = with_run_settings(make_cfg(), 13, 300)
    fixed = _mc(cfg, "fixed", half_spread=0.75)
    for name, params in (("skew", {"half_spread": 0.75, "kappa": 0.05}),
                         ("avellaneda_stoikov", {"gamma": 0.1})):  # fmt: skip
        managed = _mc(cfg, name, **params)
        assert managed["terminal_q"].std() < 0.6 * fixed["terminal_q"].std()
        assert managed["pnl_mtm"].std() < 0.8 * fixed["pnl_mtm"].std()


# ---------------------------------------------------------------- jumps and latency


def test_jump_increments_frequency_and_size() -> None:
    cfg = make_cfg(market={"process": "jump_diffusion", "n_steps": 200_000,
                           "jump": {"intensity": 20.0, "size": 1.5}}).market  # fmt: skip
    jumps = jump_increments(cfg, np.random.default_rng(1))
    p = 20.0 * cfg.dt  # 0.1 per step
    share = float((jumps != 0).mean())
    assert abs(share - p) < 4 * math.sqrt(p * (1 - p) / cfg.n_steps)
    assert set(np.unique(jumps)) == {-1.5, 0.0, 1.5}
    ups = float((jumps > 0).sum() / (jumps != 0).sum())
    assert abs(ups - 0.5) < 4 * math.sqrt(0.25 / (jumps != 0).sum())


def test_normal_jump_sizes() -> None:
    jump = {"intensity": 100.0, "size": 2.0, "size_dist": "normal"}
    cfg = make_cfg(market={"process": "jump_diffusion", "n_steps": 200_000, "jump": jump}).market
    jumps = jump_increments(cfg, np.random.default_rng(2))
    sizes = jumps[jumps != 0]
    assert sizes.std() == pytest.approx(2.0, rel=0.02)
    assert abs(sizes.mean()) < 4 * 2.0 / math.sqrt(len(sizes))


def test_jump_path_is_the_random_walk_plus_the_jumps() -> None:
    cfg = make_cfg(**JUMPY)
    path = episode_values(cfg, 0)
    walk = random_walk_path(cfg.market, component_rng(cfg.analysis.seed, 0, "value"))
    jumps = jump_increments(cfg.market, component_rng(cfg.analysis.seed, 0, "jumps"))
    np.testing.assert_allclose(path[1:] - walk[1:], np.cumsum(jumps), atol=1e-12)
    assert path[0] == cfg.market.s0


def test_stale_quotes_are_picked_off_right_after_jumps() -> None:
    """Jumps of 1.0 against a half-spread of 0.75, requote every 5 steps. Over 200 episodes:
    most pick-offs happen on quotes that a jump went through since they were posted, those
    fills have a negative edge at the fill and a negative markout at short horizons, and
    with requote_every = 1 there are no pick-offs at all."""
    cfg = with_run_settings(make_cfg(**JUMPY), 5, 200)
    strategy, _ = build_strategy(cfg, "fixed")
    every = cfg.engine.requote_every
    after_jump = other = 0
    edges, markouts_2 = [], []
    for episode in range(cfg.analysis.episodes):
        res = simulate_episode(cfg, strategy, episode)
        jumps = jump_increments(cfg.market, component_rng(cfg.analysis.seed, episode, "jumps"))
        for f in res.fills:
            edge = f.side * (res.values[f.t] - f.price)
            if f.quote_age > 0 and edge < 0:
                posted = f.t - f.quote_age
                assert posted % every == 0
                jumped = bool((jumps[posted : f.t] != 0).any())  # moves since the quote
                after_jump += jumped
                other += not jumped
                edges.append(edge)
                markouts_2.append(f.side * (res.values[min(f.t + 2, len(res.bids))] - f.price))
    assert after_jump > 300 and after_jump > 3 * other
    assert np.mean(edges) < -0.1
    assert np.mean(markouts_2) + 4 * np.std(markouts_2) / math.sqrt(len(markouts_2)) < 0

    fresh = with_run_settings(make_cfg(**{**JUMPY, "engine": {"requote_every": 1}}), 5, 50)
    assert _mc(fresh, "fixed")["picked_off"].sum() == 0


def test_latency_theory_reduces_to_the_noise_only_formula() -> None:
    cfg = make_cfg()  # no jumps, requote every step: every quote has age 0
    d = 0.75 + cfg.market.tick_size / 2
    assert theory.latency_mean_pnl(cfg, 0.75) == pytest.approx(
        theory.fixed_noise_mean_pnl(cfg, d, tick=0.0)
    )
    assert theory.latency_pick_offs(cfg, 0.75) == 0.0


def test_simulated_latency_matches_theory() -> None:
    """Mean P&L and pick-offs within 4 standard errors (400 episodes, fixed seed), for
    requote_every 5 and 20; slower requoting earns less."""
    means = []
    for every in (5, 20):
        cfg = with_run_settings(
            make_cfg(**{**JUMPY, "engine": {"requote_every": every, "q_max": 200}}), 23, 400
        )
        ep = _mc(cfg, "fixed")
        for column, expected in (
            ("pnl_mtm", theory.latency_mean_pnl(cfg, 0.75)),
            ("picked_off", theory.latency_pick_offs(cfg, 0.75)),
        ):
            x = ep[column]
            assert abs(x.mean() - expected) < 4 * x.std(ddof=1) / math.sqrt(len(x)), column
        means.append(theory.latency_mean_pnl(cfg, 0.75))
    assert (
        means[1]
        < means[0]
        < theory.latency_mean_pnl(
            make_cfg(
                **JUMPY,
            ),
            0.75,
        )
        + 1e-9
    )


# ---------------------------------------------------------------- paired statistics


def test_paired_comparison_by_hand() -> None:
    """a = 10, 12, 9, 15; b = 8, 11, 9, 12. Differences 2, 1, 0, 3: mean 1.5, sample std
    1.29099, se 0.645497, t(0.975, 3) = 3.18245 -> half width 2.05426.
    Unpaired: var(a) = 7, var(b) = 3.3333; se = sqrt(7/4 + 3.3333/4) = 1.60728,
    t(0.975, 6) = 2.44691 -> half width 3.93287. Ratio 0.52233."""
    r = paired_comparison([10, 12, 9, 15], [8, 11, 9, 12], 0.95)
    assert r["mean_diff"] == pytest.approx(1.5)
    assert (r["ci_high"] - r["ci_low"]) / 2 == pytest.approx(2.05426, abs=1e-4)
    assert (r["unpaired_ci_high"] - r["unpaired_ci_low"]) / 2 == pytest.approx(3.93287, abs=1e-4)
    assert r["ci_width_ratio"] == pytest.approx(0.52233, abs=1e-4)
    assert r["correlation"] > 0.8


def test_common_random_numbers_narrow_the_confidence_interval() -> None:
    cfg = with_run_settings(make_cfg(), 13, 200)
    a = _mc(cfg, "fixed", half_spread=0.7)["pnl_mtm"]
    b = _mc(cfg, "fixed", half_spread=0.8)["pnl_mtm"]
    r = paired_comparison(a, b, 0.95)
    assert r["ci_width_ratio"] < 0.5  # same paths, same traders: the difference is much less noisy


def test_bootstrap_ci_is_deterministic_and_covers_a_known_std() -> None:
    x = np.random.default_rng(0).normal(0.0, 3.0, 2000)
    lo, hi = bootstrap_ci(lambda i: float(x[i].std(ddof=1)), len(x), 0.95, 1, 500)
    assert lo < 3.0 < hi and hi - lo < 0.5
    assert (lo, hi) == bootstrap_ci(lambda i: float(x[i].std(ddof=1)), len(x), 0.95, 1, 500)
