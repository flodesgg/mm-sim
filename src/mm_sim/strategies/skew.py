"""Fixed spread with an inventory skew: both quotes shift by -kappa * q.

Long inventory (q > 0) lowers both quotes: the ask comes closer to the mid (more likely to
sell) and the bid moves away (less likely to buy), so the inventory tends back to zero.
kappa = 0 is the `fixed` strategy.
"""

from __future__ import annotations

from pydantic import Field

from mm_sim.config import Config, StrictModel
from mm_sim.strategies.base import Observation, Quotes, Strategy, register, within_limit


class SkewParams(StrictModel):
    half_spread: float = Field(gt=0)  # h
    kappa: float = Field(ge=0)  # price shift per lot of inventory


@register
class Skew(Strategy):
    name = "skew"
    Params = SkewParams

    def __init__(self, cfg: Config, params: StrictModel) -> None:
        assert isinstance(params, SkewParams)
        self._h, self._kappa = params.half_spread, params.kappa

    def quote(self, obs: Observation) -> Quotes:
        assert obs.mid is not None
        center = obs.mid - self._kappa * obs.inventory
        return within_limit(obs, center - self._h, center + self._h)
