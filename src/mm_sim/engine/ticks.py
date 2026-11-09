"""Rounding quotes to the tick grid, always outwards: bid down, ask up.

Rounding can therefore never narrow the spread. A price within 1e-9 ticks of a grid point is
treated as being on it, so that 99.25 with tick 0.01 stays 99.25 despite float division.
"""

from __future__ import annotations

import math

_SNAP_DECIMALS = 9  # in units of ticks
_PRICE_DECIMALS = 10


def round_bid(price: float, tick: float) -> float:
    return round(math.floor(round(price / tick, _SNAP_DECIMALS)) * tick, _PRICE_DECIMALS)


def round_ask(price: float, tick: float) -> float:
    return round(math.ceil(round(price / tick, _SNAP_DECIMALS)) * tick, _PRICE_DECIMALS)
