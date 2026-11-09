"""Quoting strategies. Importing this package registers every strategy module in it."""

from mm_sim.strategies import (  # noqa: F401  (importing registers the strategy)
    avellaneda_stoikov,
    fixed,
    fixed_prior,
    glosten_milgrom,
    skew,
)
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
