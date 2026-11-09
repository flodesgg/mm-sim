"""Experiment kind `spread_intensity_heatmap` (EXP-002): the fixed strategy over a grid of
half-spreads and informed intensities, compared with the closed-form mean P&L and its
break-even line.

Every cell runs on the same root seed (common random numbers). The verdict rule below is the
one written in the experiment file before the run.
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
from mm_sim.config import Config, with_overrides
from mm_sim.reports.common import LIMITATIONS, fmt, setup_lines
from mm_sim.reports.figures import DPI
from mm_sim.reports.sections import Representative, with_representative
from mm_sim.runinfo import RunInfo
from mm_sim.strategies.base import build_strategy

INTENSITY_KEY = "flow.informed.intensity"
Z_LIMIT = 4.0  # |simulated mean - theory| / standard error allowed in every cell
BREAK_EVEN_TOLERANCE = 0.05  # |simulated - theoretical break-even half-spread| allowed


TABLE_FILE = "cells.csv"


def sweep(
    cfg: Config, exp: Experiment, info: RunInfo, log: bool = True
) -> tuple[pd.DataFrame, Representative]:
    """One row per (informed intensity, half-spread). One trial-log line per cell (unless
    this is a reproduction). The representative cell is the middle of both grids."""
    rows = []
    rep: Representative | None = None
    lams, hs = exp.config_grid[INTENSITY_KEY], exp.grid["half_spread"]
    middle = (lams[len(lams) // 2], hs[len(hs) // 2])
    for lam in exp.config_grid[INTENSITY_KEY]:
        cell_cfg = with_overrides(cfg, {INTENSITY_KEY: lam})
        for h in exp.grid["half_spread"]:
            strategy, params = build_strategy(cell_cfg, exp.strategy, {"half_spread": h})
            ep = run_monte_carlo(cell_cfg, strategy)
            if log:
                append_trial(
                    cfg.paths.experiments,
                    info,
                    exp.id,
                    exp.strategy,
                    {**params, INTENSITY_KEY: lam},
                    exp.seed,
                    exp.episodes,
                )
            if (lam, h) == middle:
                label = f"informed intensity {lam:g}, half-spread {h:g}"
                rep = Representative(cell_cfg, exp.strategy, params, ep, label)
            pnl = ep["pnl_mtm"]
            mean, lo, hi = mean_ci(pnl, cfg.analysis.ci_level)
            se = float(pnl.std(ddof=1)) / np.sqrt(len(pnl))
            theory_mean = theory.fixed_mean_pnl_with_informed(cell_cfg, h)
            rows.append(
                {
                    "informed_intensity": lam,
                    "half_spread": h,
                    "mean_pnl": mean,
                    "ci_low": lo,
                    "ci_high": hi,
                    "se": se,
                    "theory_mean": theory_mean,
                    "z_mean": (mean - theory_mean) / se,
                    "spread_capture": float(ep["spread_capture"].mean()),
                    "adverse_selection": float(ep["adverse_selection"].mean()),
                    "inventory_pnl": float(ep["inventory_pnl"].mean()),
                    "fills_noise": float(ep["fills_noise"].mean()),
                    "fills_informed": float(ep["fills_informed"].mean()),
                    "fees": float(ep["fees"].mean()),
                    "share_at_limit": float(ep["share_at_limit"].mean()),
                }
            )
    assert rep is not None
    return pd.DataFrame(rows), rep


def simulated_break_even(h: np.ndarray, mean: np.ndarray) -> float:
    """First half-spread at which the simulated mean P&L crosses from negative to
    non-negative, by linear interpolation between grid points. If the mean is already
    non-negative at the smallest half-spread, that half-spread (an upper bound). NaN if the
    mean never becomes non-negative."""
    if mean[0] >= 0:
        return float(h[0])
    for i in range(1, len(h)):
        if mean[i] >= 0:
            return float(h[i - 1] + (h[i] - h[i - 1]) * (-mean[i - 1]) / (mean[i] - mean[i - 1]))
    return float("nan")


def break_even_table(cfg: Config, table: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for lam, part in table.groupby("informed_intensity"):
        part = part.sort_values("half_spread")
        cell_cfg = with_overrides(cfg, {INTENSITY_KEY: float(lam)})  # type: ignore[arg-type]
        rows.append(
            {
                "informed_intensity": float(lam),  # type: ignore[arg-type]
                "break_even_simulated": simulated_break_even(
                    part["half_spread"].to_numpy(), part["mean_pnl"].to_numpy()
                ),
                "break_even_theory": theory.break_even_half_spread(cell_cfg),
            }
        )
    return pd.DataFrame(rows)


def verdict(table: pd.DataFrame, be: pd.DataFrame) -> tuple[str, dict[str, bool], list[str]]:
    """The pre-registered rule of EXP-002, plus SUSPICIOUS flags (a likely bug)."""
    informed = be[be["informed_intensity"] > 0]
    inside = be[be["break_even_theory"] > table["half_spread"].min()]
    diff = (informed["break_even_simulated"] - informed["break_even_theory"]).abs()
    checks = {
        "C1 mean matches theory (|z| <= 4.0 in every cell)": bool(
            (table["z_mean"].abs() <= Z_LIMIT).all()
        ),
        "C2 simulated break-even within 0.05 of theory at every informed intensity > 0": bool(
            (diff <= BREAK_EVEN_TOLERANCE).all()
        ),
        "C3 simulated break-even rises with the informed intensity (where the theoretical "
        "break-even is inside the half-spread grid)": bool(
            (np.diff(inside.sort_values("informed_intensity")["break_even_simulated"]) > 0).all()
        ),
    }
    flags = []
    theory_be = dict(zip(be["informed_intensity"], be["break_even_theory"], strict=True))
    for r in table.to_dict("records"):
        below = r["half_spread"] < theory_be[r["informed_intensity"]] - BREAK_EVEN_TOLERANCE
        if below and r["ci_low"] > 0:
            flags.append(
                f"SUSPICIOUS: positive mean P&L (CI above 0) below the break-even line at "
                f"lambda_I={r['informed_intensity']:g}, h={r['half_spread']:g}"
            )
    c1, c2, c3 = checks.values()
    if c1 and c2 and c3:
        return "CONFIRMED", checks, flags
    if not c1 or not c2:
        return "REJECTED", checks, flags
    return "INCONCLUSIVE", checks, flags


def _edges(x: np.ndarray) -> np.ndarray:
    mid = (x[:-1] + x[1:]) / 2
    return np.concatenate([[x[0] - (mid[0] - x[0])], mid, [x[-1] + (x[-1] - mid[-1])]])


def _figure(cfg: Config, table: pd.DataFrame, be: pd.DataFrame, path: Path) -> None:
    pivot = table.pivot(index="informed_intensity", columns="half_spread", values="mean_pnl")
    h, lam = pivot.columns.to_numpy(dtype=float), pivot.index.to_numpy(dtype=float)
    limit = float(np.abs(pivot.to_numpy()).max())
    fig, ax = plt.subplots(figsize=(8, 4.8))
    mesh = ax.pcolormesh(
        _edges(h), _edges(lam), pivot.to_numpy(), cmap="RdBu", vmin=-limit, vmax=limit
    )
    fig.colorbar(mesh, ax=ax, label="mean episode P&L")
    lam_fine = np.linspace(lam.min(), lam.max(), 60)
    be_fine = [
        theory.break_even_half_spread(with_overrides(cfg, {INTENSITY_KEY: float(x)}))
        for x in lam_fine
    ]
    ax.plot(be_fine, lam_fine, color="black", lw=1.5, label="break-even, theory")
    ax.plot(
        be["break_even_simulated"],
        be["informed_intensity"],
        "o",
        color="gold",
        mec="black",
        ms=6,
        label="break-even, simulated",
    )
    ax.set_xlabel("half-spread h")
    ax.set_ylabel("informed intensity lambda_I (arrivals per unit time)")
    ax.set_title("Mean P&L of the fixed strategy: half-spread x informed intensity", fontsize=10)
    ax.legend(fontsize=8, loc="upper right")
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)


def _report_md(
    cfg: Config,
    exp: Experiment,
    info: RunInfo,
    table: pd.DataFrame,
    be: pd.DataFrame,
    decision: str,
    checks: dict[str, bool],
    flags: list[str],
    trials: int,
) -> str:
    inf = cfg.flow.informed
    hs = sorted(table["half_spread"].unique())
    lines = [
        f"# {exp.id}: {exp.title}",
        "",
        LIMITATIONS,
        f"Specific to this experiment: informed traders know the value {inf.horizon_steps} steps "
        f"ahead and trade whenever the quote is wrong by more than {inf.threshold:g}. Both "
        "numbers are invented. The break-even spreads below scale with them.",
        "",
        "## Setup",
        "",
        setup_lines(info, exp.seed, exp.episodes, trials)
        + f"- strategy `{exp.strategy}`, half-spreads `{json.dumps(exp.grid)}`, informed "
        f"intensities `{json.dumps(exp.config_grid)}`; every cell uses the same seed\n"
        f"- pre-registered as {exp.id}, approved by {exp.approved_by} on {exp.approved_on}",
        "",
        "## Results: mean episode P&L (rows: informed intensity, columns: half-spread)",
        "",
        "| lambda_I | " + " | ".join(f"h={x:g}" for x in hs) + " |",
        "|---|" + "---|" * len(hs),
    ]
    pivot = table.pivot(index="informed_intensity", columns="half_spread", values="mean_pnl")
    for lam, row in pivot.iterrows():
        lines.append(f"| {lam:g} | " + " | ".join(fmt(float(row[x]), 1) for x in hs) + " |")
    worst = max(table.to_dict("records"), key=lambda r: abs(float(r["z_mean"])))
    lines += [
        "",
        f"Confidence intervals, theory values and z-scores for all {len(table)} cells are in "
        f"`cells.csv`. Largest |z| against theory: {abs(float(worst['z_mean'])):.2f} at "
        f"lambda_I={float(worst['informed_intensity']):g}, h={float(worst['half_spread']):g}. "
        "Largest share of steps at the inventory limit: "
        f"{float(table['share_at_limit'].max()):.4f}.",
        "",
        "## Break-even half-spread",
        "",
        "| lambda_I | arrival prob. per step | simulated | theory | difference |",
        "|---|---|---|---|---|",
    ]
    for r in be.to_dict("records"):
        lam = float(r["informed_intensity"])
        sim, th = float(r["break_even_simulated"]), float(r["break_even_theory"])
        lines.append(
            f"| {lam:g} | {lam * cfg.market.dt:.2f} | {fmt(sim)} | {fmt(th)} | {fmt(sim - th)} |"
        )
    lines += [
        "",
        "`simulated` is the first zero of the mean P&L, linearly interpolated between grid "
        "points; where the mean is already positive at the smallest half-spread it is that "
        "half-spread (an upper bound).",
        "",
        "![heatmap of mean P&L with the break-even line](heatmap.png)",
        "",
        "## P&L decomposition along the grid (mean per episode)",
        "",
        "| lambda_I | h | spread capture | short-term move (adverse selection) | inventory "
        "| informed fills | noise fills |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in table.to_dict("records"):
        if r["half_spread"] in (hs[0], hs[len(hs) // 2], hs[-1]):
            lines.append(
                f"| {r['informed_intensity']:g} | {r['half_spread']:g} "
                f"| {fmt(r['spread_capture'], 1)} | {fmt(r['adverse_selection'], 1)} "
                f"| {fmt(r['inventory_pnl'], 1)} | {fmt(r['fills_informed'], 1)} "
                f"| {fmt(r['fills_noise'], 1)} |"
            )
    lines += ["", "## Verdict against the pre-registered hypothesis", ""]
    lines += [f"- {'PASS' if ok else 'FAIL'}: {name}" for name, ok in checks.items()]
    lines += [f"- {flag}" for flag in flags] or ["- no SUSPICIOUS flags"]
    lines += [
        "",
        f"**{decision}**",
        "",
        "## What depends on the model's assumptions",
        "",
        "- The size of the informed traders' edge is set by their horizon: they know a move of "
        "std sigma*sqrt(horizon*dt). A shorter horizon means a smaller edge and a narrower "
        "break-even spread.",
        "- Informed traders here always trade when it pays and never hide; real informed flow "
        "is strategic (Kyle 1985) and partly indistinguishable from noise.",
        "- The market maker never reacts: a fixed spread does not widen after being hit. "
        "Glosten-Milgrom quotes (the two-point world) do.",
        "- Noise traders keep arriving at the same rate whatever the spread history.",
        "",
    ]
    return "\n".join(lines)


def run(cfg: Config, exp: Experiment, info: RunInfo, out_dir: Path, log: bool = True) -> str:
    out_dir.mkdir(parents=True, exist_ok=False)  # an existing directory means it already ran
    table, rep = sweep(cfg, exp, info, log)
    be = break_even_table(cfg, table)
    decision, checks, flags = verdict(table, be)
    table.to_csv(out_dir / TABLE_FILE, index=False, float_format="%.10g")
    be.to_csv(out_dir / "break_even.csv", index=False, float_format="%.10g")
    summary = {
        "run": info.as_dict(),
        "experiment": exp.id,
        "seed": exp.seed,
        "episodes": exp.episodes,
        "decision": decision,
        "checks": checks,
        "suspicious": flags,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    _figure(cfg, table, be, out_dir / "heatmap.png")
    trials = count_trials(cfg.paths.experiments)
    report = _report_md(cfg, exp, info, table, be, decision, checks, flags, trials)
    (out_dir / "report.md").write_text(with_representative(report, rep, out_dir))
    return decision
