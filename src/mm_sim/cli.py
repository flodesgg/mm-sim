"""Command-line entry point: `mm-sim <command>`.

Commands
  check-config [--scenario X]   validate config.yaml (+ scenario) and print it with its hash
  run --scenario X --strategy S [--episodes N] [--seed K]
                                Monte Carlo run -> reports/runs/<run_id>/
  experiment EXP-NNN            run an approved, pre-registered experiment (once)
  reproduce EXP-NNN             rebuild a finished experiment's report and figures from
                                scratch and verify the numbers against the stored ones
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pandas as pd
import yaml
from pydantic import ValidationError

from mm_sim import __version__
from mm_sim.analysis import (
    exp_fixed_spread,
    exp_frontier,
    exp_heatmap,
    exp_latency,
    exp_robustness,
)
from mm_sim.analysis.experiment import (
    Experiment,
    ExperimentError,
    check_runnable,
    find_experiment,
    load_experiment,
)
from mm_sim.analysis.montecarlo import run_monte_carlo, with_run_settings
from mm_sim.analysis.trials import append_trial, count_trials
from mm_sim.config import DEFAULT_CONFIG_PATH, Config, available_scenarios, load_config
from mm_sim.logging_setup import setup_logging
from mm_sim.reports.run_report import write_run
from mm_sim.runinfo import RunInfo, new_run_info
from mm_sim.strategies import REGISTRY, build_strategy

# experiment kind -> module with run(cfg, experiment, run info, output dir, log) and TABLE_FILE
EXPERIMENT_KINDS: dict[str, ModuleType] = {
    "fixed_spread_sweep": exp_fixed_spread,
    "spread_intensity_heatmap": exp_heatmap,
    "inventory_frontier": exp_frontier,
    "latency_sweep": exp_latency,
    "robustness": exp_robustness,
}


def _start(args: argparse.Namespace, scenario: str | None = None) -> tuple[Config, RunInfo]:
    cfg, chash = load_config(args.config, scenario or getattr(args, "scenario", None))
    info = new_run_info(chash, cfg.scenario.name)
    log = setup_logging(cfg.logging, cfg.paths.logs, info.run_id)
    log.info("run start command=%s %s", args.command, json.dumps(info.as_dict()))
    return cfg, info


def cmd_check_config(args: argparse.Namespace) -> int:
    cfg, info = _start(args)
    print(yaml.safe_dump(cfg.model_dump(mode="json"), sort_keys=False), end="")
    print("---")
    print(f"config OK   scenario={cfg.scenario.name}   horizon T={cfg.market.horizon:g}")
    print(f"config_hash {info.config_hash}")
    print(f"run_id      {info.run_id}")
    print(f"git_commit  {info.git_commit}{' (dirty)' if info.git_dirty else ''}")
    print(f"scenarios   {', '.join(available_scenarios(args.config))}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    cfg, info = _start(args)
    cfg = with_run_settings(cfg, args.seed, args.episodes)
    strategy, params = build_strategy(cfg, args.strategy)
    episodes = run_monte_carlo(cfg, strategy)
    a = cfg.analysis
    append_trial(cfg.paths.experiments, info, "", args.strategy, params, a.seed, a.episodes)
    out_dir = cfg.paths.reports / "runs" / info.run_id
    trials = count_trials(cfg.paths.experiments)
    summary = write_run(out_dir, cfg, info, args.strategy, strategy, params, episodes, trials)
    pnl: dict[str, float] = summary["pnl_mtm"]  # type: ignore[assignment]
    print(f"strategy {args.strategy} {params}  scenario {info.scenario}  seed {a.seed}")
    print(
        f"mean P&L (MTM) {pnl['mean']:.3f}  {a.ci_level:.0%} CI "
        f"[{pnl['ci_low']:.3f}, {pnl['ci_high']:.3f}]  std {pnl['std']:.3f}  n={a.episodes}"
    )
    print(f"report: {out_dir / 'report.md'}")
    return 0


def _experiment_setup(
    args: argparse.Namespace,
) -> tuple[Config, RunInfo, Experiment, ModuleType, Path]:
    base, _ = load_config(args.config)
    exp = load_experiment(find_experiment(base.paths.experiments, args.id))
    cfg, info = _start(args, scenario=exp.scenario)
    if exp.kind not in EXPERIMENT_KINDS:
        raise ExperimentError(f"unknown experiment kind {exp.kind!r}")
    cfg = with_run_settings(cfg, exp.seed, exp.episodes)
    return cfg, info, exp, EXPERIMENT_KINDS[exp.kind], cfg.paths.reports / "experiments" / exp.id


def cmd_experiment(args: argparse.Namespace) -> int:
    cfg, info, exp, kind, out_dir = _experiment_setup(args)
    check_runnable(exp, info.config_hash)
    if out_dir.exists():
        raise ExperimentError(f"{out_dir} exists: {exp.id} has already run")
    decision = kind.run(cfg, exp, info, out_dir)
    print(f"{exp.id}: {decision}")
    print(f"report: {out_dir / 'report.md'}")
    print("Now record the result and the decision in the experiment file and set status: done.")
    return 0


def cmd_reproduce(args: argparse.Namespace) -> int:
    """Rebuild a finished experiment's report and figures from scratch and check that the
    numbers are the stored ones. Same seed, same grid: a reproduction, not a new trial, so
    nothing is added to the trial log."""
    cfg, info, exp, kind, out_dir = _experiment_setup(args)
    if exp.status != "done" or not out_dir.is_dir():
        raise ExperimentError(f"{exp.id} has not run yet; `reproduce` is for finished experiments")
    stored = pd.read_csv(out_dir / kind.TABLE_FILE)
    old_summary = json.loads((out_dir / "summary.json").read_text())
    scratch = out_dir.with_name(f"{exp.id}.reproduce")
    if scratch.exists():
        shutil.rmtree(scratch)
    decision = kind.run(cfg, exp, info, scratch, log=False)
    fresh = pd.read_csv(scratch / kind.TABLE_FILE)
    shared = [c for c in stored.columns if c in fresh.columns]
    numeric = [c for c in shared if pd.api.types.is_numeric_dtype(stored[c])]
    same = len(stored) == len(fresh) and all(
        stored[c].equals(fresh[c]) for c in shared if c not in numeric
    )
    worst = 0.0
    if same and numeric:
        a, b = stored[numeric].to_numpy(dtype=float), fresh[numeric].to_numpy(dtype=float)
        worst = float(np.nanmax(np.abs(a - b) / (1e-9 + np.abs(a))))
        same = bool(np.array_equal(np.isnan(a), np.isnan(b)) and worst <= 1e-8)
    if not same or decision != exp.decision:
        shutil.rmtree(scratch)
        print(
            f"error: {exp.id} did NOT reproduce (largest relative difference {worst:.2e}, "
            f"decision {decision} vs recorded {exp.decision}). The stored report is unchanged.",
            file=sys.stderr,
        )
        return 1
    summary = json.loads((scratch / "summary.json").read_text())
    summary["original_run"] = old_summary.get("original_run", old_summary["run"])
    summary["reproduction"] = {
        "run": info.as_dict(),
        "pinned_config_hash": exp.config_hash,
        "columns_compared": shared,
        "largest_relative_difference": worst,
    }
    summary["run"] = summary["original_run"]
    (scratch / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    shutil.rmtree(out_dir)
    scratch.rename(out_dir)
    print(f"{exp.id}: reproduced ({len(shared)} columns, largest relative difference {worst:.1e})")
    print(f"report: {out_dir / 'report.md'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mm-sim", description=__doc__.splitlines()[0])
    parser.add_argument("--version", action="version", version=f"mm-sim {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
        p.add_argument("--scenario", default=None, help="name of a file in scenarios/")

    p_check = sub.add_parser("check-config", help="validate the config and print it")
    add_common(p_check)
    p_check.set_defaults(func=cmd_check_config)

    p_run = sub.add_parser("run", help="Monte Carlo run of one strategy")
    add_common(p_run)
    p_run.add_argument("--strategy", required=True, choices=sorted(REGISTRY))
    p_run.add_argument("--episodes", type=int, default=None, help="default: analysis.episodes")
    p_run.add_argument("--seed", type=int, default=None, help="default: analysis.seed")
    p_run.set_defaults(func=cmd_run)

    p_exp = sub.add_parser("experiment", help="run an approved pre-registered experiment")
    p_exp.add_argument("id", help="for example EXP-001")
    p_exp.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    p_exp.set_defaults(func=cmd_experiment)

    p_rep = sub.add_parser("reproduce", help="rebuild a finished experiment and verify it")
    p_rep.add_argument("id", help="for example EXP-001")
    p_rep.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    p_rep.set_defaults(func=cmd_reproduce)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        code: int = args.func(args)
    except (ValidationError, ValueError, FileNotFoundError, ExperimentError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return code


if __name__ == "__main__":
    sys.exit(main())
