"""Glosten-Milgrom quotes in the two-point world (no reference price, only the trade tape).

The market maker keeps the posterior pi = P(V = V_H | trades so far), starting at the prior p.
A buy is more likely when V = V_H:

    P(buy | V_H) = mu + (1 - mu)/2        P(buy | V_L) = (1 - mu)/2
    P(sell | V_H) = (1 - mu)/2            P(sell | V_L) = mu + (1 - mu)/2

Quotes are the expected value given the next trade's direction (Bayes' rule), so each trade
is priced at what the value is expected to be once that trade is known: zero expected profit.

    ask = E[V | buy]  = (pi * P(buy|V_H) * V_H + (1-pi) * P(buy|V_L) * V_L) / P(buy)
    bid = E[V | sell] = (pi * P(sell|V_H) * V_H + (1-pi) * P(sell|V_L) * V_L) / P(sell)

After a trade, pi becomes P(V_H | that trade). Assumptions: the market maker knows mu, p, V_H
and V_L, and the inventory limit never closes a side (a closed side would make "no trade"
informative, which this update ignores).
"""

from __future__ import annotations

from mm_sim.config import Config, StrictModel
from mm_sim.strategies.base import Observation, Quotes, Strategy, register


class GlostenMilgromParams(StrictModel):
    pass


def likelihoods(mu: float) -> tuple[float, float]:
    """(P(buy | V_H), P(buy | V_L)); the sell probabilities are the same two, swapped."""
    return mu + (1 - mu) / 2, (1 - mu) / 2


def posterior_after(pi: float, side: int, mu: float) -> float:
    """P(V_H) after one trade. side: +1 the trader bought, -1 sold."""
    buy_h, buy_l = likelihoods(mu)
    like_h, like_l = (buy_h, buy_l) if side > 0 else (buy_l, buy_h)
    return pi * like_h / (pi * like_h + (1 - pi) * like_l)


def gm_quotes(pi: float, mu: float, v_high: float, v_low: float) -> tuple[float, float]:
    """(bid, ask) for the posterior pi: E[V | next trade is a sell], E[V | it is a buy]."""
    pi_buy, pi_sell = posterior_after(pi, +1, mu), posterior_after(pi, -1, mu)
    return (
        pi_sell * v_high + (1 - pi_sell) * v_low,
        pi_buy * v_high + (1 - pi_buy) * v_low,
    )


@register
class GlostenMilgrom(Strategy):
    name = "glosten_milgrom"
    worlds = ("trades_only",)
    Params = GlostenMilgromParams

    def __init__(self, cfg: Config, params: StrictModel) -> None:
        tp = cfg.market.two_point
        self._mu = cfg.flow.glosten_milgrom.mu
        self._prior, self._v_high, self._v_low = tp.p_high, tp.v_high, tp.v_low
        self.reset()

    def reset(self) -> None:
        self._pi = self._prior
        self._trades_seen = 0

    def quote(self, obs: Observation) -> Quotes:
        for trade in obs.tape[self._trades_seen :]:  # update on the trades not yet processed
            self._pi = posterior_after(self._pi, trade.side, self._mu)
        self._trades_seen = len(obs.tape)
        bid, ask = gm_quotes(self._pi, self._mu, self._v_high, self._v_low)
        return Quotes(bid=bid, ask=ask)
