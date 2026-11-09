"""Informed traders in the public-mid world.

One arrives with probability lambda_I * dt per step. It knows the value `horizon_steps` ahead
(clipped to the end of the episode) and trades one lot only when that is profitable by more
than its threshold c_I:

    buy  at the ask  if  ask < V_{t+h} - c_I
    sell at the bid  if  bid > V_{t+h} + c_I
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from mm_sim.config import InformedFlowConfig


class InformedFlow:
    counterparty = "informed"

    def __init__(
        self,
        cfg: InformedFlowConfig,
        dt: float,
        known_values: NDArray[np.float64],  # the path the informed traders know (V_0 .. V_N)
        draws: NDArray[np.float64],  # one uniform per step: arrival if draw < lambda_I * dt
    ) -> None:
        self._cfg, self._known, self._draws = cfg, known_values, draws
        self._arrival_probability = cfg.intensity * dt

    def act(self, t: int, bid: float | None, ask: float | None) -> tuple[bool, bool]:
        if self._draws[t] >= self._arrival_probability:
            return False, False
        future = float(self._known[min(t + self._cfg.horizon_steps, len(self._known) - 1)])
        if ask is not None and ask < future - self._cfg.threshold:
            return False, True
        if bid is not None and bid > future + self._cfg.threshold:
            return True, False
        return False, False
