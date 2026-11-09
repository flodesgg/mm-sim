"""Report sections shared by run reports and experiment reports: the P&L decomposition table,
markout curves, an example episode and the terminal-inventory histogram.

Every report has the same order: limitations, setup, results with CIs, P&L decomposition,
figures, verdict (experiments), what depends on the model's assumptions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from mm_sim.analysis.markouts import markout_curve
from mm_sim.analysis.stats import mean_ci
from mm_sim.config import Config
from mm_sim.engine.reference import simulate_episode
from mm_sim.reports.common import fmt
from mm_sim.reports.figures import DPI, example_episode_figure, markout_figure
from mm_sim.strategies.base import build_strategy

IDENTITY_TOLERANCE = 1e-9
PARTS = {
    "spread_capture": "spread capture",
    "adverse_selection": "short-term move after fills (negative = adverse selection)",
    "inventory_pnl": "inventory / holding P&L",
    "fees": "fees paid (subtracted)",
    "pnl_mtm": "**total: mark-to-market P&L**",
}


@dataclass(frozen=True)
class Representative:
    """One grid point of an experiment, shown in detail in its report."""

    cfg: Config
    strategy: str
    params: dict[str, object]
    episodes: pd.DataFrame
    label: str


def decomposition_error(episodes: pd.DataFrame) -> float:
    """Largest |spread + short-term + inventory - fees - P&L| over the episodes."""
    parts = episodes["spread_capture"] + episodes["adverse_selection"] + episodes["inventory_pnl"]
    return float((parts - episodes["fees"] - episodes["pnl_mtm"]).abs().max())


def decomposition_lines(cfg: Config, episodes: pd.DataFrame) -> list[str]:
    level = cfg.analysis.ci_level
    lines = [f"| part | mean | {level:.0%} CI |", "|---|---|---|"]
    for column, label in PARTS.items():
        mean, lo, hi = mean_ci(episodes[column], level)
        lines.append(f"| {label} | {fmt(mean)} | [{fmt(lo)}, {fmt(hi)}] |")
    err = decomposition_error(episodes)
    flag = (
        "" if err <= IDENTITY_TOLERANCE else " **SUSPICIOUS: the decomposition does not add up.**"
    )
    lines += [
        "",
        f"Decomposition horizon h = {cfg.accounting.markout_horizon_steps} steps. Identity "
        f"check: the largest per-episode error of `spread + short-term + inventory - fees = "
        f"P&L` is {err:.2e}.{flag}",
    ]
    return lines


def markout_lines(cfg: Config, episodes: pd.DataFrame) -> list[str]:
    level = cfg.analysis.ci_level
    lines = [f"| counterparty | fills | h | markout | {level:.0%} CI |", "|---|---|---|---|---|"]
    for r in markout_curve(cfg, episodes).to_dict("records"):
        if r["fills"] == 0:
            continue
        lines.append(
            f"| {r['counterparty']} | {r['fills']} | {r['horizon']} "
            f"| {fmt(float(r['markout']), 4)} "
            f"| [{fmt(float(r['ci_low']), 4)}, {fmt(float(r['ci_high']), 4)}] |"
        )
    return lines


def inventory_figure(episodes: pd.DataFrame, title: str, path: Path) -> None:
    q = episodes["terminal_q"].to_numpy()
    lim = int(np.abs(q).max()) if len(q) else 0
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.hist(q, bins=list(np.arange(-lim - 0.5, lim + 1.5)), color="tab:green", alpha=0.7)
    ax.set_xlabel("terminal inventory (lots)")
    ax.set_ylabel("episodes")
    ax.set_title(title, fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)


def representative_sections(rep: Representative, out_dir: Path) -> list[str]:
    """Decomposition table and the standard figures for one representative grid point."""
    cfg, ep = rep.cfg, rep.episodes
    strategy, _ = build_strategy(cfg, rep.strategy, rep.params)
    title = f"{rep.strategy} {json.dumps(rep.params)}"
    markout_figure(markout_curve(cfg, ep), f"Markouts: {rep.label}", out_dir / "markouts.png")
    example_episode_figure(
        simulate_episode(cfg, strategy, 0),
        f"{rep.label}: episode 0 (seed {cfg.analysis.seed})",
        out_dir / "example_episode.png",
    )
    inventory_figure(ep, f"Terminal inventory: {rep.label}", out_dir / "inventory_histogram.png")
    return [
        f"## Representative grid point in detail: {rep.label}",
        "",
        f"Strategy `{title}`, {len(ep)} episodes. One grid point, shown so that the mechanics "
        "behind the table above are visible.",
        "",
        "### P&L decomposition (mean per episode)",
        "",
        *decomposition_lines(cfg, ep),
        "",
        "### Markouts by counterparty (mean per fill)",
        "",
        *markout_lines(cfg, ep),
        "",
        "![markout curves](markouts.png)",
        "",
        "![terminal inventory](inventory_histogram.png)",
        "",
        "![example episode](example_episode.png)",
        "",
        "One episode is an illustration, not evidence.",
        "",
    ]


VERDICT_HEADING = "## Verdict against the pre-registered hypothesis"


def with_representative(report_md: str, rep: Representative, out_dir: Path) -> str:
    """Insert the representative-grid-point sections before the verdict."""
    head, heading, tail = report_md.partition(VERDICT_HEADING)
    if not heading:
        raise ValueError("the report has no verdict section")
    return head + "\n".join(representative_sections(rep, out_dir)) + "\n" + heading + tail
