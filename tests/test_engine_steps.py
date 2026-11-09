"""Hand-computed engine steps that pin the order of events (docs/model_notes.md, section 4)."""

from __future__ import annotations

import numpy as np
import pytest
from helpers import make_cfg

from mm_sim.accounting.pnl import episode_metrics
from mm_sim.config import Config, StrictModel
from mm_sim.engine.reference import BOUGHT, SOLD, EpisodeResult, Fill, run_episode
from mm_sim.strategies.base import Observation, PastQuote, Quotes, Strategy, Trade


class ScriptedStrategy(Strategy):
    """Returns the given quotes in order, one per call, and records what it observed."""

    name = "scripted"
    Params = StrictModel

    def __init__(self, quotes: list[Quotes]) -> None:
        self._quotes = quotes
        self.seen: list[Observation] = []

    def quote(self, obs: Observation) -> Quotes:
        self.seen.append(obs)
        return self._quotes[len(self.seen) - 1]


class ScriptedFlow:
    """Wants to trade at the scripted steps: t -> (hit the bid, lift the ask)."""

    def __init__(self, counterparty: str, wants: dict[int, tuple[bool, bool]]) -> None:
        self.counterparty = counterparty
        self._wants = wants
        self.offered: dict[int, tuple[float | None, float | None]] = {}

    def act(self, t: int, bid: float | None, ask: float | None) -> tuple[bool, bool]:
        self.offered[t] = (bid, ask)
        return self._wants.get(t, (False, False))


def _cfg(**engine: object) -> Config:
    base = {"requote_every": 2, "q_max": 2, "maker_fee": 0.1}
    return make_cfg(
        market={"n_steps": 10, "tick_size": 0.5},
        engine={**base, **engine},
        accounting={"markout_horizon_steps": 2, "markout_curve_horizons": [0, 2]},
    )


VALUES = np.array([100, 100, 101, 101, 102, 102, 100, 100, 100, 100, 103], dtype=float)
QUOTES = [
    Quotes(99.3, 100.6),  # t=0: rounds outwards to 99.0 / 101.0
    Quotes(100.5, 101.5),  # t=2: already on the 0.5 grid
    Quotes(101.0, None),  # t=4: ask pulled
    Quotes(99.5, 100.5),  # t=6
    Quotes(99.5, 100.5),  # t=8
]


def _run() -> tuple[Config, ScriptedStrategy, ScriptedFlow, ScriptedFlow, EpisodeResult]:
    cfg = _cfg()
    strategy = ScriptedStrategy(QUOTES)
    informed = ScriptedFlow("informed", {1: (False, True), 2: (True, False), 7: (False, True)})
    noise = ScriptedFlow(
        "noise",
        {
            0: (True, False),
            1: (True, True),
            3: (True, False),
            4: (True, True),
            6: (False, True),
            7: (True, False),
            9: (False, True),
        },
    )
    res = run_episode(cfg, strategy, VALUES, [informed, noise])
    return cfg, strategy, informed, noise, res


def test_ten_hand_computed_steps() -> None:
    """requote_every=2, q_max=2, fee 0.1 per lot, tick 0.5. Quotes posted at t=0,2,4,6,8.

    t  quotes (bid/ask)   events                                         q   cash
    0  99.0 / 101.0       noise hits bid: buy 99.0                       1   -99.1
    1  stale 99.0/101.0   informed lifts ask first: sell 101.0           0     1.8
                          noise wants the ask too: already filled
                          noise hits bid: buy 99.0                       1   -97.3
    2  100.5 / 101.5      informed hits bid: buy 100.5                   2  -197.9
    3  stale              q = q_max: bid closed, noise's hit is refused  2  -197.9
    4  101.0 / none       bid closed (limit), ask pulled: nothing        2  -197.9
    5  stale              nothing                                        2  -197.9
    6  99.5 / 100.5       noise lifts ask: sell 100.5                    1   -97.5
    7  stale              informed lifts ask: sell 100.5                 0     2.9
                          noise hits bid: buy 99.5                       1   -96.7
    8  99.5 / 100.5       nothing                                        1   -96.7
    9  stale              noise lifts ask: sell 100.5                    0     3.7

    Check: sells 101 + 3*100.5 = 402.5, buys 99 + 99 + 100.5 + 99.5 = 398, 8 fees = 0.8,
    cash = 402.5 - 398 - 0.8 = 3.7.
    """
    _, strategy, informed, noise, res = _run()
    assert res.fills == (
        Fill(0, BOUGHT, 99.0, 1, "noise"),
        Fill(1, SOLD, 101.0, 1, "informed"),
        Fill(1, BOUGHT, 99.0, 1, "noise"),
        Fill(2, BOUGHT, 100.5, 1, "informed"),
        Fill(6, SOLD, 100.5, 1, "noise"),
        Fill(7, SOLD, 100.5, 1, "informed"),
        Fill(7, BOUGHT, 99.5, 1, "noise"),
        Fill(9, SOLD, 100.5, 1, "noise"),
    )
    assert res.inventory.tolist() == [0, 1, 1, 2, 2, 2, 2, 1, 1, 1, 0]
    assert res.cash == pytest.approx(3.7, abs=1e-12)
    assert res.fees == pytest.approx(0.8, abs=1e-12)
    # standing quotes per step: stale quotes stay, a pulled side is NaN
    np.testing.assert_array_equal(
        res.bids,
        [99.0, 99.0, 100.5, 100.5, 101.0, 101.0, 99.5, 99.5, 99.5, 99.5],
    )
    np.testing.assert_array_equal(
        res.asks,
        [101.0, 101.0, 101.5, 101.5, np.nan, np.nan, 100.5, 100.5, 100.5, 100.5],
    )

    # the strategy is asked only on requote steps
    assert [o.t for o in strategy.seen] == [0, 2, 4, 6, 8]
    # informed act before noise: at t=1 noise is no longer offered the ask
    assert informed.offered[1] == (99.0, 101.0)
    assert noise.offered[1] == (99.0, None)
    # at the inventory limit the bid is closed to every flow, before anyone trades
    assert informed.offered[3] == (None, 101.5)
    assert noise.offered[3] == (None, 101.5)
    assert noise.offered[4] == (None, None)


def test_observation_at_step_two_shows_only_the_past() -> None:
    cfg, strategy, _, _, _ = _run()
    obs = strategy.seen[1]
    assert obs.t == 2
    assert obs.time_left == pytest.approx(8 * cfg.market.dt)
    assert obs.inventory == 1
    assert obs.cash == pytest.approx(-97.3)
    assert obs.mid == 101.0  # the current value, not a future one
    assert obs.q_max == 2
    assert obs.past_quotes == (PastQuote(0, 99.0, 101.0),)
    assert obs.tape == (Trade(0, 99.0, -1), Trade(1, 101.0, +1), Trade(1, 99.0, -1))


def test_hand_computed_decomposition() -> None:
    """h = 2 steps, V_T = 103. Per fill (side d, price p): spread d*(V_t - p),
    short-term d*(V_{t+2} - V_t), inventory d*(V_T - V_{t+2}).

    t0 +1  99.0: V0=100, V2=101  ->  +1.0  +1  +2
    t1 -1 101.0: V1=100, V3=101  ->  +1.0  -1  -2
    t1 +1  99.0:                 ->  +1.0  +1  +2
    t2 +1 100.5: V2=101, V4=102  ->  +0.5  +1  +1
    t6 -1 100.5: V6=100, V8=100  ->  +0.5   0  -3
    t7 -1 100.5: V7=100, V9=100  ->  +0.5   0  -3
    t7 +1  99.5:                 ->  +0.5   0  +3
    t9 -1 100.5: V9=100, V11 clipped to V10=103 -> +0.5  -3  0
    sums: spread 5.5, short-term -1, inventory 0; minus fees 0.8 = 3.7 = cash + 0 * V_T.
    """
    cfg, _, _, _, res = _run()
    m = episode_metrics(cfg, res)
    assert m["spread_capture"] == pytest.approx(5.5)
    assert m["adverse_selection"] == pytest.approx(-1.0)
    assert m["inventory_pnl"] == pytest.approx(0.0)
    assert m["fees"] == pytest.approx(0.8)
    assert m["pnl_mtm"] == pytest.approx(3.7)
    assert (m["buys"], m["sells"], m["volume"]) == (4, 4, 8)
    assert m["max_abs_q"] == 2
    assert m["mean_abs_q"] == pytest.approx(1.3)  # (1+1+2+2+2+2+1+1+1+0)/10
    assert m["share_at_limit"] == pytest.approx(0.4)  # after steps 2, 3, 4, 5
    assert m["terminal_q"] == 0


def test_liquidated_pnl_charges_for_final_inventory() -> None:
    """Two buys at 99.0 and nothing else: q_T = 2, V_T = 103, cash = -198.
    MTM = -198 + 2*103 = 8. Liquidation costs |q| * (0.25 + 0.1*|q|) = 2 * 0.45 = 0.9."""
    cfg = _cfg(maker_fee=0.0, liq_half_spread=0.25, liq_impact=0.1)
    noise = ScriptedFlow("noise", {0: (True, False), 1: (True, False)})
    res = run_episode(cfg, ScriptedStrategy(QUOTES), VALUES, [noise])
    m = episode_metrics(cfg, res)
    assert m["pnl_mtm"] == pytest.approx(8.0)
    assert m["pnl_liquidated"] == pytest.approx(7.1)


def test_kill_switch_stops_quoting() -> None:
    """Buy 2 lots at 99.0 (t=0, t=1), then the value falls to 90 at t=3:
    MTM = -198 + 2*90 = -18 < -10, so from step 3 there are no quotes and no strategy calls."""
    cfg = _cfg(maker_fee=0.0, requote_every=1, kill_switch_loss=10.0)
    values = np.array([100, 100, 100, 90, 90, 90, 90, 90, 90, 90, 90], dtype=float)
    strategy = ScriptedStrategy([Quotes(99.0, 101.0)] * 10)
    noise = ScriptedFlow("noise", {t: (True, False) for t in range(10)})
    res = run_episode(cfg, strategy, values, [noise])
    assert res.killed_at == 3
    assert [o.t for o in strategy.seen] == [0, 1, 2]
    assert len(res.fills) == 2  # the third hit at t=2 is refused by the inventory limit
    assert np.isnan(res.bids[3:]).all() and np.isnan(res.asks[3:]).all()


def test_crossed_quotes_are_rejected() -> None:
    with pytest.raises(ValueError, match="crossed quotes"):
        run_episode(_cfg(), ScriptedStrategy([Quotes(101.0, 100.0)]), VALUES, [])
