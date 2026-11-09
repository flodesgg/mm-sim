"""Quoting strategies. Importing this package registers every strategy module in it."""

from mm_sim.strategies import fixed  # noqa: F401  (registers "fixed")
from mm_sim.strategies.base import (
    REGISTRY,
    Observation,
    PastQuote,
    Quotes,
    Strategy,
    Trade,
    build_strategy,
)

__all__ = [
    "REGISTRY",
    "Observation",
    "PastQuote",
    "Quotes",
    "Strategy",
    "Trade",
    "build_strategy",
]
