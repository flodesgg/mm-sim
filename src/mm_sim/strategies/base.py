"""What a strategy sees and returns, and the registry of strategies.

A strategy is a function of the `Observation` and its own state. The observation is frozen
and holds no true value, no future value, no random generator and no reference to the engine;
the future-scramble test (Stage B) proves that quotes do not depend on the future.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from mm_sim.config import Config, StrictModel


@dataclass(frozen=True)
class Trade:
    """One line of the public trade tape. side: +1 the trader bought (ask lifted), -1 sold."""

    t: int
    price: float
    side: int


@dataclass(frozen=True)
class Quotes:
    """One lot on each side; None pulls that side."""

    bid: float | None
    ask: float | None


@dataclass(frozen=True)
class PastQuote:
    t: int
    bid: float | None
    ask: float | None


@dataclass(frozen=True)
class Observation:
    t: int  # current step
    time_left: float  # T - t*dt
    inventory: int  # lots, before this step's trades
    cash: float
    q_max: int  # the engine's inventory limit
    mid: float | None  # reference price s_t in the public_mid world, None in trades_only
    past_quotes: tuple[PastQuote, ...]  # the strategy's own earlier quotes (after rounding)
    tape: tuple[Trade, ...]  # all trades so far


class Strategy(ABC):
    """Base class. A subclass sets `name`, a `Params` schema, and implements `quote`."""

    name: ClassVar[str]
    worlds: ClassVar[tuple[str, ...]] = ("public_mid",)  # where the strategy can run
    Params: ClassVar[type[StrictModel]]

    def __init__(self, cfg: Config, params: StrictModel) -> None:  # noqa: B027
        """`cfg` gives the static model parameters a strategy is allowed to know."""

    def reset(self) -> None:  # noqa: B027 - optional hook, stateless strategies need nothing
        """Called before every episode; a stateful strategy clears its state here."""

    @abstractmethod
    def quote(self, obs: Observation) -> Quotes: ...


REGISTRY: dict[str, type[Strategy]] = {}


def register[S: type[Strategy]](cls: S) -> S:
    if cls.name in REGISTRY:
        raise ValueError(f"strategy {cls.name!r} is registered twice")
    REGISTRY[cls.name] = cls
    return cls


def build_strategy(
    cfg: Config, name: str, overrides: dict[str, object] | None = None
) -> tuple[Strategy, dict[str, object]]:
    """Build a strategy from its block in config.strategies, with optional overrides.

    Returns the strategy and its validated parameters (for run records).
    """
    if name not in REGISTRY:
        raise ValueError(f"unknown strategy {name!r}; available: {sorted(REGISTRY)}")
    cls = REGISTRY[name]
    if cfg.market.world not in cls.worlds:
        raise ValueError(
            f"strategy {name!r} runs in market.world {list(cls.worlds)}, "
            f"not in {cfg.market.world!r}"
        )
    params = cls.Params.model_validate({**cfg.strategies.get(name, {}), **(overrides or {})})
    return cls(cfg, params), params.model_dump(mode="json")
