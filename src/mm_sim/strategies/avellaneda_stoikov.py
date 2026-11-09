"""The Avellaneda-Stoikov (2008) finite-horizon quotes, eq. (29)-(30) of the paper.

    reservation price   r = s - q * gamma * sigma^2 * (T - t)
    total spread        gamma * sigma^2 * (T - t) + (2 / gamma) * ln(1 + gamma / k)
    quotes              r -+ spread / 2

The reservation price is where a risk-averse (CARA, risk aversion gamma) market maker is
indifferent between its inventory and cash: below the mid when long, above when short, and
closer to the mid as the end approaches (less time for the inventory to hurt). The spread has
a risk part that shrinks to zero at T and a part from the fill intensity that tends to 2/k as
gamma -> 0.

This is the paper's approximate solution, not an exact optimum. Optimistic assumption: the
strategy is given the model's true sigma and k.
"""

from __future__ import annotations

import math

from pydantic import Field

from mm_sim.config import Config, StrictModel
from mm_sim.strategies.base import Observation, Quotes, Strategy, register, within_limit


class AvellanedaStoikovParams(StrictModel):
    gamma: float = Field(gt=0)  # risk aversion


def reservation_price(mid: float, q: int, gamma: float, sigma: float, time_left: float) -> float:
    return mid - q * gamma * sigma**2 * time_left


def total_spread(gamma: float, sigma: float, k: float, time_left: float) -> float:
    return gamma * sigma**2 * time_left + (2 / gamma) * math.log(1 + gamma / k)


@register
class AvellanedaStoikov(Strategy):
    name = "avellaneda_stoikov"
    Params = AvellanedaStoikovParams

    def __init__(self, cfg: Config, params: StrictModel) -> None:
        assert isinstance(params, AvellanedaStoikovParams)
        self._gamma = params.gamma
        self._sigma, self._k = cfg.market.sigma, cfg.flow.noise.k  # the true model values

    def quote(self, obs: Observation) -> Quotes:
        assert obs.mid is not None
        r = reservation_price(obs.mid, obs.inventory, self._gamma, self._sigma, obs.time_left)
        half = total_spread(self._gamma, self._sigma, self._k, obs.time_left) / 2
        return within_limit(obs, r - half, r + half)
