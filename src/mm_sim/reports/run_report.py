"""Output of `mm-sim run`: summary.json, episodes.csv, report.md and figures.

Report order: limitations, setup, results with CIs, P&L decomposition, markouts, sanity
checks (SUSPICIOUS flags), activity, figures.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from mm_sim.analysis.markouts import markout_curve
from mm_sim.analysis.stats import mean_ci, summarize
from mm_sim.analysis.suspicious import Check, run_checks
from mm_sim.config import Config
from mm_sim.engine.reference import simulate_episode
from mm_sim.reports.common import LIMITATIONS, fmt, setup_lines
from mm_sim.reports.figures import example_episode_figure, markout_figure
from mm_sim.reports.sections import (
    decomposition_error,
    decomposition_lines,
    inventory_figure,
    markout_lines,
)
from mm_sim.runinfo import RunInfo
from mm_sim.strategies.base import Strategy

_ACTIVITY = (
    "buys",
    "sells",
    "volume",
    "max_abs_q",
    "mean_abs_q",
    "terminal_q",
    "share_at_limit",
    "mean_quoted_spread",
    "picked_off",
)


def build_summary(
    cfg: Config,
    info: RunInfo,
    strategy: str,
    params: dict[str, object],
    episodes: pd.DataFrame,
    checks: list[Check],
) -> dict[str, object]:
    a = cfg.analysis
    return {
        "run": info.as_dict(),
        "strategy": strategy,
        "parameters": params,
        "seed": a.seed,
        "episodes": len(episodes),
        "ci_level": a.ci_level,
        "pnl_mtm": summarize(episodes["pnl_mtm"], a.ci_level, a.cara_gamma),
        "pnl_liquidated": summarize(episodes["pnl_liquidated"], a.ci_level, a.cara_gamma),
        "means": {
            c: dict(
                zip(("mean", "ci_low", "ci_high"), mean_ci(episodes[c], a.ci_level), strict=True)
            )
            for c in episodes.columns
        },
        "decomposition_max_abs_error": decomposition_error(episodes),
        "markouts": markout_curve(cfg, episodes).to_dict("records"),
        "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in checks],
        "suspicious": [c.name for c in checks if not c.ok],
    }


def _report_md(
    cfg: Config,
    summary: dict[str, object],
    episodes: pd.DataFrame,
    checks: list[Check],
    trials: int,
) -> str:
    a = cfg.analysis
    info = RunInfo(**summary["run"])  # type: ignore[arg-type]
    level = f"{a.ci_level:.0%}"
    lines = [
        f"# Run report: `{summary['strategy']}` in scenario `{info.scenario}`",
        "",
        LIMITATIONS,
        "## Setup",
        "",
        setup_lines(info, a.seed, len(episodes), trials)
        + f"- strategy `{summary['strategy']}`, parameters `{json.dumps(summary['parameters'])}`\n"
        f"- {cfg.market.n_steps} steps of dt = {cfg.market.dt:g} per episode",
        "",
        "## Results (per episode)",
        "",
        f"| P&L | mean | {level} CI | std | Sharpe (per episode, not annualised) "
        "| 5% quantile | ES 5% | P(P&L<0) | CE (CARA) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for key, label in (("pnl_mtm", "mark-to-market"), ("pnl_liquidated", "liquidated")):
        s: dict[str, float] = summary[key]  # type: ignore[assignment]
        lines.append(
            f"| {label} | {fmt(s['mean'])} | [{fmt(s['ci_low'])}, {fmt(s['ci_high'])}] "
            f"| {fmt(s['std'])} | {fmt(s['sharpe_per_episode'])} | {fmt(s['q05'])} "
            f"| {fmt(s['es05'])} | {fmt(s['p_loss'])} | {fmt(s['certainty_equivalent'])} |"
        )
    lines += [
        "",
        f"CE uses risk aversion gamma = {a.cara_gamma:g}.",
        "",
        "## P&L decomposition (mean per episode)",
        "",
        *decomposition_lines(cfg, episodes),
        "",
        "## Markouts by counterparty (mean per fill)",
        "",
        "Markout at horizon h = side * (V at h steps after the fill - fill price). At h = 0 it "
        "is the edge at the fill; a curve that falls with h means the flow was informed. The "
        "market maker cannot see the counterparty type; the analysis can.",
        "",
        *markout_lines(cfg, episodes),
        "",
        "![markout curves](markouts.png)",
        "",
        "## Sanity checks",
        "",
        "A SUSPICIOUS line most likely means a bug: look for it before believing the numbers.",
        "",
    ]
    lines += [f"- {'ok' if c.ok else '**SUSPICIOUS**'}: {c.name} ({c.detail})" for c in checks]
    lines += [
        "",
        "## Activity (mean per episode)",
        "",
        f"| metric | mean | {level} CI |",
        "|---|---|---|",
    ]
    means: dict[str, dict[str, float]] = summary["means"]  # type: ignore[assignment]
    for c in _ACTIVITY:
        m = means[c]
        lines.append(f"| {c} | {fmt(m['mean'])} | [{fmt(m['ci_low'])}, {fmt(m['ci_high'])}] |")
    lines += [
        "",
        "## Figures",
        "",
        "![terminal inventory](inventory_histogram.png)",
        "",
        "![example episode](example_episode.png)",
        "",
        "Episode 0 of this run. One episode is an illustration, not evidence.",
        "",
        "## Files",
        "",
        "`summary.json` (all numbers above), `episodes.csv` (one row per episode).",
        "",
    ]
    return "\n".join(lines)


def write_run(
    out_dir: Path,
    cfg: Config,
    info: RunInfo,
    strategy_name: str,
    strategy: Strategy,
    params: dict[str, object],
    episodes: pd.DataFrame,
    trials: int,
) -> dict[str, object]:
    out_dir.mkdir(parents=True, exist_ok=False)
    checks = run_checks(cfg, strategy_name, params, episodes)
    summary = build_summary(cfg, info, strategy_name, params, episodes, checks)
    episodes.to_csv(out_dir / "episodes.csv", float_format="%.10g")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    label = f"{strategy_name} {params}, scenario {info.scenario}"
    example_episode_figure(
        simulate_episode(cfg, strategy, 0),
        f"{label}, seed {cfg.analysis.seed}, episode 0",
        out_dir / "example_episode.png",
    )
    markout_figure(markout_curve(cfg, episodes), f"Markouts: {label}", out_dir / "markouts.png")
    inventory_figure(episodes, f"Terminal inventory: {label}", out_dir / "inventory_histogram.png")
    (out_dir / "report.md").write_text(_report_md(cfg, summary, episodes, checks, trials))
    return summary
