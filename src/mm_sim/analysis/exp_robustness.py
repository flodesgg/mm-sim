"""Experiment kind `robustness` (EXP-005): do the key conclusions of EXP-001..004 keep their
sign when the model changes?

Each conclusion is a signed quantity with a confidence interval, re-estimated under the base
configuration and under each variant listed in the experiment file (for example higher
volatility, a different fill-decay k, jumps). A conclusion whose CI lies entirely on the
other side of zero in some variant has flipped sign and is labelled `fragile`.

  K1a  fixed at the best half-spread h* earns more than at h*/f   (too narrow is worse)
  K1b  fixed at h* earns more than at h*·f                        (too wide is worse)
  K2   with informed flow a narrow fixed spread loses money       (mean P&L < 0)
  K3a  Avellaneda-Stoikov has a lower P&L std than fixed quotes at the same spread
  K3b  skew has a lower P&L std than fixed quotes at the same spread
  K4   requoting slowly earns less than requoting every step

h* is the theoretical optimum for the variant's own parameters. K3 is measured on liquidated
P&L. All runs of one variant share the root seed (common random numbers).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from mm_sim.analysis import theory
from mm_sim.analysis.experiment import Experiment
from mm_sim.analysis.montecarlo import run_monte_carlo
from mm_sim.analysis.stats import bootstrap_ci, mean_ci, paired_comparison
from mm_sim.analysis.trials import append_trial, count_trials
from mm_sim.config import Config, with_overrides
from mm_sim.reports.common import LIMITATIONS, fmt, setup_lines
from mm_sim.reports.sections import Representative, with_representative
from mm_sim.runinfo import RunInfo
from mm_sim.strategies.base import build_strategy

TABLE_FILE = "robustness.csv"
BOOTSTRAP_SEED = 20261109

CONCLUSIONS = {
    "K1a": ("fixed at h* earns more than at h*/f (P&L difference)", +1),
    "K1b": ("fixed at h* earns more than at h*·f (P&L difference)", +1),
    "K2": ("narrow fixed spread against informed flow loses (mean P&L)", -1),
    "K3a": ("Avellaneda-Stoikov std below fixed at the same spread (std ratio - 1)", -1),
    "K3b": ("skew std below fixed at the same spread (std ratio - 1)", -1),
    "K4": ("slow requoting earns less than requoting every step (P&L difference)", -1),
}


def _status(lo: float, hi: float, expected: int) -> str:
    if (expected > 0 and lo > 0) or (expected < 0 and hi < 0):
        return "holds"
    if (expected > 0 and hi < 0) or (expected < 0 and lo > 0):
        return "flipped"
    return "unresolved"


class _Runner:
    """Runs one strategy under one variant and logs the trial."""

    def __init__(self, exp: Experiment, info: RunInfo, variant: str, log: bool) -> None:
        self.exp, self.info, self.variant, self.log = exp, info, variant, log

    def run(self, cfg: Config, strategy: str, params: dict[str, object]) -> pd.DataFrame:
        built, full = build_strategy(cfg, strategy, params)
        if self.log:
            append_trial(
                cfg.paths.experiments,
                self.info,
                self.exp.id,
                strategy,
                {**full, "variant": self.variant},
                self.exp.seed,
                self.exp.episodes,
            )
        return run_monte_carlo(cfg, built)


def _std_ratio_minus_one(cfg: Config, v: np.ndarray, b: np.ndarray) -> tuple[float, float, float]:
    lo, hi = bootstrap_ci(
        lambda i: float(v[i].std(ddof=1) / b[i].std(ddof=1)),
        len(v),
        cfg.analysis.ci_level,
        BOOTSTRAP_SEED,
        cfg.analysis.bootstrap_samples,
    )
    return float(v.std(ddof=1) / b.std(ddof=1)) - 1, lo - 1, hi - 1


def evaluate_variant(
    cfg: Config, exp: Experiment, info: RunInfo, variant: str, overrides: dict[str, Any], log: bool
) -> tuple[list[dict[str, object]], Representative]:
    s = exp.settings
    level = cfg.analysis.ci_level
    base = with_overrides(cfg, overrides)
    runner = _Runner(exp, info, variant, log)
    results: dict[str, tuple[float, float, float]] = {}

    # K1: an interior optimum of the half-spread (noise flow only)
    h_star = theory.optimal_fixed_half_spread(base)
    factor = float(s["spread_factor"])
    best = runner.run(base, "fixed", {"half_spread": h_star})["pnl_mtm"]
    for key, h in (("K1a", h_star / factor), ("K1b", h_star * factor)):
        other = runner.run(base, "fixed", {"half_spread": h})["pnl_mtm"]
        d = paired_comparison(best, other, level)
        results[key] = (d["mean_diff"], d["ci_low"], d["ci_high"])

    # K2: a narrow spread loses to informed flow
    informed = with_overrides(base, s["informed"])
    pnl = runner.run(informed, "fixed", {"half_spread": float(s["narrow_half_spread"])})
    results["K2"] = mean_ci(pnl["pnl_mtm"], level)

    # K3: inventory management lowers the std of liquidated P&L
    inventory = with_overrides(base, s["inventory"])
    rep: Representative | None = None
    variants: tuple[tuple[str, str, dict[str, object]], ...] = (
        ("K3a", "avellaneda_stoikov", {"gamma": float(s["as_gamma"])}),
        ("K3b", "skew", {"half_spread": h_star, "kappa": float(s["skew_kappa"])}),
    )
    for key, strategy, params in variants:
        ep_v = runner.run(inventory, strategy, params)
        half = float(ep_v["mean_quoted_spread"].mean()) / 2
        ep_b = runner.run(inventory, "fixed", {"half_spread": half})
        results[key] = _std_ratio_minus_one(
            inventory, ep_v["pnl_liquidated"].to_numpy(), ep_b["pnl_liquidated"].to_numpy()
        )
        if key == "K3a":
            label = f"{strategy} gamma={float(s['as_gamma']):g}, variant {variant}"
            rep = Representative(inventory, strategy, dict(params), ep_v, label)

    # K4: slow requoting earns less
    latency = with_overrides(base, s["latency"])
    slow = with_overrides(latency, {"engine.requote_every": int(s["slow_requote"])})
    fast = with_overrides(latency, {"engine.requote_every": 1})
    d = paired_comparison(
        runner.run(slow, "fixed", {"half_spread": h_star})["pnl_mtm"],
        runner.run(fast, "fixed", {"half_spread": h_star})["pnl_mtm"],
        level,
    )
    results["K4"] = (d["mean_diff"], d["ci_low"], d["ci_high"])

    rows: list[dict[str, object]] = []
    for key, (estimate, lo, hi) in results.items():
        description, expected = CONCLUSIONS[key]
        rows.append(
            {
                "conclusion": key,
                "description": description,
                "variant": variant,
                "estimate": estimate,
                "ci_low": lo,
                "ci_high": hi,
                "expected_sign": expected,
                "status": _status(lo, hi, expected),
                "optimal_half_spread": h_star,
            }
        )
    assert rep is not None
    return rows, rep


def sweep(
    cfg: Config, exp: Experiment, info: RunInfo, log: bool = True
) -> tuple[pd.DataFrame, Representative]:
    rows: list[dict[str, object]] = []
    rep: Representative | None = None
    for variant, overrides in exp.settings["variants"].items():
        variant_rows, variant_rep = evaluate_variant(cfg, exp, info, variant, overrides, log)
        rows += variant_rows
        rep = rep or variant_rep  # the first variant listed is the base
    assert rep is not None
    return pd.DataFrame(rows), rep


def labels(table: pd.DataFrame) -> dict[str, str]:
    """robust: holds in every variant; fragile: the sign flips somewhere; else unresolved."""
    out = {}
    for key, part in table.groupby("conclusion"):
        statuses = set(part["status"])
        if "flipped" in statuses:
            out[str(key)] = "fragile"
        elif statuses == {"holds"}:
            out[str(key)] = "robust"
        else:
            out[str(key)] = "unresolved"
    return out


def verdict(table: pd.DataFrame) -> tuple[str, dict[str, bool]]:
    """The pre-registered rule of EXP-005."""
    result = labels(table)
    checks = {
        f"{key} is robust ({CONCLUSIONS[key][0]}): {result[key]}": result[key] == "robust"
        for key in CONCLUSIONS
    }
    if all(v == "robust" for v in result.values()):
        return "CONFIRMED", checks
    if any(v == "fragile" for v in result.values()):
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
    variants = list(exp.settings["variants"])
    other_settings = {k: v for k, v in exp.settings.items() if k != "variants"}
    result = labels(table)
    lines = [
        f"# {exp.id}: {exp.title}",
        "",
        LIMITATIONS,
        "Specific to this experiment: the variants change one model assumption at a time, with "
        "invented values. Keeping its sign under these variants does not make a conclusion true "
        "of real markets; flipping its sign shows that it depends on the assumption changed.",
        "",
        "## Setup",
        "",
        setup_lines(info, exp.seed, exp.episodes, trials)
        + f"- variants: `{json.dumps(exp.settings['variants'])}`\n"
        f"- other settings: `{json.dumps(other_settings)}`\n"
        f"- pre-registered as {exp.id}, approved by {exp.approved_by} on {exp.approved_on}",
        "",
        "## Results: estimate [95% CI] of each conclusion under each variant",
        "",
        "| conclusion | expected sign | " + " | ".join(variants) + " | label |",
        "|---|---|" + "---|" * (len(variants) + 1),
    ]
    for key, (description, expected) in CONCLUSIONS.items():
        cells = []
        for variant in variants:
            r = table[(table["conclusion"] == key) & (table["variant"] == variant)].iloc[0]
            mark = "" if r["status"] == "holds" else f" **{r['status']}**"
            cells.append(
                f"{fmt(float(r['estimate']))} "
                f"[{fmt(float(r['ci_low']))}, {fmt(float(r['ci_high']))}]{mark}"
            )
        label = result[key] if result[key] == "robust" else f"**{result[key]}**"
        sign = "positive" if expected > 0 else "negative"
        lines.append(f"| {key}: {description} | {sign} | " + " | ".join(cells) + f" | {label} |")
    h_star = table.groupby("variant")["optimal_half_spread"].first()
    lines += [
        "",
        "Best half-spread h* used in each variant: "
        + ", ".join(f"{v} {fmt(float(h_star[v]))}" for v in variants)
        + ".",
        "",
        "`robust`: the CI is on the expected side of zero in every variant. `fragile`: in some "
        "variant the CI is entirely on the other side. `unresolved`: some CI includes zero.",
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
        "- Every variant keeps the exponential fill intensity, one-lot orders and a single "
        "market maker. Those assumptions are not tested here.",
        "- The variants are single changes; combinations are not explored.",
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
        "labels": labels(table),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    trials = count_trials(cfg.paths.experiments)
    report = _report_md(cfg, exp, info, table, decision, checks, trials)
    (out_dir / "report.md").write_text(with_representative(report, rep, out_dir))
    return decision
