"""Saving games and plotting progress: play/games/<timestamp>.csv, play/history.csv."""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from mm_sim.config import Config
from mm_sim.play.game import GameResult
from mm_sim.reports.figures import DPI

HISTORY_COLUMNS = [
    "timestamp",
    "scenario",
    "seed",
    "config_hash",
    "rounds",
    "mu",
    "v_high",
    "v_low",
    "true_value",
    "pnl",
    "pnl_informed",
    "pnl_noise",
    "fills_informed",
    "fills_noise",
    "terminal_inventory",
    "rounds_quoted",
    "timeouts",
    "mean_spread",
    "gm_mean_spread",
    "mean_abs_mid_error_vs_gm",
]


def save_game(cfg: Config, config_hash: str, result: GameResult, timestamp: str) -> Path:
    """Write the round table and append one line to the history. Returns the game file."""
    games = cfg.paths.play / "games"
    games.mkdir(parents=True, exist_ok=True)
    path = games / f"{timestamp}.csv"
    result.rounds.to_csv(path, index=False, float_format="%.6g")
    tp = cfg.market.two_point
    row = {
        "timestamp": timestamp,
        "scenario": cfg.scenario.name,
        "seed": result.seed,
        "config_hash": config_hash,
        "rounds": cfg.market.n_steps,
        "mu": cfg.flow.glosten_milgrom.mu,
        "v_high": tp.v_high,
        "v_low": tp.v_low,
        **{k: v for k, v in result.summary.items() if k in HISTORY_COLUMNS},
    }
    history = cfg.paths.play / "history.csv"
    new = not history.exists()
    with history.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HISTORY_COLUMNS)
        if new:
            w.writeheader()
        w.writerow({k: (f"{v:.6g}" if isinstance(v, float) else v) for k, v in row.items()})
    return path


def load_history(cfg: Config) -> pd.DataFrame:
    path = cfg.paths.play / "history.csv"
    if not path.exists():
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    return pd.read_csv(path)


def stats_table(history: pd.DataFrame) -> pd.DataFrame:
    """Per scenario: games, mean P&L, share of P&L lost to informed flow, mid error vs GM."""
    grouped = history.groupby("scenario")
    return pd.DataFrame(
        {
            "games": grouped.size(),
            "mean_pnl": grouped["pnl"].mean(),
            "mean_pnl_informed": grouped["pnl_informed"].mean(),
            "mean_pnl_noise": grouped["pnl_noise"].mean(),
            "mean_spread": grouped["mean_spread"].mean(),
            "gm_mean_spread": grouped["gm_mean_spread"].mean(),
            "mean_abs_mid_error_vs_gm": grouped["mean_abs_mid_error_vs_gm"].mean(),
        }
    ).reset_index()


def progress_figure(history: pd.DataFrame, path: Path) -> None:
    """P&L per game and the distance from the Glosten-Milgrom mid, in playing order."""
    fig, (ax, ax_e) = plt.subplots(2, 1, figsize=(8, 6), sharex=True)
    for scenario, part in history.groupby("scenario"):
        ax.plot(part.index + 1, part["pnl"], "o-", ms=4, lw=0.8, label=str(scenario))
        ax_e.plot(part.index + 1, part["mean_abs_mid_error_vs_gm"], "o-", ms=4, lw=0.8)
    ax.axhline(0, color="grey", lw=0.5)
    ax.set_ylabel("P&L of the game")
    ax.set_title("Play mode progress (Glosten-Milgrom quotes break even on average)", fontsize=10)
    ax.legend(fontsize=8)
    ax_e.set_ylabel("mean |your mid - GM mid|")
    ax_e.set_xlabel("game number")
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
