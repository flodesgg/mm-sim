"""Experiment kind `independent_seed_check` (EXP-006): are the closed forms biased?

EXP-001 and EXP-002 confirmed the closed forms, but all their grid points shared one seed, so
deviations in one direction (every std a little below the formula; every mean about two
standard errors above theory) could be one fluctuation or a real bias. Here every cell has
its OWN seed and more episodes, so the cells are independent and a bias of the size seen
there would show.

  part A  std of P&L, fixed strategy, noise only          vs theory.fixed_noise_pnl_std
  part B  mean P&L, fixed strategy, noise + informed flow vs theory.fixed_mean_pnl_with_informed
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from mm_sim.analysis import theory
from mm_sim.analysis.experiment import Experiment
from mm_sim.analysis.montecarlo import run_monte_carlo, with_run_settings
from mm_sim.analysis.stats import bootstrap_ci
from mm_sim.analysis.trials import append_trial, count_trials
from mm_sim.config import Config, with_overrides
from mm_sim.reports.common import LIMITATIONS, fmt, setup_lines
from mm_sim.reports.sections import Representative, with_representative
from mm_sim.runinfo import RunInfo
from mm_sim.strategies.base import build_strategy

TABLE_FILE = "cells.csv"
Z_LIMIT = 3.0
SEED_STEP = 1000  # cell i uses seed exp.seed + i * SEED_STEP
BOOTSTRAP_SEED = 20261110


def _std_of(pnl: NDArray[np.float64]) -> Callable[[NDArray[np.int64]], float]:
    def statistic(i: NDArray[np.int64]) -> float:
        return float(pnl[i].std(ddof=1))

    return statistic


def sweep(
    cfg: Config, exp: Experiment, info: RunInfo, log: bool = True
) -> tuple[pd.DataFrame, Representative]:
    """One row per cell, each on its own seed. The representative cell is the first of
    part B."""
    s = exp.settings
    cells: list[tuple[str, Config, float, float]] = [
        ("A_std", cfg, float(h), 0.0) for h in s["std_half_spreads"]
    ]
    informed = with_overrides(cfg, s["informed"])
    for lam, h in s["mean_cells"]:
        cell_cfg = with_overrides(informed, {"flow.informed.intensity": float(lam)})
        cells.append(("B_mean", cell_cfg, float(h), float(lam)))

    rows = []
    rep: Representative | None = None
    for i, (part, base, h, lam) in enumerate(cells):
        seed = exp.seed + i * SEED_STEP
        c = with_run_settings(base, seed, exp.episodes)
        strategy, params = build_strategy(c, "fixed", {"half_spread": h})
        ep = run_monte_carlo(c, strategy)
        if log:
            extra = {**params, "part": part, "flow.informed.intensity": lam}
            append_trial(cfg.paths.experiments, info, exp.id, "fixed", extra, seed, exp.episodes)
        pnl = ep["pnl_mtm"].to_numpy()
        if part == "A_std":
            simulated, predicted = float(pnl.std(ddof=1)), theory.fixed_noise_pnl_std(c, h)
            lo, hi = bootstrap_ci(
                _std_of(pnl),
                len(pnl),
                c.analysis.ci_level,
                BOOTSTRAP_SEED,
                c.analysis.bootstrap_samples,
            )
            se = (hi - lo) / (2 * 1.959964)  # bootstrap CI half-width -> standard error
        else:
            simulated = float(pnl.mean())
            predicted = theory.fixed_mean_pnl_with_informed(c, h)
            se = float(pnl.std(ddof=1)) / float(np.sqrt(len(pnl)))
            lo, hi = simulated - 1.959964 * se, simulated + 1.959964 * se
            if rep is None:
                label = f"informed intensity {lam:g}, half-spread {h:g}, seed {seed}"
                rep = Representative(c, "fixed", params, ep, label)
        rows.append(
            {
                "part": part,
                "informed_intensity": lam,
                "half_spread": h,
                "seed": seed,
                "simulated": simulated,
                "ci_low": lo,
                "ci_high": hi,
                "theory": predicted,
                "ratio": simulated / predicted if part == "A_std" else float("nan"),
                "se": se,
                "z": (simulated - predicted) / se,
                "share_at_limit": float(ep["share_at_limit"].mean()),
            }
        )
    assert rep is not None
    return pd.DataFrame(rows), rep


def pooled_z(z: pd.Series) -> float:
    """Independent cells: under 'no bias' the mean z times sqrt(n) is standard normal. This is
    the statistic that detects a small bias with the same sign in every cell."""
    return float(z.mean() * np.sqrt(len(z)))


def verdict(table: pd.DataFrame) -> tuple[str, dict[str, bool]]:
    """The pre-registered rule of EXP-006."""
    a, b = table[table["part"] == "A_std"], table[table["part"] == "B_mean"]
    checks = {
        "A1 std: |z| <= 3 in every cell": bool((a["z"].abs() <= Z_LIMIT).all()),
        "A2 std: pooled |z| <= 3 (no common bias)": abs(pooled_z(a["z"])) <= Z_LIMIT,
        "B1 mean with informed flow: |z| <= 3 in every cell": bool((b["z"].abs() <= Z_LIMIT).all()),
        "B2 mean with informed flow: pooled |z| <= 3 (no common bias)": abs(pooled_z(b["z"]))
        <= Z_LIMIT,
    }
    return ("CONFIRMED" if all(checks.values()) else "REJECTED"), checks


def _report_md(
    cfg: Config,
    exp: Experiment,
    info: RunInfo,
    table: pd.DataFrame,
    decision: str,
    checks: dict[str, bool],
    trials: int,
) -> str:
    a, b = table[table["part"] == "A_std"], table[table["part"] == "B_mean"]
    lines = [
        f"# {exp.id}: {exp.title}",
        "",
        LIMITATIONS,
        "Specific to this experiment: it tests the simulator against its own closed forms. It "
        "says nothing about whether the model resembles a market.",
        "",
        "## Setup",
        "",
        setup_lines(info, exp.seed, exp.episodes, trials)
        + f"- every cell has its own seed: `{exp.seed} + {SEED_STEP} * cell index`, so the cells "
        "are independent\n"
        f"- settings `{json.dumps(exp.settings)}`\n"
        f"- pre-registered as {exp.id}, approved by {exp.approved_by} on {exp.approved_on}",
        "",
        "## Results",
        "",
        "### Part A: std of P&L, noise flow only",
        "",
        "| half-spread | seed | simulated std [95% CI] | theory | ratio | z |",
        "|---|---|---|---|---|---|",
    ]
    for r in a.to_dict("records"):
        lines.append(
            f"| {r['half_spread']:g} | {int(r['seed'])} | {fmt(r['simulated'])} "
            f"[{fmt(r['ci_low'])}, {fmt(r['ci_high'])}] | {fmt(r['theory'])} "
            f"| {fmt(r['ratio'])} | {fmt(r['z'], 2)} |"
        )
    lines += [
        "",
        f"Mean ratio {fmt(float(a['ratio'].mean()))}; pooled z {fmt(pooled_z(a['z']), 2)}.",
        "",
        "### Part B: mean P&L with informed flow",
        "",
        "| informed intensity | half-spread | seed | simulated mean [95% CI] | theory | z |",
        "|---|---|---|---|---|---|",
    ]
    for r in b.to_dict("records"):
        lines.append(
            f"| {r['informed_intensity']:g} | {r['half_spread']:g} | {int(r['seed'])} "
            f"| {fmt(r['simulated'], 2)} [{fmt(r['ci_low'], 2)}, {fmt(r['ci_high'], 2)}] "
            f"| {fmt(r['theory'], 2)} | {fmt(r['z'], 2)} |"
        )
    lines += [
        "",
        f"Pooled z {fmt(pooled_z(b['z']), 2)}. Largest share of steps at the inventory limit: "
        f"{float(table['share_at_limit'].max()):.4f}.",
        "",
        "`z` = (simulated - theory) / standard error. The std's standard error comes from a "
        "bootstrap over episodes. `pooled z` = mean z times the square root of the number of "
        "cells: with independent cells it is standard normal if there is no bias.",
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
        "- Both formulas assume an inventory limit that does not bind and requoting every step.",
        "- The check covers the cells listed; a bias elsewhere on the grid is not excluded.",
        "",
    ]
    return "\n".join(lines)


def run(cfg: Config, exp: Experiment, info: RunInfo, out_dir: Path, log: bool = True) -> str:
    out_dir.mkdir(parents=True, exist_ok=False)  # an existing directory means it already ran
    table, rep = sweep(cfg, exp, info, log)
    decision, checks = verdict(table)
    table.to_csv(out_dir / TABLE_FILE, index=False, float_format="%.10g")
    a, b = table[table["part"] == "A_std"], table[table["part"] == "B_mean"]
    summary = {
        "run": info.as_dict(),
        "experiment": exp.id,
        "seed": exp.seed,
        "episodes": exp.episodes,
        "decision": decision,
        "checks": checks,
        "pooled_z_std": pooled_z(a["z"]),
        "pooled_z_mean": pooled_z(b["z"]),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    trials = count_trials(cfg.paths.experiments)
    report = _report_md(cfg, exp, info, table, decision, checks, trials)
    (out_dir / "report.md").write_text(with_representative(report, rep, out_dir))
    return decision
