from __future__ import annotations

import dataclasses

import pytest
from helpers import make_cfg
from pydantic import ValidationError

from mm_sim.strategies import REGISTRY, Observation, Quotes, build_strategy


def _obs(mid: float | None = 100.0) -> Observation:
    return Observation(
        t=0, time_left=1.0, inventory=0, cash=0.0, q_max=50, mid=mid, past_quotes=(), tape=()
    )


def test_fixed_quotes_are_symmetric_around_the_mid() -> None:
    strategy, params = build_strategy(make_cfg(), "fixed", {"half_spread": 0.4})
    assert params == {"half_spread": 0.4}
    assert strategy.quote(_obs(100.0)) == Quotes(99.6, 100.4)


def test_fixed_reads_its_block_from_config() -> None:
    _, params = build_strategy(make_cfg(), "fixed")
    assert params == {"half_spread": 0.75}


def test_registry_rejects_unknown_strategy_and_bad_parameters() -> None:
    assert "fixed" in REGISTRY
    with pytest.raises(ValueError, match="unknown strategy"):
        build_strategy(make_cfg(), "nope")
    with pytest.raises(ValidationError):
        build_strategy(make_cfg(), "fixed", {"half_spread": -1.0})
    with pytest.raises(ValidationError):
        build_strategy(make_cfg(), "fixed", {"half_spred": 1.0})


def test_fixed_needs_the_public_mid() -> None:
    cfg = make_cfg(market={"process": "two_point", "world": "trades_only"})
    with pytest.raises(ValueError, match=r"runs in market\.world"):
        build_strategy(cfg, "fixed")


def test_observation_is_frozen_and_carries_no_true_value_or_future() -> None:
    """The structural part of the no-look-ahead guarantee: the observation has exactly these
    fields. Adding a field must be a deliberate change to this test."""
    assert [f.name for f in dataclasses.fields(Observation)] == [
        "t",
        "time_left",
        "inventory",
        "cash",
        "q_max",
        "mid",
        "past_quotes",
        "tape",
    ]
    with pytest.raises(dataclasses.FrozenInstanceError):
        _obs().mid = 1.0  # type: ignore[misc]
