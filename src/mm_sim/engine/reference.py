"""The reference engine: one episode, one step at a time. This file is the source of truth.

Order of events in step t (docs/model_notes.md, section 4):
  1. if t % requote_every == 0 the strategy sees the observation for step t and posts quotes
     (rounded outwards to the tick grid); otherwise the previous quotes stay
  2. the flows act in the order given (informed first, then noise); each side fills at most
     once per step
  3. each fill is recorded with its counterparty type
  4. the value moves to V_{t+1}

`run_episode` is a pure function of its inputs: all randomness is prepared beforehand
(`simulate_episode`), so tests can inject a hand-made value path and hand-made flows.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from mm_sim.config import Config
from mm_sim.engine.ticks import round_ask, round_bid
from mm_sim.flow.base import Flow
from mm_sim.flow.glosten_milgrom import GMInformedFlow, GMNoiseFlow
from mm_sim.flow.informed import InformedFlow
from mm_sim.flow.noise import NoiseFlow
from mm_sim.market.value import value_path
from mm_sim.seeds import component_rng
from mm_sim.strategies.base import Observation, PastQuote, Quotes, Strategy, Trade

BOUGHT, SOLD = 1, -1  # the market maker's side of a fill


@dataclass(frozen=True)
class Fill:
    t: int
    side: int  # +1 the market maker bought (its bid was hit), -1 it sold (its ask was lifted)
    price: float
    size: int  # lots
    counterparty: str


@dataclass(frozen=True)
class EpisodeResult:
    values: NDArray[np.float64]  # V_0 .. V_N; V_N is the terminal value V_T
    bids: NDArray[np.float64]  # quote standing in step t (NaN = no quote), length N
    asks: NDArray[np.float64]
    inventory: NDArray[np.int64]  # inventory[t] before step t; inventory[N] is terminal
    fills: tuple[Fill, ...]
    cash: float  # after fees
    fees: float  # total fees paid (negative = rebates received)
    killed_at: int | None  # step at which the kill switch stopped quoting


def _rounded(quotes: Quotes, tick: float) -> Quotes:
    bid = None if quotes.bid is None else round_bid(quotes.bid, tick)
    ask = None if quotes.ask is None else round_ask(quotes.ask, tick)
    if bid is not None and ask is not None and bid >= ask:
        raise ValueError(f"crossed quotes: bid {bid} >= ask {ask}")
    return Quotes(bid, ask)


def run_episode(
    cfg: Config, strategy: Strategy, values: NDArray[np.float64], flows: Sequence[Flow]
) -> EpisodeResult:
    market, eng = cfg.market, cfg.engine
    n = market.n_steps
    public_mid = market.world == "public_mid"

    bids, asks = np.full(n, np.nan), np.full(n, np.nan)
    inventory = np.zeros(n + 1, dtype=np.int64)
    q, cash, fees = 0, 0.0, 0.0
    quotes = Quotes(None, None)
    killed_at: int | None = None
    fills: list[Fill] = []
    tape: list[Trade] = []
    past_quotes: list[PastQuote] = []

    strategy.reset()
    for t in range(n):
        v = float(values[t])

        # kill switch: mark-to-market loss beyond the limit stops quoting for the episode
        if (
            killed_at is None
            and eng.kill_switch_loss is not None
            and cash + q * v < -eng.kill_switch_loss
        ):
            killed_at, quotes = t, Quotes(None, None)

        # 1. requote
        if killed_at is None and t % eng.requote_every == 0:
            obs = Observation(
                t=t,
                time_left=(n - t) * market.dt,
                inventory=q,
                cash=cash,
                q_max=eng.q_max,
                mid=v if public_mid else None,
                past_quotes=tuple(past_quotes),
                tape=tuple(tape),
            )
            quotes = _rounded(strategy.quote(obs), market.tick_size)
            past_quotes.append(PastQuote(t, quotes.bid, quotes.ask))
        if quotes.bid is not None:
            bids[t] = quotes.bid
        if quotes.ask is not None:
            asks[t] = quotes.ask

        # 2.-3. flows trade against the quotes. A side at the inventory limit is closed for
        # the whole step, so |q| can never exceed q_max whatever the order of fills.
        bid = quotes.bid if q < eng.q_max else None
        ask = quotes.ask if q > -eng.q_max else None
        for flow in flows:
            hit, lift = flow.act(t, bid, ask)
            if hit and bid is not None:
                fills.append(Fill(t, BOUGHT, bid, 1, flow.counterparty))
                tape.append(Trade(t, bid, -1))
                q, cash, fees = q + 1, cash - bid - eng.maker_fee, fees + eng.maker_fee
                bid = None  # at most one fill per side per step
            if lift and ask is not None:
                fills.append(Fill(t, SOLD, ask, 1, flow.counterparty))
                tape.append(Trade(t, ask, +1))
                q, cash, fees = q - 1, cash + ask - eng.maker_fee, fees + eng.maker_fee
                ask = None

        # 4. the value moves to V_{t+1} (the path was drawn beforehand)
        inventory[t + 1] = q

    return EpisodeResult(values, bids, asks, inventory, tuple(fills), cash, fees, killed_at)


def build_flows(
    cfg: Config,
    episode: int,
    values: NDArray[np.float64],
    informed_knowledge: NDArray[np.float64] | None = None,
) -> list[Flow]:
    """This episode's flows, informed first. `values` is the path the market sees (the mid in
    the public_mid world); `informed_knowledge` is the path the informed traders know. They
    are the same path except in the future-scramble test."""
    seed, n = cfg.analysis.seed, cfg.market.n_steps
    known = values if informed_knowledge is None else informed_knowledge
    if cfg.market.world == "public_mid":
        flows: list[Flow] = []
        if cfg.flow.informed.intensity > 0:
            arrivals = component_rng(seed, episode, "informed_arrivals").random(n)
            flows.append(InformedFlow(cfg.flow.informed, cfg.market.dt, known, arrivals))
        rng = component_rng(seed, episode, "noise_fills")
        flows.append(NoiseFlow.from_rng(cfg.flow.noise, cfg.market.dt, values, rng))
        return flows
    mu = cfg.flow.glosten_milgrom.mu
    types = component_rng(seed, episode, "trader_types").random(n)
    sides = component_rng(seed, episode, "noise_fills").random(n)
    return [GMInformedFlow(mu, known, types), GMNoiseFlow(mu, types, sides)]


def simulate_episode(cfg: Config, strategy: Strategy, episode: int) -> EpisodeResult:
    """Draw this episode's random inputs from its own streams and run it."""
    values = value_path(cfg.market, component_rng(cfg.analysis.seed, episode, "value"))
    # Test-only hook for the `clairvoyant` negative control: the only way a strategy can get
    # the true path. No registered strategy defines it.
    peek = getattr(strategy, "test_only_peek", None)
    if peek is not None:
        peek(values)
    return run_episode(cfg, strategy, values, build_flows(cfg, episode, values))
