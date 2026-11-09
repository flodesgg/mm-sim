"""Determinism, statistics, theory checks and the stored regression scenario."""

from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from helpers import make_cfg

from mm_sim.analysis import theory
from mm_sim.analysis.montecarlo import run_monte_carlo, with_run_settings
from mm_sim.analysis.stats import certainty_equivalent, mean_ci, summarize
from mm_sim.config import Config
from mm_sim.seeds import component_rng
from mm_sim.strategies import build_strategy

FIXTURE = Path(__file__).parent / "fixtures" / "regression_fixed_seed7.csv"


def _mc(cfg: Config, episodes: list[int] | None = None, **params: object) -> pd.DataFrame:
    strategy, _ = build_strategy(cfg, "fixed", params or None)
    return run_monte_carlo(cfg, strategy, episodes)


def test_same_seed_gives_byte_identical_output() -> None:
    cfg = with_run_settings(make_cfg(market={"n_steps": 50}), seed=11, episodes=15)
    assert _mc(cfg).to_csv() == _mc(cfg).to_csv()
    other = with_run_settings(cfg, seed=12, episodes=15)
    assert _mc(cfg).to_csv() != _mc(other).to_csv()


def test_episode_results_do_not_depend_on_order_or_subset() -> None:
    cfg = with_run_settings(make_cfg(market={"n_steps": 50}), seed=11, episodes=12)
    full = _mc(cfg)
    order = [7, 2, 11, 0, 5, 9, 1, 10, 3, 8, 6, 4]
    shuffled = _mc(cfg, order)
    pd.testing.assert_frame_equal(shuffled.sort_index(), full, check_exact=True)
    pd.testing.assert_frame_equal(_mc(cfg, [9]), full.loc[[9]], check_exact=True)


def test_streams_differ_between_components_and_episodes() -> None:
    draws = {
        (e, c): component_rng(5, e, c).random()
        for e in (0, 1)
        for c in ("value", "noise_fills", "informed_arrivals")
    }
    assert len(set(draws.values())) == len(draws)
    assert component_rng(5, 1, "value").random() == draws[(1, "value")]


def test_common_random_numbers_same_value_path_for_two_strategies() -> None:
    """Two half-spreads on one seed see the same value path: with noise flow only, the wide
    quote's fills are a subset of the narrow one's (checked in test_engine_properties) and the
    terminal value is identical, so inventory P&L differs only through the fills."""
    from mm_sim.engine.reference import simulate_episode

    cfg = with_run_settings(make_cfg(), seed=3, episodes=1)
    a, _ = build_strategy(cfg, "fixed", {"half_spread": 0.3})
    b, _ = build_strategy(cfg, "fixed", {"half_spread": 1.2})
    np.testing.assert_array_equal(
        simulate_episode(cfg, a, 4).values, simulate_episode(cfg, b, 4).values
    )


def test_inventory_pnl_is_zero_on_average_on_a_martingale() -> None:
    """Noise flow only, random-walk value: what the inventory earns after the fill has mean 0.
    400 episodes, fixed seed, tolerance 4 standard errors."""
    cfg = with_run_settings(make_cfg(), seed=2025, episodes=400)
    ep = _mc(cfg)
    for column in ("inventory_pnl", "adverse_selection"):
        x = ep[column]
        assert abs(x.mean()) < 4 * x.std(ddof=1) / math.sqrt(len(x)), column
    mean, lo, hi = mean_ci(ep["inventory_pnl"] + ep["adverse_selection"], 0.95)
    assert abs(mean) < 4 * (hi - lo) / (2 * 1.96)


def test_simulated_mean_and_std_match_the_closed_form() -> None:
    """Fixed strategy, noise only: mean P&L within 4 standard errors of the formula, and the
    std within 10% (400 episodes, fixed seed)."""
    cfg = with_run_settings(make_cfg(), seed=77, episodes=400)
    for h in (0.3, 0.9):
        pnl = _mc(cfg, half_spread=h)["pnl_mtm"]
        se = pnl.std(ddof=1) / math.sqrt(len(pnl))
        assert abs(pnl.mean() - theory.fixed_noise_mean_pnl(cfg, h)) < 4 * se
        assert pnl.std(ddof=1) == pytest.approx(theory.fixed_noise_pnl_std(cfg, h), rel=0.10)


def test_theory_closed_form_without_tick() -> None:
    cfg = make_cfg()
    c, m, h = cfg.flow.noise, cfg.market, 0.5
    expected = m.n_steps * 2 * h * (1 - math.exp(-c.A * math.exp(-c.k * h) * m.dt))
    assert theory.fixed_noise_mean_pnl(cfg, h, tick=0.0) == pytest.approx(expected)
    # averaging over the tick offset is close to evaluating at h + tick/2
    assert theory.fixed_noise_mean_pnl(cfg, h) == pytest.approx(
        theory.fixed_noise_mean_pnl(cfg, h + m.tick_size / 2, tick=0.0), rel=1e-4
    )


def test_optimal_half_spread_tends_to_one_over_k_for_small_dt() -> None:
    """For A*dt -> 0 the expected P&L per step is 2*h*A*exp(-k*h)*dt, maximised at h = 1/k."""
    small = make_cfg(market={"dt": 1e-6})
    assert theory.optimal_fixed_half_spread(small) == pytest.approx(1 / 1.5, rel=1e-3)
    base = make_cfg()  # A*dt = 0.7 is not small: the optimum is wider than 1/k
    assert theory.optimal_fixed_half_spread(base) > 1 / 1.5


def test_mean_ci_hand_example() -> None:
    """x = 1..5: mean 3, sample std sqrt(2.5), se = sqrt(0.5), t(0.975, 4) = 2.776445."""
    mean, lo, hi = mean_ci([1, 2, 3, 4, 5], 0.95)
    half = 2.776445 * math.sqrt(0.5)
    assert mean == 3
    assert (lo, hi) == pytest.approx((3 - half, 3 + half), abs=1e-5)


def test_certainty_equivalent() -> None:
    """Constant payoff: CE = the payoff. Two-point payoff {0, 2} with gamma = 1:
    CE = -ln((1 + e^-2)/2) = 0.566219. Large payoffs must not overflow (log-sum-exp)."""
    assert certainty_equivalent([5.0, 5.0, 5.0], 0.1) == pytest.approx(5.0)
    assert certainty_equivalent([0.0, 2.0], 1.0) == pytest.approx(0.566219, abs=1e-6)
    assert certainty_equivalent([-1e4, 1e4], 1.0) == pytest.approx(-1e4 + math.log(2))
    x = np.random.default_rng(0).normal(10.0, 2.0, 200_000)
    assert certainty_equivalent(x, 0.5) == pytest.approx(10.0 - 0.5 * 4.0 / 2, abs=0.05)
    assert certainty_equivalent(x, 0.5) < x.mean()  # risk costs something


def test_summarize_hand_example() -> None:
    x = list(range(1, 101))  # 1..100
    s = summarize(x, 0.95, 0.1)
    assert s["mean"] == 50.5
    assert s["q05"] == pytest.approx(5.95)
    assert s["es05"] == pytest.approx(3.0)  # mean of 1..5
    assert s["p_loss"] == 0.0
    assert s["sharpe_per_episode"] == pytest.approx(50.5 / np.std(x, ddof=1))


def test_regression_scenario_matches_stored_results() -> None:
    """20 episodes x 200 steps, seed 7, fixed h = 0.75. Regenerate only on purpose:
    MM_SIM_REGENERATE_FIXTURES=1 uv run pytest -k regression  (say why in the commit)."""
    cfg = with_run_settings(make_cfg(), seed=7, episodes=20)
    ep = _mc(cfg, half_spread=0.75)
    if os.environ.get("MM_SIM_REGENERATE_FIXTURES") == "1":
        ep.to_csv(FIXTURE, float_format="%.12g")
    stored = pd.read_csv(FIXTURE, index_col="episode").astype(float)
    # columns added later (e.g. markouts) are not in the fixture; the stored ones must not move
    pd.testing.assert_frame_equal(
        ep[list(stored.columns)], stored, check_exact=False, rtol=1e-10, atol=1e-10
    )
