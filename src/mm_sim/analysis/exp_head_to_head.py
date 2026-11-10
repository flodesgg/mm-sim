"""Experiment kind `head_to_head` (EXP-007): two strategies on the same random numbers.

Strategy A against strategy B, episode by episode, on liquidated P&L (the pre-registered
criteria) and on mark-to-market P&L (reported next to it). The experiment file names the two
strategies and their parameters in `settings`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.typing import NDArray

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
from mm_sim.reports.sections import Representative, with_representative
from mm_sim.runinfo import RunInfo
from mm_sim.strategies.base import build_strategy

TABLE_FILE = "head_to_head.csv"
Sample = NDArray[np.float64]
BOOTSTRAP_SEED = 20261110
MEASURES = {"pnl_liquidated": "liquidated P&L", "pnl_mtm": "mark-to-market P&L"}


def _std_ratio(a: Sample, b: Sample) -> Callable[[NDArray[np.int64]], float]:
    """std(A) / std(B) on resampled episodes (the same episodes for both: paired)."""

    def statistic(i: NDArray[np.int64]) -> float:
        return float(a[i].std(ddof=1) / b[i].std(ddof=1))

    return statistic


def _ce_diff(a: Sample, b: Sample, gamma: float) -> Callable[[NDArray[np.int64]], float]:
    def statistic(i: NDArray[np.int64]) -> float:
        return certainty_equivalent(a[i], gamma) - certainty_equivalent(b[i], gamma)

    return statistic


def sweep(
    cfg: Config, exp: Experiment, info: RunInfo, log: bool = True
) -> tuple[pd.DataFrame, Representative]:
    """One row per P&L measure: A, B, and the paired comparison A - B."""
    an = cfg.analysis
    level, gamma, boot = an.ci_level, an.cara_gamma, an.bootstrap_samples
    episodes = {}
    names = {}
    for key in ("a", "b"):
        spec = exp.settings[key]
        built, params = build_strategy(cfg, spec["strategy"], spec["params"])
        if log:
            append_trial(
                cfg.paths.experiments,
                info,
                exp.id,
                spec["strategy"],
                params,
                exp.seed,
                exp.episodes,
            )
        episodes[key] = run_monte_carlo(cfg, built)
        names[key] = f"{spec['strategy']} {json.dumps(params)}"
    rows = []
    for column in MEASURES:
        a, b = episodes["a"][column].to_numpy(), episodes["b"][column].to_numpy()
        mean_a, lo_a, hi_a = mean_ci(a, level)
        mean_b, lo_b, hi_b = mean_ci(b, level)
        paired = paired_comparison(a, b, level)
        ratio_lo, ratio_hi = bootstrap_ci(_std_ratio(a, b), len(a), level, BOOTSTRAP_SEED, boot)
        ce_lo, ce_hi = bootstrap_ci(_ce_diff(a, b, gamma), len(a), level, BOOTSTRAP_SEED, boot)
        rows.append(
            {
                "measure": column,
                "a": names["a"],
                "b": names["b"],
                "mean_a": mean_a,
                "mean_a_ci_low": lo_a,
                "mean_a_ci_high": hi_a,
                "std_a": float(a.std(ddof=1)),
                "mean_b": mean_b,
                "mean_b_ci_low": lo_b,
                "mean_b_ci_high": hi_b,
                "std_b": float(b.std(ddof=1)),
                "mean_diff": paired["mean_diff"],
                "mean_diff_ci_low": paired["ci_low"],
                "mean_diff_ci_high": paired["ci_high"],
                "std_ratio": float(a.std(ddof=1) / b.std(ddof=1)),
                "std_ratio_ci_low": ratio_lo,
                "std_ratio_ci_high": ratio_hi,
                "ce_a": certainty_equivalent(a, gamma),
                "ce_b": certainty_equivalent(b, gamma),
                "ce_diff": certainty_equivalent(a, gamma) - certainty_equivalent(b, gamma),
                "ce_diff_ci_low": ce_lo,
                "ce_diff_ci_high": ce_hi,
                "quoted_spread_a": float(episodes["a"]["mean_quoted_spread"].mean()),
                "quoted_spread_b": float(episodes["b"]["mean_quoted_spread"].mean()),
                "terminal_q_std_a": float(episodes["a"]["terminal_q"].std(ddof=1)),
                "terminal_q_std_b": float(episodes["b"]["terminal_q"].std(ddof=1)),
                "mean_abs_q_a": float(episodes["a"]["mean_abs_q"].mean()),
                "mean_abs_q_b": float(episodes["b"]["mean_abs_q"].mean()),
            }
        )
    spec = exp.settings["a"]
    rep = Representative(cfg, spec["strategy"], dict(spec["params"]), episodes["a"], names["a"])
    return pd.DataFrame(rows), rep


def verdict(table: pd.DataFrame) -> tuple[str, dict[str, bool]]:
    """The pre-registered rule of EXP-007, on liquidated P&L."""
    r = table[table["measure"] == "pnl_liquidated"].iloc[0]
    checks = {
        "H1 A has a higher mean liquidated P&L than B (paired CI above 0)": bool(
            r["mean_diff_ci_low"] > 0
        ),
        "H2 A's std of liquidated P&L is not above B's (ratio CI upper end below 1)": bool(
            r["std_ratio_ci_high"] < 1
        ),
    }
    if all(checks.values()):
        return "CONFIRMED", checks
    if r["mean_diff_ci_high"] < 0 or r["std_ratio_ci_low"] > 1:
        return "REJECTED", checks
    return "INCONCLUSIVE", checks


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
    first = table.iloc[0]
    lines = [
        f"# {exp.id}: {exp.title}",
        "",
        LIMITATIONS,
        "Specific to this experiment: noise traders only. The final inventory is closed at "
        f"{eng.liq_half_spread:g} + {eng.liq_impact:g}*|q| per lot (invented). Avellaneda-Stoikov "
        "is derived for mark-to-market wealth without that cost and is given the true sigma "
        "and k. One parameter setting of each strategy is compared, not the best of each.",
        "",
        "## Setup",
        "",
        setup_lines(info, exp.seed, exp.episodes, trials)
        + f"- A = `{first['a']}`, B = `{first['b']}`, same seed (common random numbers)\n"
        f"- pre-registered as {exp.id}, approved by {exp.approved_by} on {exp.approved_on}\n"
        f"- CE with risk aversion {cfg.analysis.cara_gamma:g}; std-ratio and CE intervals by "
        f"paired bootstrap ({cfg.analysis.bootstrap_samples} resamples)",
        "",
        "## Results",
        "",
        "| measure | A: mean [95% CI] | A: std | B: mean [95% CI] | B: std "
        "| mean A - B [95% CI] | std A / B [95% CI] | CE A - B [95% CI] |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in table.to_dict("records"):
        lines.append(
            f"| {MEASURES[r['measure']]} "
            f"| {fmt(r['mean_a'], 2)} [{fmt(r['mean_a_ci_low'], 2)}, "
            f"{fmt(r['mean_a_ci_high'], 2)}] "
            f"| {fmt(r['std_a'], 2)} "
            f"| {fmt(r['mean_b'], 2)} [{fmt(r['mean_b_ci_low'], 2)}, "
            f"{fmt(r['mean_b_ci_high'], 2)}] "
            f"| {fmt(r['std_b'], 2)} "
            f"| {fmt(r['mean_diff'], 2)} [{fmt(r['mean_diff_ci_low'], 2)}, "
            f"{fmt(r['mean_diff_ci_high'], 2)}] "
            f"| {fmt(r['std_ratio'])} [{fmt(r['std_ratio_ci_low'])}, "
            f"{fmt(r['std_ratio_ci_high'])}] "
            f"| {fmt(r['ce_diff'], 2)} [{fmt(r['ce_diff_ci_low'], 2)}, "
            f"{fmt(r['ce_diff_ci_high'], 2)}] |"
        )
    lines += [
        "",
        f"Average quoted spread: A {fmt(float(first['quoted_spread_a']))}, "
        f"B {fmt(float(first['quoted_spread_b']))}. Std of terminal inventory: "
        f"A {fmt(float(first['terminal_q_std_a']), 2)}, "
        f"B {fmt(float(first['terminal_q_std_b']), 2)}. "
        f"Mean |inventory| during the episode: A {fmt(float(first['mean_abs_q_a']), 2)}, "
        f"B {fmt(float(first['mean_abs_q_b']), 2)}.",
        "",
        "The criteria are on liquidated P&L. The mark-to-market row is the objective "
        "Avellaneda-Stoikov is derived for; it is reported without a pre-registered prediction.",
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
        "- A martingale value and noise-only flow: leaning toward the mid is never exploited.",
        "- The liquidation cost decides how much terminal inventory matters.",
        "- One (gamma, kappa) pair. Another pair can order the two strategies differently.",
        "",
    ]
    return "\n".join(lines)


def run(cfg: Config, exp: Experiment, info: RunInfo, out_dir: Path, log: bool = True) -> str:
    out_dir.mkdir(parents=True, exist_ok=False)  # an existing directory means it already ran
    table, rep = sweep(cfg, exp, info, log)
    decision, checks = verdict(table)
    table.to_csv(out_dir / TABLE_FILE, index=False, float_format="%.10g")
    summary = {
        "run": info.as_dict(),
        "experiment": exp.id,
        "seed": exp.seed,
        "episodes": exp.episodes,
        "decision": decision,
        "checks": checks,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    trials = count_trials(cfg.paths.experiments)
    report = _report_md(cfg, exp, info, table, decision, checks, trials)
    (out_dir / "report.md").write_text(with_representative(report, rep, out_dir))
    return decision
