"""TEST-ONLY negative control: a strategy that cheats by reading the future value.

It is not registered, so the CLI and the experiments cannot run it, and it never appears in a
report as a strategy. It exists for two reasons:
  * the future-scramble test must FAIL for it (a test that cannot fail proves nothing);
  * it is an upper bound: a real strategy that beats it signals a bug.

The future path arrives through `test_only_peek`, which `simulate_episode` calls for any
strategy that defines it. It never comes through the `Observation`.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from mm_sim.strategies.base import Observation, Quotes, Strategy


class Clairvoyant(Strategy):
    name = "clairvoyant"
    worlds = ("public_mid", "trades_only")

    def __init__(self, half_spread: float, lookahead_steps: int) -> None:
        self._h, self._lookahead = half_spread, lookahead_steps
        self._path: NDArray[np.float64] | None = None

    def test_only_peek(self, values: NDArray[np.float64]) -> None:
        self._path = values

    def quote(self, obs: Observation) -> Quotes:
        assert self._path is not None, "clairvoyant needs test_only_peek"
        future = float(self._path[min(obs.t + self._lookahead, len(self._path) - 1)])
        return Quotes(bid=future - self._h, ask=future + self._h)  # centred on the future value
