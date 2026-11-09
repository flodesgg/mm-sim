"""Noise traders in the public-mid world (Avellaneda-Stoikov style arrivals).

Market orders that reach a quote at distance d from the mid arrive at rate A * exp(-k * d).
Over one step of length dt the quote is filled with the probability of at least one arrival:

    p(d) = 1 - exp(-A * exp(-k * d) * dt)
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

from mm_sim.config import NoiseFlowConfig


def fill_probability(distance: float, A: float, k: float, dt: float) -> float:
    return 1.0 - math.exp(-A * math.exp(-k * distance) * dt)


class NoiseFlow:
    """One uniform draw per step and side, fixed before the episode starts.

    The side fills when its draw is below p(distance). Because the draws do not depend on the
    quotes, two strategies on the same seed face the same noise traders, and a wider quote
    can only lose fills, never gain them.
    """

    counterparty = "noise"

    def __init__(
        self,
        cfg: NoiseFlowConfig,
        dt: float,
        mids: NDArray[np.float64],
        draws: NDArray[np.float64],  # shape (N, 2): column 0 bid side, column 1 ask side
    ) -> None:
        self._cfg, self._dt, self._mids, self._draws = cfg, dt, mids, draws

    @classmethod
    def from_rng(
        cls, cfg: NoiseFlowConfig, dt: float, mids: NDArray[np.float64], rng: np.random.Generator
    ) -> NoiseFlow:
        return cls(cfg, dt, mids, rng.random((len(mids) - 1, 2)))

    def act(self, t: int, bid: float | None, ask: float | None) -> tuple[bool, bool]:
        mid = float(self._mids[t])  # the current mid: a stale quote is measured against it
        c = self._cfg
        hit = bid is not None and self._draws[t, 0] < fill_probability(
            mid - bid, c.A, c.k, self._dt
        )
        lift = ask is not None and self._draws[t, 1] < fill_probability(
            ask - mid, c.A, c.k, self._dt
        )
        return bool(hit), bool(lift)
