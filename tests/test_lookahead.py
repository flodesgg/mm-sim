"""Future-scramble test: no strategy's quotes may depend on the future of the true value.

Run an episode. Rerun it with the value path after step t replaced by a different random
path, keeping every random stream and everything up to step t the same. Every quote up to
and including step t must be identical. The `clairvoyant` strategy must FAIL this test:
a test that cannot fail proves nothing.

The informed traders legitimately know the future, so in the rerun they keep their knowledge
of the ORIGINAL path: their trades up to step t are then unchanged, and any difference in the
quotes can only come from the strategy itself looking ahead.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from helpers import make_cfg
from numpy.typing import NDArray

from mm_sim.config import Config
from mm_sim.engine.reference import EpisodeResult, build_flows, episode_values, run_episode
from mm_sim.market.value import random_walk_path
from mm_sim.strategies import REGISTRY, Strategy, build_strategy
from mm_sim.strategies.clairvoyant import Clairvoyant

WORLDS: dict[str, dict[str, Any]] = {
    "noise_only": {},
    "informed": {"flow": {"informed": {"intensity": 80.0, "horizon_steps": 20}}},
    "latency": {
        "flow": {"informed": {"intensity": 80.0, "horizon_steps": 20}},
        "engine": {"requote_every": 3},
    },
    "jumps": {
        "market": {"process": "jump_diffusion", "jump": {"intensity": 5.0, "size": 1.0}},
        "engine": {"requote_every": 5},
    },
    "two_point": {
        "market": {"process": "two_point", "world": "trades_only", "n_steps": 100},
        "engine": {"q_max": 1000},
    },
}


def scrambled(cfg: Config, values: NDArray[np.float64], t: int) -> NDArray[np.float64]:
    """The same path up to and including step t, a different one after it."""
    new = values.copy()
    if cfg.market.process == "two_point":
        tp = cfg.market.two_point
        new[t + 1 :] = tp.v_low if values[0] == tp.v_high else tp.v_high
    else:
        fresh = random_walk_path(cfg.market, np.random.default_rng(987_654))
        new[t + 1 :] = values[t] + (fresh[t + 1 :] - fresh[t])
    assert np.array_equal(new[: t + 1], values[: t + 1])
    assert not np.array_equal(new[t + 1 :], values[t + 1 :])  # the future really changed
    return new


def _run(
    cfg: Config, strategy: Strategy, values: NDArray[np.float64], known: NDArray[np.float64]
) -> EpisodeResult:
    peek = getattr(strategy, "test_only_peek", None)
    if peek is not None:
        peek(values)
    return run_episode(cfg, strategy, values, build_flows(cfg, 0, values, known))


def quotes_change_with_the_future(cfg: Config, strategy: Strategy, t: int) -> bool:
    values = episode_values(cfg, 0)
    original = _run(cfg, strategy, values, values)
    rerun = _run(cfg, strategy, scrambled(cfg, values, t), values)
    same = np.array_equal(
        original.bids[: t + 1], rerun.bids[: t + 1], equal_nan=True
    ) and np.array_equal(original.asks[: t + 1], rerun.asks[: t + 1], equal_nan=True)
    return not same


CASES = [
    (world, name)
    for world, overrides in WORLDS.items()
    for name, cls in sorted(REGISTRY.items())
    if make_cfg(**overrides).market.world in cls.worlds
]


@pytest.mark.parametrize(("world", "name"), CASES)
@pytest.mark.parametrize("t", [0, 1, 17, 50, 98])
def test_registered_strategies_do_not_look_ahead(world: str, name: str, t: int) -> None:
    """Every registered strategy, in every world it can run in. A strategy added later is
    covered automatically."""
    cfg = make_cfg(**WORLDS[world])
    strategy, _ = build_strategy(cfg, name)
    assert not quotes_change_with_the_future(cfg, strategy, t)


def test_every_registered_strategy_is_covered() -> None:
    assert {name for _, name in CASES} == set(REGISTRY)


@pytest.mark.parametrize("world", ["noise_only", "informed", "two_point"])
@pytest.mark.parametrize("t", [0, 17, 50])
def test_clairvoyant_fails_the_scramble_test(world: str, t: int) -> None:
    """The negative control: a strategy that reads the future is caught."""
    cfg = make_cfg(**WORLDS[world])
    cheat = Clairvoyant(half_spread=0.5, lookahead_steps=10)
    assert quotes_change_with_the_future(cfg, cheat, t)


def test_informed_fills_up_to_t_are_unchanged_by_the_scramble() -> None:
    """The design assumption of this test: with the informed traders' knowledge held fixed,
    the fills up to step t are the same in both runs."""
    cfg = make_cfg(**WORLDS["informed"])
    strategy, _ = build_strategy(cfg, "fixed")
    values = episode_values(cfg, 0)
    a = _run(cfg, strategy, values, values)
    b = _run(cfg, strategy, scrambled(cfg, values, 60), values)
    assert [f for f in a.fills if f.t <= 60] == [f for f in b.fills if f.t <= 60]
    assert any(f.counterparty == "informed" for f in a.fills if f.t <= 60)
