"""Experiment kind `fixed_spread_sweep` (EXP-001): the fixed strategy over a half-spread grid
against noise flow only, compared with the closed-form mean and std of P&L.

Every grid point runs on the same root seed (common random numbers). The verdict rule below
is the one written in the experiment file before the run.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from mm_sim.analysis import theory
from mm_sim.analysis.experiment import Experiment
from mm_sim.analysis.montecarlo import run_monte_carlo
from mm_sim.analysis.stats import mean_ci
from mm_sim.analysis.trials import append_trial, count_trials
from mm_sim.config import Config
from mm_sim.reports.common import LIMITATIONS, fmt, setup_lines
from mm_sim.reports.figures import DPI
from mm_sim.runinfo import RunInfo
from mm_sim.strategies.base import build_strategy

Z_LIMIT = 3.5  # |simulated mean - theory| / standard error allowed at every grid point
STD_TOLERANCE = 0.10  # simulated std / theory std must be within 1 +- this


def sweep(cfg: Config, exp: Experiment, info: RunInfo) -> pd.DataFrame:
    """One row per half-spread. Appends one trial-log line per grid point."""
    level = cfg.analysis.ci_level
    rows = []
    for h in exp.grid["half_spread"]:
        strategy, params = build_strategy(cfg, exp.strategy, {"half_spread": h})
        ep = run_monte_carlo(cfg, strategy)
        append_trial(
            cfg.paths.experiments, info, exp.id, exp.strategy, params, exp.seed, exp.episodes
        )
        pnl = ep["pnl_mtm"]
        mean, lo, hi = mean_ci(pnl, level)
        se = float(pnl.std(ddof=1)) / np.sqrt(len(pnl))
        # paired check of the fill mechanics: P&L minus its conditional expectation
        diff = pnl - ep["noise_capture_expected"]
        theory_mean = theory.fixed_noise_mean_pnl(cfg, h)
        theory_std = theory.fixed_noise_pnl_std(cfg, h)
        rows.append(
            {
                "half_spread": h,
                "mean_pnl": mean,
                "ci_low": lo,
                "ci_high": hi,
                "se": se,
                "theory_mean": theory_mean,
                "theory_mean_no_tick": theory.fixed_noise_mean_pnl(cfg, h, tick=0.0),
                "z_mean": (mean - theory_mean) / se,
                "z_paired": float(diff.mean()) / (float(diff.std(ddof=1)) / np.sqrt(len(diff))),
                "std_pnl": float(pnl.std(ddof=1)),
                "theory_std": theory_std,
                "std_ratio": float(pnl.std(ddof=1)) / theory_std,
                "fills_per_episode": float(ep["volume"].mean()),
                "theory_fills": 2 * cfg.market.n_steps * theory.fill_probability_per_side(cfg, h),
                "share_at_limit": float(ep["share_at_limit"].mean()),
            }
        )
    return pd.DataFrame(rows)


def verdict(table: pd.DataFrame) -> tuple[str, dict[str, bool]]:
    """The pre-registered rule of EXP-001."""
    h = table["half_spread"].to_numpy()
    best_sim = int(table["mean_pnl"].to_numpy().argmax())
    best_theory = int(table["theory_mean"].to_numpy().argmax())
    checks = {
        "C1 mean matches theory (|z| <= 3.5 at every grid point)": bool(
            (table["z_mean"].abs() <= Z_LIMIT).all()
        ),
        "C2 best simulated half-spread is the theory's best grid point or its neighbour": abs(
            best_sim - best_theory
        )
        <= 1,
        "C3a std within 10% of theory at every grid point": bool(
            ((table["std_ratio"] - 1).abs() <= STD_TOLERANCE).all()
        ),
        "C3b std at the widest half-spread is below std at the narrowest": bool(
            table["std_pnl"].to_numpy()[h.argmax()] < table["std_pnl"].to_numpy()[h.argmin()]
        ),
    }
    c1, c2, c3a, c3b = checks.values()
    if c1 and c2 and c3a and c3b:
        return "CONFIRMED", checks
    if not c1 or not c3a:
        return "REJECTED", checks
    return "INCONCLUSIVE", checks


def _figure(cfg: Config, table: pd.DataFrame, path: Path) -> None:
    hs = np.linspace(table["half_spread"].min(), table["half_spread"].max(), 200)
    fig, (ax, ax_s) = plt.subplots(1, 2, figsize=(10, 4))
    ax.plot(hs, [theory.fixed_noise_mean_pnl(cfg, float(x)) for x in hs], color="black", lw=1)
    ax.errorbar(
        table["half_spread"],
        table["mean_pnl"],
        yerr=[table["mean_pnl"] - table["ci_low"], table["ci_high"] - table["mean_pnl"]],
        fmt="o",
        ms=4,
        color="tab:blue",
        capsize=3,
    )
    ax.axvline(1 / cfg.flow.noise.k, color="grey", ls=":", lw=1)
    ax.set_xlabel("half-spread h")
    ax.set_ylabel("mean episode P&L")
    ax.set_title("Mean P&L: simulation (95% CI) vs theory (line); dotted: h = 1/k")
    ax.title.set_fontsize(9)
    ax_s.plot(hs, [theory.fixed_noise_pnl_std(cfg, float(x)) for x in hs], color="black", lw=1)
    ax_s.plot(table["half_spread"], table["std_pnl"], "o", ms=4, color="tab:red")
    ax_s.set_xlabel("half-spread h")
    ax_s.set_ylabel("std of episode P&L")
    ax_s.set_title("P&L std: simulation (points) vs theory (line)")
    ax_s.title.set_fontsize(9)
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
    lines = [
        f"# {exp.id}: {exp.title}",
        "",
        LIMITATIONS,
        "This experiment has noise traders only: no informed flow, no jumps, no latency, no fees.",
        "",
        "## Setup",
        "",
        setup_lines(info, exp.seed, exp.episodes, trials)
        + f"- strategy `{exp.strategy}`, grid `{json.dumps(exp.grid)}`; every grid point uses "
        "the same seed (common random numbers)\n"
        f"- pre-registered in `experiments/` as {exp.id}, approved by {exp.approved_by} on "
        f"{exp.approved_on}",
        "",
        "## Results",
        "",
        "| h | mean P&L | 95% CI | theory | z | paired z | std | theory std | ratio "
        "| fills | theory fills | at limit |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    records: list[dict[str, float]] = [
        {str(k): float(v) for k, v in row.items()} for row in table.to_dict("records")
    ]
    for r in records:
        lines.append(
            f"| {r['half_spread']:g} | {fmt(r['mean_pnl'], 2)} "
            f"| [{fmt(r['ci_low'], 2)}, {fmt(r['ci_high'], 2)}] "
            f"| {fmt(r['theory_mean'], 2)} | {fmt(r['z_mean'], 2)} | {fmt(r['z_paired'], 2)} "
            f"| {fmt(r['std_pnl'], 2)} | {fmt(r['theory_std'], 2)} | {fmt(r['std_ratio'])} "
            f"| {fmt(r['fills_per_episode'], 1)} | {fmt(r['theory_fills'], 1)} "
            f"| {fmt(r['share_at_limit'], 4)} |"
        )
    best_h = max(records, key=lambda r: r["mean_pnl"])["half_spread"]
    lines += [
        "",
        "`theory` averages the closed form over the tick offset; `z` = (mean - theory) / standard "
        "error; `paired z` tests P&L minus its expectation given the actual quotes; `at limit` "
        "is the share of steps at the inventory limit (the theory assumes it is 0).",
        "",
        f"Highest simulated mean P&L: h = {best_h:g}. Continuous optimum of the "
        f"closed form: h = {fmt(theory.optimal_fixed_half_spread(cfg))}; 1/k = "
        f"{fmt(1 / cfg.flow.noise.k)}.",
        "",
        "![mean and std of P&L against the half-spread](pnl_vs_half_spread.png)",
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
        "- The optimum near 1/k is a property of the exponential fill intensity. Another "
        "intensity shape gives another optimum.",
        "- With noise traders only, a narrower spread is never punished by informed flow; "
        "EXP-002 adds it.",
        "- P&L std comes almost entirely from carried inventory on a random-walk value; with no "
        "inventory control it grows with the number of fills.",
        "",
    ]
    return "\n".join(lines)


def run(cfg: Config, exp: Experiment, info: RunInfo, out_dir: Path) -> str:
    out_dir.mkdir(parents=True, exist_ok=False)  # an existing directory means it already ran
    table = sweep(cfg, exp, info)
    decision, checks = verdict(table)
    table.to_csv(out_dir / "sweep.csv", index=False, float_format="%.10g")
    summary = {
        "run": info.as_dict(),
        "experiment": exp.id,
        "seed": exp.seed,
        "episodes": exp.episodes,
        "decision": decision,
        "checks": checks,
        "optimal_half_spread_theory": theory.optimal_fixed_half_spread(cfg),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    _figure(cfg, table, out_dir / "pnl_vs_half_spread.png")
    trials = count_trials(cfg.paths.experiments)
    (out_dir / "report.md").write_text(_report_md(cfg, exp, info, table, decision, checks, trials))
    return decision
