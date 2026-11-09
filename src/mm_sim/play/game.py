"""The interactive quoting game (`mm-sim play`).

The player is a `Strategy` like any other: each round the engine asks it for quotes and it
asks the human. The game therefore runs on the reference engine, with the same Glosten-Milgrom
flow as the simulations; there is no second implementation of the market.

During the game P&L is marked at the last trade price (the player does not know V). At the
end V is revealed, with the P&L split by counterparty and the Glosten-Milgrom quotes for each
round next to the player's.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd
from rich.console import Console
from rich.table import Table

from mm_sim.accounting.pnl import episode_metrics
from mm_sim.analysis.montecarlo import with_run_settings
from mm_sim.config import Config
from mm_sim.engine.reference import (
    BOUGHT,
    EpisodeResult,
    Fill,
    build_flows,
    episode_values,
    run_episode,
)
from mm_sim.strategies.base import Observation, Quotes, Strategy
from mm_sim.strategies.glosten_milgrom import gm_quotes, posterior_after

ReadLine = Callable[[str], str]

ROUND_COLUMNS = [
    "round",
    "bid",
    "ask",
    "gm_bid",
    "gm_ask",
    "gm_posterior",
    "trade_side",  # +1 a trader bought from you, -1 sold to you, 0 no trade
    "trade_price",
    "counterparty",
    "inventory_after",
    "cash_after",
    "pnl_marked_at_last_trade",
    "fill_pnl_at_true_value",
]


class GameAborted(Exception):
    """The player quit; nothing is saved."""


def parse_quotes(line: str) -> tuple[float, float]:
    """'99.6 100.4' (comma decimals accepted) -> (bid, ask). Raises ValueError if unusable."""
    parts = line.replace(",", ".").split()
    if len(parts) != 2:
        raise ValueError("type two numbers: bid ask")
    try:
        bid, ask = float(parts[0]), float(parts[1])
    except ValueError:
        raise ValueError("bid and ask must be numbers, for example 99.6 100.4") from None
    if not (np.isfinite(bid) and np.isfinite(ask)):
        raise ValueError("bid and ask must be numbers, for example 99.6 100.4")
    if bid >= ask:
        raise ValueError("the bid must be below the ask")
    return bid, ask


class HumanStrategy(Strategy):
    """Asks the player for quotes. Not registered: only the game constructs it."""

    name = "human"
    worlds = ("trades_only",)

    def __init__(
        self,
        cfg: Config,
        read_line: ReadLine,
        console: Console,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        tp = cfg.market.two_point
        self._cfg, self._read, self._console, self._clock = cfg, read_line, console, clock
        self._prior_mean = tp.p_high * tp.v_high + (1 - tp.p_high) * tp.v_low
        self.timeouts = 0
        self._trades_shown = 0

    def _show_last_round(self, obs: Observation) -> None:
        new = obs.tape[self._trades_shown :]
        self._trades_shown = len(obs.tape)
        if obs.t > 0:
            if new:
                for trade in new:
                    verb = "bought from you" if trade.side > 0 else "sold to you"
                    self._console.print(f"  -> a trader {verb} at {trade.price:.2f}")
            else:
                self._console.print("  -> no trade")
        mark = obs.tape[-1].price if obs.tape else self._prior_mean
        self._console.print(
            f"  inventory {obs.inventory:+d}   cash {obs.cash:.2f}   "
            f"P&L marked at the last trade ({mark:.2f}): {obs.cash + obs.inventory * mark:+.2f}"
        )

    def quote(self, obs: Observation) -> Quotes:
        self._show_last_round(obs)
        limit = self._cfg.play.time_limit_sec
        rounds = self._cfg.market.n_steps
        while True:
            started = self._clock()
            try:
                line = self._read(f"round {obs.t + 1}/{rounds}  bid ask > ").strip()
            except EOFError as e:
                raise GameAborted from e
            if line.lower() in ("q", "quit", "exit"):
                raise GameAborted
            if limit is not None and self._clock() - started > limit:
                self.timeouts += 1
                self._console.print(f"  too slow (limit {limit:g} s): no quotes this round")
                return Quotes(None, None)
            try:
                bid, ask = parse_quotes(line)
            except ValueError as e:
                self._console.print(f"  {e}")
                continue
            return Quotes(bid, ask)


@dataclass(frozen=True)
class GameResult:
    seed: int
    episode: EpisodeResult
    rounds: pd.DataFrame  # one row per round, columns ROUND_COLUMNS
    summary: dict[str, float]


def round_table(cfg: Config, res: EpisodeResult) -> pd.DataFrame:
    """One row per round: the player's quotes, the Glosten-Milgrom quotes given the same
    trades so far, the trade, and running inventory, cash and P&L."""
    tp, mu = cfg.market.two_point, cfg.flow.glosten_milgrom.mu
    prior_mean = tp.p_high * tp.v_high + (1 - tp.p_high) * tp.v_low
    v = float(res.values[0])
    fills = {f.t: f for f in res.fills}  # one trader per step: at most one fill
    pi, cash, last_price = tp.p_high, 0.0, prior_mean
    rows = []
    for t in range(cfg.market.n_steps):
        gm_bid, gm_ask = gm_quotes(pi, mu, tp.v_high, tp.v_low)
        row: dict[str, object] = {
            "round": t + 1,
            "bid": res.bids[t],
            "ask": res.asks[t],
            "gm_bid": gm_bid,
            "gm_ask": gm_ask,
            "gm_posterior": pi,
            "trade_side": 0,
            "trade_price": np.nan,
            "counterparty": "",
            "fill_pnl_at_true_value": 0.0,
        }
        f = fills.get(t)
        if f is not None:
            trader_side = -f.side  # the market maker bought <=> the trader sold
            cash += -f.side * f.price - cfg.engine.maker_fee
            last_price = f.price
            pi = posterior_after(pi, trader_side, mu)
            row.update(
                trade_side=trader_side,
                trade_price=f.price,
                counterparty=f.counterparty,
                fill_pnl_at_true_value=f.side * (v - f.price),
            )
        q = int(res.inventory[t + 1])
        row.update(
            inventory_after=q, cash_after=cash, pnl_marked_at_last_trade=cash + q * last_price
        )
        rows.append(row)
    return pd.DataFrame(rows, columns=ROUND_COLUMNS)


def summarize_game(
    cfg: Config, res: EpisodeResult, rounds: pd.DataFrame, timeouts: int
) -> dict[str, float]:
    m = episode_metrics(cfg, res)
    quoted = rounds.dropna(subset=["bid", "ask"])
    by = {c: [f for f in res.fills if f.counterparty == c] for c in ("informed", "noise")}
    v = float(res.values[0])

    def pnl(fills: list[Fill]) -> float:
        return float(sum(f.side * (v - f.price) for f in fills))

    my_mid, gm_mid = (quoted["bid"] + quoted["ask"]) / 2, (quoted["gm_bid"] + quoted["gm_ask"]) / 2
    return {
        "true_value": v,
        "pnl": m["pnl_mtm"],
        "spread_capture": m["spread_capture"],
        "adverse_selection": m["adverse_selection"],
        "inventory_pnl": m["inventory_pnl"],
        "fees": m["fees"],
        "pnl_informed": pnl(by["informed"]),
        "pnl_noise": pnl(by["noise"]),
        "fills_informed": float(len(by["informed"])),
        "fills_noise": float(len(by["noise"])),
        "terminal_inventory": m["terminal_q"],
        "rounds_quoted": float(len(quoted)),
        "timeouts": float(timeouts),
        "mean_spread": float((quoted["ask"] - quoted["bid"]).mean()) if len(quoted) else np.nan,
        "gm_mean_spread": float((rounds["gm_ask"] - rounds["gm_bid"]).mean()),
        "mean_abs_mid_error_vs_gm": float((my_mid - gm_mid).abs().mean())
        if len(quoted)
        else np.nan,
    }


def intro(cfg: Config, console: Console) -> None:
    tp, mu = cfg.market.two_point, cfg.flow.glosten_milgrom.mu
    limit = cfg.play.time_limit_sec
    console.print(f"[bold]Market-making game[/bold] - scenario {cfg.scenario.name}")
    console.print(
        f"The asset is worth {tp.v_high:g} (probability {tp.p_high:g}) or {tp.v_low:g}. "
        "You will not be told which until the end."
    )
    console.print(
        f"Each of {cfg.market.n_steps} rounds one trader arrives. With probability {mu:g} it "
        "KNOWS the value and trades only at a profit; otherwise it buys or sells at random."
    )
    console.print(
        "Type your quotes as: bid ask   (for example 99.6 100.4). One lot each side. "
        + (f"You have {limit:g} seconds per quote. " if limit else "")
        + "Type q to quit."
    )


def show_summary(cfg: Config, result: GameResult, console: Console) -> None:
    s, tp = result.summary, cfg.market.two_point
    console.print()
    console.print(f"[bold]The value was {s['true_value']:g}.[/bold]  Your P&L: {s['pnl']:+.2f}")
    table = Table(title="Rounds: your quotes next to Glosten-Milgrom's")
    for name in ("round", "your bid", "your ask", "GM bid", "GM ask", "trade", "P&L of the fill"):
        table.add_column(name, justify="right")
    for r in result.rounds.to_dict("records"):
        if r["trade_side"] == 0:
            trade, fill_pnl = "-", ""
        else:
            verb = "buys" if r["trade_side"] > 0 else "sells"
            trade = f"{r['counterparty']} {verb} @ {r['trade_price']:.2f}"
            fill_pnl = f"{r['fill_pnl_at_true_value']:+.2f}"
        mine = [f"{r[c]:.2f}" if not np.isnan(r[c]) else "none" for c in ("bid", "ask")]
        table.add_row(
            str(r["round"]), *mine, f"{r['gm_bid']:.2f}", f"{r['gm_ask']:.2f}", trade, fill_pnl
        )
    console.print(table)
    console.print(
        f"From informed traders: {s['pnl_informed']:+.2f} over {s['fills_informed']:.0f} fills.   "
        f"From noise traders: {s['pnl_noise']:+.2f} over {s['fills_noise']:.0f} fills."
    )
    console.print(
        f"Decomposition: spread capture {s['spread_capture']:+.2f}, short-term move "
        f"{s['adverse_selection']:+.2f}, inventory {s['inventory_pnl']:+.2f} "
        "(the value does not move in this world, so everything is edge against the true value)."
    )
    console.print(
        f"Your average spread {s['mean_spread']:.2f}; Glosten-Milgrom's {s['gm_mean_spread']:.2f} "
        f"(first quote {cfg.flow.glosten_milgrom.mu * (tp.v_high - tp.v_low):.2f}). "
        f"Average distance of your mid from GM's: {s['mean_abs_mid_error_vs_gm']:.2f}."
    )
    console.print(
        "GM quotes break even on average. They are computed from the trades you saw; a round "
        "without a trade also carries information, which this reference ignores."
    )


def run_game(
    cfg: Config,
    seed: int,
    read_line: ReadLine,
    console: Console,
    clock: Callable[[], float] = time.monotonic,
) -> GameResult:
    """Play one game: one episode of the reference engine with the human as the strategy."""
    if cfg.market.world != "trades_only":
        raise ValueError("play mode needs a two_point scenario (market.world 'trades_only')")
    cfg = with_run_settings(cfg, seed, 1)
    human = HumanStrategy(cfg, read_line, console, clock)
    intro(cfg, console)
    values = episode_values(cfg, 0)
    res = run_episode(cfg, human, values, build_flows(cfg, 0, values))
    # the last round's outcome has not been shown yet (the engine asks for no more quotes)
    last = [f for f in res.fills if f.t == cfg.market.n_steps - 1]
    for f in last:
        verb = "sold to you" if f.side == BOUGHT else "bought from you"
        console.print(f"  -> a trader {verb} at {f.price:.2f}")
    if not last:
        console.print("  -> no trade")
    rounds = round_table(cfg, res)
    result = GameResult(seed, res, rounds, summarize_game(cfg, res, rounds, human.timeouts))
    show_summary(cfg, result, console)
    return result
