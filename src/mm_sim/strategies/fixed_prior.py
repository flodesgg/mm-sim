"""Fixed spread around the prior mean, for the two-point world where there is no public mid:
bid = E[V] - h, ask = E[V] + h, never updated. The naive benchmark for Glosten-Milgrom."""

from __future__ import annotations

from pydantic import Field

from mm_sim.config import Config, StrictModel
from mm_sim.strategies.base import Observation, Quotes, Strategy, register


class FixedPriorParams(StrictModel):
    half_spread: float = Field(gt=0)  # h


@register
class FixedPrior(Strategy):
    name = "fixed_prior"
    worlds = ("trades_only",)
    Params = FixedPriorParams

    def __init__(self, cfg: Config, params: StrictModel) -> None:
        assert isinstance(params, FixedPriorParams)
        tp = cfg.market.two_point
        center = tp.p_high * tp.v_high + (1 - tp.p_high) * tp.v_low
        self._quotes = Quotes(bid=center - params.half_spread, ask=center + params.half_spread)

    def quote(self, obs: Observation) -> Quotes:
        return self._quotes
