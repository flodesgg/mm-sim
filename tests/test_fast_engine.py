"""Stage F: the fast engine must give the reference engine's results for the same seeds."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from helpers import make_cfg
from hypothesis import given, settings
from hypothesis import strategies as st
from test_experiments_and_cli import _workspace

from mm_sim.analysis.montecarlo import run_monte_carlo, with_run_settings
from mm_sim.cli import main
from mm_sim.config import Config, load_config
from mm_sim.engine.fast import FAST_STRATEGIES, run_monte_carlo_fast, supports
from mm_sim.strategies import build_strategy

REPO = Path(__file__).resolve().parents[1]
COUNTS = ["buys", "sells", "volume", "terminal_q", "max_abs_q", "picked_off",
          "fills_noise", "fills_informed"]  # fmt: skip


def assert_same(cfg: Config, strategy: str, params: dict[str, object] | None = None) -> None:
    built, _ = build_strategy(cfg, strategy, params)
    reference = run_monte_carlo(cfg, built)
    fast = run_monte_carlo_fast(cfg, strategy, params)
    assert list(fast.columns) == list(reference.columns)
    # every fill is the same: all counts are exactly equal
    pd.testing.assert_frame_equal(fast[COUNTS], reference[COUNTS], check_exact=True)
    # prices and P&L agree to floating-point rounding
    pd.testing.assert_frame_equal(fast, reference, check_exact=False, rtol=1e-9, atol=1e-9)


@pytest.mark.parametrize("scenario", ["baseline", "toxic", "inventory", "jumpy"])
@pytest.mark.parametrize("strategy", FAST_STRATEGIES)
def test_fast_engine_matches_reference_on_the_repo_scenarios(scenario: str, strategy: str) -> None:
    cfg, _ = load_config(REPO / "config.yaml", scenario)
    assert_same(with_run_settings(cfg, 7, 40), strategy)


@settings(max_examples=25, deadline=None)
@given(
    seed=st.integers(0, 10_000),
    strategy=st.sampled_from(FAST_STRATEGIES),
    sigma=st.floats(0.0, 6.0),
    tick=st.sampled_from([0.01, 0.05, 0.25]),
    fee=st.floats(-0.05, 0.2),
    q_max=st.integers(1, 12),
    requote_every=st.integers(1, 6),
    intensity=st.sampled_from([0.0, 60.0, 200.0]),
    horizon=st.integers(1, 40),
    threshold=st.floats(0.0, 0.3),
    jump_intensity=st.sampled_from([0.0, 10.0]),
    liq=st.floats(0.0, 0.5),
)
def test_fast_engine_matches_reference_on_random_configs(
    seed: int,
    strategy: str,
    sigma: float,
    tick: float,
    fee: float,
    q_max: int,
    requote_every: int,
    intensity: float,
    horizon: int,
    threshold: float,
    jump_intensity: float,
    liq: float,
) -> None:
    """Small inventory limits (so the limit binds), fees, latency, informed flow and jumps."""
    overrides: dict[str, Any] = {
        "market": {
            "n_steps": 60,
            "sigma": sigma,
            "tick_size": tick,
            "process": "jump_diffusion",
            "jump": {"intensity": jump_intensity, "size": 1.0},
        },
        "flow": {
            "informed": {"intensity": intensity, "horizon_steps": horizon, "threshold": threshold}
        },
        "engine": {
            "maker_fee": fee,
            "q_max": q_max,
            "requote_every": requote_every,
            "liq_half_spread": liq,
            "liq_impact": liq / 10,
        },
        "accounting": {"markout_horizon_steps": horizon},
    }
    assert_same(with_run_settings(make_cfg(**overrides), seed, 6), strategy)


def test_fast_engine_respects_episode_order_and_overrides() -> None:
    cfg = with_run_settings(make_cfg(), 5, 12)
    full = run_monte_carlo_fast(cfg, "fixed", {"half_spread": 0.4})
    subset = run_monte_carlo_fast(cfg, "fixed", {"half_spread": 0.4}, [9, 2])
    pd.testing.assert_frame_equal(subset, full.loc[[9, 2]], check_exact=True)
    assert_same(cfg, "skew", {"half_spread": 0.3, "kappa": 0.2})
    assert_same(cfg, "avellaneda_stoikov", {"gamma": 1.0})


def test_fast_engine_says_what_it_does_not_cover() -> None:
    two_point = make_cfg(market={"process": "two_point", "world": "trades_only"})
    assert not supports(two_point, "glosten_milgrom")
    assert not supports(make_cfg(), "glosten_milgrom")
    assert not supports(make_cfg(engine={"kill_switch_loss": 10.0}), "fixed")
    assert supports(make_cfg(), "fixed")
    with pytest.raises(ValueError, match="does not cover"):
        run_monte_carlo_fast(make_cfg(engine={"kill_switch_loss": 10.0}), "fixed")


def test_cli_run_with_the_fast_engine_gives_the_same_episodes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = _workspace(tmp_path)
    base = ["run", "--config", str(config), "--scenario", "toxic", "--strategy", "skew"]
    assert main([*base, "--episodes", "20", "--seed", "3", "--engine", "fast"]) == 0
    assert main([*base, "--episodes", "20", "--seed", "3"]) == 0
    first, second = sorted((tmp_path / "reports" / "runs").iterdir())
    a = pd.read_csv(first / "episodes.csv", index_col="episode")
    b = pd.read_csv(second / "episodes.csv", index_col="episode")
    pd.testing.assert_frame_equal(a, b, check_exact=False, rtol=1e-9, atol=1e-9)
    capsys.readouterr()
    args = ["run", "--config", str(config), "--scenario", "two_point", "--engine", "fast"]
    assert main([*args, "--strategy", "glosten_milgrom"]) == 2
    assert "use --engine reference" in capsys.readouterr().err


def test_cli_benchmark_and_reproduce_all(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = _workspace(tmp_path)
    assert main(["benchmark", "--config", str(config), "--episodes", "5", "--repeats", "1"]) == 0
    table = pd.read_csv(tmp_path / "reports" / "benchmark" / "benchmark.csv")
    assert set(table["strategy"]) == set(FAST_STRATEGIES)
    assert "two_point" not in set(table["scenario"])
    assert (table["max_abs_difference"] < 1e-9).all()
    assert (table["fast_steps_per_sec"] > 0).all()
    # nothing finished in this workspace: `reproduce all` has nothing to do and succeeds
    assert main(["reproduce", "all", "--config", str(config)]) == 0
