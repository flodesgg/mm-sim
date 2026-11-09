"""Fixed spread around the public mid: bid = s - h, ask = s + h."""

from __future__ import annotations

from pydantic import Field

from mm_sim.config import Config, StrictModel
from mm_sim.strategies.base import Observation, Quotes, Strategy, register, within_limit


class FixedParams(StrictModel):
    half_spread: float = Field(gt=0)  # h


@register
class FixedSpread(Strategy):
    name = "fixed"
    Params = FixedParams

    def __init__(self, cfg: Config, params: StrictModel) -> None:
        assert isinstance(params, FixedParams)
        self._h = params.half_spread

    def quote(self, obs: Observation) -> Quotes:
        assert obs.mid is not None
        return within_limit(obs, obs.mid - self._h, obs.mid + self._h)
