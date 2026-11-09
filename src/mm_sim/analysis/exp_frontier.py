"""Experiment kind `inventory_frontier` (EXP-003): inventory-managing strategies
(Avellaneda-Stoikov over a gamma grid, skew over a kappa grid) against the fixed strategy
quoting the same average spread, paired on common random numbers.

For each variant: run it, measure its average quoted spread, run `fixed` with half that
spread on the same seed (the "symmetric" benchmark of the Avellaneda-Stoikov paper), and
compare liquidated P&L episode by episode.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from mm_sim.analysis.experiment import Experiment
from mm_sim.analysis.montecarlo import run_monte_carlo
from mm_sim.analysis.stats import (
    bootstrap_ci,
    certainty_equivalent,
    mean_ci,
    paired_comparison,
)
from mm_sim.analysis.trials import append_trial, count_trials
from mm_sim.config import Config
from mm_sim.reports.common import LIMITATIONS, fmt, setup_lines
from mm_sim.reports.figures import DPI
from mm_sim.runinfo import RunInfo
from mm_sim.strategies.base import build_strategy

# grid key in the experiment file -> (strategy, parameter)
VARIANTS = {"gamma": ("avellaneda_stoikov", "gamma"), "kappa": ("skew", "kappa")}
PRIMARY = ("avellaneda_stoikov", 0.1)  # the variant the magnitude criteria are about
STD_RATIO_LIMIT = 0.75  # primary variant: std ratio CI must be below this
MAX_MEAN_COST = 0.15  # primary variant: mean P&L at most this share below the benchmark
RISK_GRID = {"avellaneda_stoikov": 0.1, "skew": 0.05}  # H1 applies from these values up
BOOTSTRAP_SEED = 20261109


def _one(
    cfg: Config, exp: Experiment, info: RunInfo, strategy: str, param: str, value: float
) -> tuple[dict[str, object], np.ndarray, np.ndarray]:
    level, gamma = cfg.analysis.ci_level, cfg.analysis.cara_gamma
    variant, v_params = build_strategy(cfg, strategy, {param: value})
    ep_v = run_monte_carlo(cfg, variant)
    append_trial(cfg.paths.experiments, info, exp.id, strategy, v_params, exp.seed, exp.episodes)
    spread = float(ep_v["mean_quoted_spread"].mean())
    bench, b_params = build_strategy(cfg, "fixed", {"half_spread": spread / 2})
    ep_b = run_monte_carlo(cfg, bench)
    append_trial(cfg.paths.experiments, info, exp.id, "fixed", b_params, exp.seed, exp.episodes)

    v, b = ep_v["pnl_liquidated"].to_numpy(), ep_b["pnl_liquidated"].to_numpy()
    mean_v, lo_v, hi_v = mean_ci(v, level)
    mean_b, lo_b, hi_b = mean_ci(b, level)
    paired = paired_comparison(v, b, level)
    boot = cfg.analysis.bootstrap_samples
    ratio_lo, ratio_hi = bootstrap_ci(
        lambda i: float(v[i].std(ddof=1) / b[i].std(ddof=1)), len(v), level, BOOTSTRAP_SEED, boot
    )
    ce_lo, ce_hi = bootstrap_ci(
        lambda i: certainty_equivalent(v[i], gamma) - certainty_equivalent(b[i], gamma),
        len(v),
        level,
        BOOTSTRAP_SEED,
        boot,
    )
    row = {
        "strategy": strategy,
        "parameter": param,
        "value": value,
        "mean_quoted_spread": spread,
        "benchmark_quoted_spread": float(ep_b["mean_quoted_spread"].mean()),
        "mean": mean_v,
        "ci_low": lo_v,
        "ci_high": hi_v,
        "std": float(v.std(ddof=1)),
        "bench_mean": mean_b,
        "bench_ci_low": lo_b,
        "bench_ci_high": hi_b,
        "bench_std": float(b.std(ddof=1)),
        "mean_diff": paired["mean_diff"],
        "mean_diff_ci_low": paired["ci_low"],
        "mean_diff_ci_high": paired["ci_high"],
        "paired_ci_width_ratio": paired["ci_width_ratio"],
        "std_ratio": float(v.std(ddof=1) / b.std(ddof=1)),
        "std_ratio_ci_low": ratio_lo,
        "std_ratio_ci_high": ratio_hi,
        "ce": certainty_equivalent(v, gamma),
        "bench_ce": certainty_equivalent(b, gamma),
        "ce_diff_ci_low": ce_lo,
        "ce_diff_ci_high": ce_hi,
        "mean_mtm": float(ep_v["pnl_mtm"].mean()),
        "bench_mean_mtm": float(ep_b["pnl_mtm"].mean()),
        "terminal_q_std": float(ep_v["terminal_q"].std(ddof=1)),
        "bench_terminal_q_std": float(ep_b["terminal_q"].std(ddof=1)),
        "share_at_limit": float(ep_v["share_at_limit"].mean()),
    }
    return row, ep_v["terminal_q"].to_numpy(), ep_b["terminal_q"].to_numpy()


def sweep(
    cfg: Config, exp: Experiment, info: RunInfo
) -> tuple[pd.DataFrame, dict[tuple[str, float], tuple[np.ndarray, np.ndarray]]]:
    rows, inventories = [], {}
    for key, values in exp.grid.items():
        strategy, param = VARIANTS[key]
        for value in values:
            row, q_v, q_b = _one(cfg, exp, info, strategy, param, value)
            rows.append(row)
            inventories[(strategy, value)] = (q_v, q_b)
    return pd.DataFrame(rows), inventories


def verdict(table: pd.DataFrame) -> tuple[str, dict[str, bool]]:
    """The pre-registered rule of EXP-003."""
    risk = table[[r["value"] >= RISK_GRID[r["strategy"]] - 1e-12 for r in table.to_dict("records")]]
    primary = table[(table["strategy"] == PRIMARY[0]) & np.isclose(table["value"], PRIMARY[1])]
    if len(primary) != 1:
        raise ValueError("the grid must contain avellaneda_stoikov gamma = 0.1")
    p = primary.iloc[0]
    checks = {
        "H1 std of liquidated P&L below the benchmark's (ratio CI below 1) for every AS "
        "gamma >= 0.1 and every skew kappa >= 0.05": bool((risk["std_ratio_ci_high"] < 1).all()),
        "H2 AS gamma = 0.1 cuts the std by at least 25% (ratio CI below 0.75)": bool(
            p["std_ratio_ci_high"] < STD_RATIO_LIMIT
        ),
        "H3 AS gamma = 0.1 costs at most 15% of the benchmark's mean liquidated P&L "
        "(paired CI)": bool(p["mean_diff_ci_low"] > -MAX_MEAN_COST * p["bench_mean"]),
        "H4 AS gamma = 0.1 has a higher certainty equivalent than its benchmark "
        "(difference CI above 0)": bool(p["ce_diff_ci_low"] > 0),
    }
    h1, h2, h3, h4 = checks.values()
    if h1 and h2 and h3 and h4:
        return "CONFIRMED", checks
    if not h1 or not h2:
        return "REJECTED", checks
    return "INCONCLUSIVE", checks


def _frontier_figure(table: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    styles = {"avellaneda_stoikov": ("tab:blue", "o", "gamma"), "skew": ("tab:green", "s", "kappa")}
    for strategy, part in table.groupby("strategy"):
        color, marker, symbol = styles[str(strategy)]
        ax.errorbar(
            part["std"],
            part["mean"],
            yerr=[part["mean"] - part["ci_low"], part["ci_high"] - part["mean"]],
            color=color,
            marker=marker,
            ms=5,
            capsize=3,
            lw=1,
            label=f"{strategy} (label: {symbol})",
        )
        for r in part.to_dict("records"):
            ax.annotate(
                f"{r['value']:g}",
                (r["std"], r["mean"]),
                fontsize=7,
                xytext=(4, 4),
                textcoords="offset points",
            )
        ax.errorbar(
            part["bench_std"],
            part["bench_mean"],
            yerr=[
                part["bench_mean"] - part["bench_ci_low"],
                part["bench_ci_high"] - part["bench_mean"],
            ],
            color=color,
            marker="x",
            ls="none",
            ms=6,
            capsize=3,
            alpha=0.6,
            label=f"fixed at the same average spread as {strategy}",
        )
    ax.set_xlabel("std of liquidated episode P&L")
    ax.set_ylabel("mean liquidated episode P&L (95% CI)")
    ax.set_title(
        "Risk-return: inventory management vs fixed quotes at the same spread", fontsize=10
    )
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)


def _inventory_figure(
    inventories: dict[tuple[str, float], tuple[np.ndarray, np.ndarray]], path: Path
) -> None:
    keys = [k for k in inventories if np.isclose(k[1], RISK_GRID[k[0]])]
    fig, axes = plt.subplots(1, len(keys), figsize=(5 * len(keys), 3.6), squeeze=False)
    for ax, key in zip(axes[0], keys, strict=True):
        q_v, q_b = inventories[key]
        lim = int(max(np.abs(q_v).max(), np.abs(q_b).max()))
        bins = np.arange(-lim - 0.5, lim + 1.5)
        ax.hist(q_b, bins=bins, alpha=0.5, color="grey", label="fixed, same spread")
        ax.hist(q_v, bins=bins, alpha=0.6, color="tab:blue", label=f"{key[0]} {key[1]:g}")
        ax.set_xlabel("terminal inventory (lots)")
        ax.set_ylabel("episodes")
        ax.legend(fontsize=7)
    fig.suptitle("Terminal inventory", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)


def _report_md(
    cfg: Config,
    exp: Experiment,
    info: RunInfo,
    table: pd.DataFrame,
    decision: str,
    checks: dict[str, bool],
    trials: int,
) -> str:
    eng = cfg.engine
    lines = [
        f"# {exp.id}: {exp.title}",
        "",
        LIMITATIONS,
        "Specific to this experiment: noise traders only (no informed flow, no jumps). The "
        f"final inventory is closed at a cost of {eng.liq_half_spread:g} + "
        f"{eng.liq_impact:g}*|q| per lot, an invented number; with a zero cost, liquidated and "
        "mark-to-market P&L coincide. Avellaneda-Stoikov is given the true sigma and k.",
        "",
        "## Setup",
        "",
        setup_lines(info, exp.seed, exp.episodes, trials)
        + f"- grids `{json.dumps(exp.grid)}`; each variant is paired with `fixed` at half its "
        "average quoted spread, on the same seed (common random numbers)\n"
        f"- pre-registered as {exp.id}, approved by {exp.approved_by} on {exp.approved_on}\n"
        f"- certainty equivalent with risk aversion {cfg.analysis.cara_gamma:g}; std-ratio and "
        f"CE intervals by paired bootstrap over episodes ({cfg.analysis.bootstrap_samples} "
        "resamples)",
        "",
        "## Results: liquidated P&L per episode",
        "",
        "| strategy | value | avg spread | mean [95% CI] | std | fixed: mean [95% CI] | fixed: std "
        "| std ratio [95% CI] | mean diff [95% CI] | CE | fixed: CE |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in table.to_dict("records"):
        lines.append(
            f"| {r['strategy']} | {r['value']:g} | {fmt(r['mean_quoted_spread'])} "
            f"| {fmt(r['mean'], 2)} [{fmt(r['ci_low'], 2)}, {fmt(r['ci_high'], 2)}] "
            f"| {fmt(r['std'], 2)} "
            f"| {fmt(r['bench_mean'], 2)} [{fmt(r['bench_ci_low'], 2)}, "
            f"{fmt(r['bench_ci_high'], 2)}] "
            f"| {fmt(r['bench_std'], 2)} "
            f"| {fmt(r['std_ratio'])} [{fmt(r['std_ratio_ci_low'])}, "
            f"{fmt(r['std_ratio_ci_high'])}] "
            f"| {fmt(r['mean_diff'], 2)} [{fmt(r['mean_diff_ci_low'], 2)}, "
            f"{fmt(r['mean_diff_ci_high'], 2)}] "
            f"| {fmt(r['ce'], 2)} | {fmt(r['bench_ce'], 2)} |"
        )
    ratio = table["paired_ci_width_ratio"]
    lines += [
        "",
        "`mean diff` is the mean of the per-episode differences (strategy minus fixed). Pairing "
        f"on common random numbers made its CI {fmt(float(ratio.min()), 2)} to "
        f"{fmt(float(ratio.max()), 2)} times as wide as the unpaired CI would be.",
        "",
        "## P&L decomposition and inventory (mean per episode)",
        "",
        "| strategy | value | mark-to-market mean | fixed: MTM mean | std of terminal inventory "
        "| fixed: std of terminal inventory | share of steps at the limit |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in table.to_dict("records"):
        lines.append(
            f"| {r['strategy']} | {r['value']:g} | {fmt(r['mean_mtm'], 2)} "
            f"| {fmt(r['bench_mean_mtm'], 2)} | {fmt(r['terminal_q_std'], 2)} "
            f"| {fmt(r['bench_terminal_q_std'], 2)} | {fmt(r['share_at_limit'], 4)} |"
        )
    lines += [
        "",
        "The difference between mark-to-market and liquidated P&L is the cost of closing the "
        "final inventory.",
        "",
        "![risk-return frontier](frontier.png)",
        "",
        "![terminal inventory](terminal_inventory.png)",
        "",
        "## Verdict against the pre-registered hypothesis",
        "",
    ]
    lines += [f"- {'PASS' if ok else 'FAIL'}: {name}" for name, ok in checks.items()]
    lines += [
        "",
        f"**{decision}**",
        "",
        "## What depends on the model's assumptions",
        "",
        "- The value is a martingale, so inventory earns nothing on average and reducing it is "
        "almost free. With a drift or with informed flow the trade-off changes.",
        "- Skewing works because noise traders respond to price (the exponential fill "
        "intensity): a better price reliably attracts the offsetting trade.",
        "- Avellaneda-Stoikov knows the true sigma and k and the horizon T; its spread widens "
        "early in the episode by construction.",
        "- The size of the gain in liquidated P&L depends directly on the invented liquidation "
        "cost.",
        "",
    ]
    return "\n".join(lines)


def run(cfg: Config, exp: Experiment, info: RunInfo, out_dir: Path) -> str:
    out_dir.mkdir(parents=True, exist_ok=False)  # an existing directory means it already ran
    table, inventories = sweep(cfg, exp, info)
    decision, checks = verdict(table)
    table.to_csv(out_dir / "frontier.csv", index=False, float_format="%.10g")
    summary = {
        "run": info.as_dict(),
        "experiment": exp.id,
        "seed": exp.seed,
        "episodes": exp.episodes,
        "decision": decision,
        "checks": checks,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    _frontier_figure(table, out_dir / "frontier.png")
    _inventory_figure(inventories, out_dir / "terminal_inventory.png")
    trials = count_trials(cfg.paths.experiments)
    (out_dir / "report.md").write_text(_report_md(cfg, exp, info, table, decision, checks, trials))
    return decision
