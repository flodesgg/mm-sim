"""Order flow of the two-point (Glosten-Milgrom) world: exactly one trader arrives per step.

With probability mu the trader is informed and knows V: it buys if the ask is below V and
sells if the bid is above V (so it never trades at a loss). Otherwise it is a noise trader
who buys or sells with probability 1/2 at whatever the quote is.

The two classes share the per-step "type" draw, so exactly one of them acts in a step.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


class GMInformedFlow:
    counterparty = "informed"

    def __init__(
        self, mu: float, known_values: NDArray[np.float64], type_draws: NDArray[np.float64]
    ) -> None:
        self._mu, self._known, self._types = mu, known_values, type_draws

    def act(self, t: int, bid: float | None, ask: float | None) -> tuple[bool, bool]:
        if self._types[t] >= self._mu:
            return False, False  # this step's trader is a noise trader
        v = float(self._known[t])
        if ask is not None and ask < v:
            return False, True
        if bid is not None and bid > v:
            return True, False
        return False, False


class GMNoiseFlow:
    counterparty = "noise"

    def __init__(
        self, mu: float, type_draws: NDArray[np.float64], side_draws: NDArray[np.float64]
    ) -> None:
        self._mu, self._types, self._sides = mu, type_draws, side_draws

    def act(self, t: int, bid: float | None, ask: float | None) -> tuple[bool, bool]:
        if self._types[t] < self._mu:
            return False, False  # this step's trader is informed
        if self._sides[t] < 0.5:
            return False, ask is not None  # wants to buy
        return bid is not None, False  # wants to sell
