"""Experiment kind `latency_sweep` (EXP-004): the fixed strategy in a jump scenario, over a
grid of `requote_every`. Mean P&L and the number of pick-offs are compared with the closed
forms of docs/model_notes.md, section 13. Every grid point runs on the same root seed.
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
from mm_sim.analysis.markouts import ratio_ci
from mm_sim.analysis.montecarlo import run_monte_carlo
from mm_sim.analysis.stats import mean_ci
from mm_sim.analysis.trials import append_trial, count_trials
from mm_sim.config import Config, with_overrides
from mm_sim.reports.common import LIMITATIONS, fmt, setup_lines
from mm_sim.reports.figures import DPI
from mm_sim.reports.sections import Representative, with_representative
from mm_sim.runinfo import RunInfo
from mm_sim.strategies.base import build_strategy

REQUOTE_KEY = "engine.requote_every"
Z_LIMIT = 4.0


def _se(x: pd.Series) -> float:
    return float(x.std(ddof=1)) / float(np.sqrt(len(x)))


TABLE_FILE = "latency.csv"


def sweep(
    cfg: Config, exp: Experiment, info: RunInfo, log: bool = True
) -> tuple[pd.DataFrame, Representative]:
    """One row per requote interval. The representative grid point is the middle one."""
    level = cfg.analysis.ci_level
    rows = []
    rep: Representative | None = None
    grid = exp.config_grid[REQUOTE_KEY]
    middle = int(grid[len(grid) // 2])
    for raw in exp.config_grid[REQUOTE_KEY]:
        every = int(raw)
        c = with_overrides(cfg, {REQUOTE_KEY: every})
        strategy, params = build_strategy(c, exp.strategy)
        h = float(params["half_spread"])  # type: ignore[arg-type]
        ep = run_monte_carlo(c, strategy)
        if log:
            append_trial(
                cfg.paths.experiments,
                info,
                exp.id,
                exp.strategy,
                {**params, REQUOTE_KEY: every},
                exp.seed,
                exp.episodes,
            )
        if every == middle:
            rep = Representative(c, exp.strategy, params, ep, f"requote every {every} steps")
        pnl, picks = ep["pnl_mtm"], ep["picked_off"]
        mean, lo, hi = mean_ci(pnl, level)
        p_mean, p_lo, p_hi = mean_ci(picks, level)
        theory_mean = theory.latency_mean_pnl(c, h)
        theory_picks = theory.latency_pick_offs(c, h)
        edge, edge_lo, edge_hi = ratio_ci(ep["picked_off_edge"], picks, level)
        rows.append(
            {
                "requote_every": every,
                "mean_pnl": mean,
                "ci_low": lo,
                "ci_high": hi,
                "theory_mean": theory_mean,
                "z_mean": (mean - theory_mean) / _se(pnl),
                "std_pnl": float(pnl.std(ddof=1)),
                "pick_offs": p_mean,
                "pick_offs_ci_low": p_lo,
                "pick_offs_ci_high": p_hi,
                "theory_pick_offs": theory_picks,
                "z_pick_offs": (p_mean - theory_picks) / _se(picks) if _se(picks) > 0 else 0.0,
                "edge_per_pick_off": edge,
                "edge_ci_low": edge_lo,
                "edge_ci_high": edge_hi,
                "fills": float(ep["volume"].mean()),
                "spread_capture": float(ep["spread_capture"].mean()),
                "adverse_selection": float(ep["adverse_selection"].mean()),
                "inventory_pnl": float(ep["inventory_pnl"].mean()),
                "fees": float(ep["fees"].mean()),
                "share_at_limit": float(ep["share_at_limit"].mean()),
            }
        )
    assert rep is not None
    return pd.DataFrame(rows), rep


def verdict(table: pd.DataFrame) -> tuple[str, dict[str, bool]]:
    """The pre-registered rule of EXP-004."""
    t = table.sort_values("requote_every")
    stale = t[t["requote_every"] > 1]
    checks = {
        "C1 mean P&L matches theory (|z| <= 4.0 at every grid point)": bool(
            (t["z_mean"].abs() <= Z_LIMIT).all()
        ),
        "C2 mean P&L falls strictly as requoting gets slower": bool(
            (np.diff(t["mean_pnl"].to_numpy()) < 0).all()
        ),
        "C3 pick-offs per episode match theory (|z| <= 4.0 for requote_every > 1)": bool(
            (stale["z_pick_offs"].abs() <= Z_LIMIT).all()
        ),
        "C4 pick-off fills have a negative edge (CI below 0 for requote_every > 1)": bool(
            (stale["edge_ci_high"] < 0).all()
        ),
    }
    c1, c2, c3, c4 = checks.values()
    if c1 and c2 and c3 and c4:
        return "CONFIRMED", checks
    if not c1 or not c3:
        return "REJECTED", checks
    return "INCONCLUSIVE", checks


def _figure(table: pd.DataFrame, path: Path) -> None:
    fig, (ax, ax_p) = plt.subplots(1, 2, figsize=(10, 4))
    x = table["requote_every"]
    ax.plot(x, table["theory_mean"], color="black", lw=1, label="theory")
    ax.errorbar(
        x,
        table["mean_pnl"],
        yerr=[table["mean_pnl"] - table["ci_low"], table["ci_high"] - table["mean_pnl"]],
        fmt="o",
        ms=4,
        capsize=3,
        color="tab:blue",
        label="simulation (95% CI)",
    )
    ax.set_xscale("log")
    ax.set_xlabel("requote every (steps)")
    ax.set_ylabel("mean episode P&L")
    ax.set_title("Mean P&L against requote latency", fontsize=10)
    ax.legend(fontsize=8)
    ax_p.plot(x, table["theory_pick_offs"], color="black", lw=1, label="theory")
    ax_p.errorbar(
        x,
        table["pick_offs"],
        yerr=[
            table["pick_offs"] - table["pick_offs_ci_low"],
            table["pick_offs_ci_high"] - table["pick_offs"],
        ],
        fmt="o",
        ms=4,
        capsize=3,
        color="tab:red",
        label="simulation (95% CI)",
    )
    ax_p.set_xscale("log")
    ax_p.set_xlabel("requote every (steps)")
    ax_p.set_ylabel("pick-offs per episode")
    ax_p.set_title("Stale quotes picked off", fontsize=10)
    ax_p.legend(fontsize=8)
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
    j = cfg.market.jump
    lines = [
        f"# {exp.id}: {exp.title}",
        "",
        LIMITATIONS,
        f"Specific to this experiment: jumps of size {j.size:g} ({j.size_dist}) arrive at rate "
        f"{j.intensity:g} per unit time, invented numbers. Latency is only the requote interval: "
        "everyone else reacts instantly, and the 'fast' traders here are the ordinary noise "
        "traders, whose arrival rate rises steeply for a quote that is through the mid. There "
        "are no informed traders and no race between market makers.",
        "",
        "## Setup",
        "",
        setup_lines(info, exp.seed, exp.episodes, trials)
        + f"- strategy `{exp.strategy}` (half-spread from the config), "
        f"`{json.dumps(exp.config_grid)}`; every grid point uses the same seed\n"
        f"- pre-registered as {exp.id}, approved by {exp.approved_by} on {exp.approved_on}",
        "",
        "## Results (per episode)",
        "",
        "| requote every | mean P&L [95% CI] | theory | z | std | pick-offs [95% CI] | theory | z "
        "| edge per pick-off [95% CI] | fills | at limit |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in table.to_dict("records"):
        if r["requote_every"] > 1:
            edge = (
                f"{fmt(r['edge_per_pick_off'])} [{fmt(r['edge_ci_low'])}, {fmt(r['edge_ci_high'])}]"
            )
        else:
            edge = "n/a"
        lines.append(
            f"| {int(r['requote_every'])} "
            f"| {fmt(r['mean_pnl'], 2)} [{fmt(r['ci_low'], 2)}, {fmt(r['ci_high'], 2)}] "
            f"| {fmt(r['theory_mean'], 2)} | {fmt(r['z_mean'], 2)} | {fmt(r['std_pnl'], 2)} "
            f"| {fmt(r['pick_offs'], 2)} [{fmt(r['pick_offs_ci_low'], 2)}, "
            f"{fmt(r['pick_offs_ci_high'], 2)}] "
            f"| {fmt(r['theory_pick_offs'], 2)} | {fmt(r['z_pick_offs'], 2)} | {edge} "
            f"| {fmt(r['fills'], 1)} | {fmt(r['share_at_limit'], 4)} |"
        )
    lines += [
        "",
        "A pick-off is a fill on a quote posted at an earlier step that is on the wrong side of "
        "the current value (the market maker buys above it or sells below it). `edge per "
        "pick-off` is the average edge of those fills at the moment of the fill.",
        "",
        "![mean P&L and pick-offs against requote latency](latency.png)",
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
        "- Who picks off a stale quote: here the noise flow, through an intensity that grows "
        "exponentially as the quote goes through the mid. In a real market it is a race "
        "between fast traders, and the stale quote is hit almost surely.",
        "- The cost of latency scales with how far the value moves between requotes: volatility, "
        "jump size and jump rate, all invented here.",
        "- A real market maker cancels on a signal instead of waiting for a fixed interval.",
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
    _figure(table, out_dir / "latency.png")
    trials = count_trials(cfg.paths.experiments)
    report = _report_md(cfg, exp, info, table, decision, checks, trials)
    (out_dir / "report.md").write_text(with_representative(report, rep, out_dir))
    return decision
