"""Figures. Agg backend: PNG files only, no GUI windows."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from mm_sim.engine.reference import BOUGHT, EpisodeResult

DPI = 100


def example_episode_figure(res: EpisodeResult, title: str, path: Path) -> None:
    """Value, quotes and fills on top; inventory below."""
    n = len(res.bids)
    steps = np.arange(n)
    fig, (ax, ax_q) = plt.subplots(
        2, 1, figsize=(9, 5.5), sharex=True, gridspec_kw={"height_ratios": [3, 1]}
    )
    ax.plot(np.arange(n + 1), res.values, color="black", lw=1.0, label="true value V")
    ax.plot(steps, res.bids, color="tab:blue", lw=0.6, alpha=0.7, label="bid")
    ax.plot(steps, res.asks, color="tab:red", lw=0.6, alpha=0.7, label="ask")
    buys = [(f.t, f.price) for f in res.fills if f.side == BOUGHT]
    sells = [(f.t, f.price) for f in res.fills if f.side != BOUGHT]
    if buys:
        ax.scatter(*zip(*buys, strict=True), marker="^", s=14, color="tab:blue", label="MM buys")
    if sells:
        ax.scatter(*zip(*sells, strict=True), marker="v", s=14, color="tab:red", label="MM sells")
    ax.set_ylabel("price")
    ax.set_title(title)
    ax.legend(loc="best", fontsize=8, ncol=5)
    ax_q.step(np.arange(n + 1), res.inventory, where="post", color="tab:green", lw=1.0)
    ax_q.axhline(0, color="grey", lw=0.5)
    ax_q.set_ylabel("inventory (lots)")
    ax_q.set_xlabel("step")
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)


def markout_figure(curve: pd.DataFrame, title: str, path: Path) -> None:
    """Mean markout per fill against the horizon, one line per counterparty, with CIs."""
    fig, ax = plt.subplots(figsize=(7, 4))
    colors = {"noise": "tab:blue", "informed": "tab:red"}
    for name, part in curve.groupby("counterparty"):
        if int(part["fills"].iloc[0]) == 0:
            continue
        ax.errorbar(
            part["horizon"],
            part["markout"],
            yerr=[part["markout"] - part["ci_low"], part["ci_high"] - part["markout"]],
            marker="o",
            ms=4,
            capsize=3,
            color=colors.get(str(name), "black"),
            label=f"{name} fills (n={int(part['fills'].iloc[0])})",
        )
    ax.axhline(0, color="grey", lw=0.5)
    ax.set_xscale("symlog", linthresh=1)
    ax.set_xlabel("horizon h (steps after the fill)")
    ax.set_ylabel("mean markout per fill")
    ax.set_title(title, fontsize=9)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
