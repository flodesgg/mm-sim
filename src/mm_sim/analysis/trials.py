"""The trial log: one line for every run and every sweep point, so the number of variants
tried is always visible."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from mm_sim.runinfo import RunInfo

COLUMNS = (
    "run_id",
    "started_utc",
    "git_commit",
    "config_hash",
    "experiment",
    "scenario",
    "strategy",
    "parameters",
    "seed",
    "episodes",
)


def trial_log_path(experiments_dir: Path) -> Path:
    return experiments_dir / "trial_log.csv"


def append_trial(
    experiments_dir: Path,
    info: RunInfo,
    experiment: str,
    strategy: str,
    parameters: dict[str, object],
    seed: int,
    episodes: int,
) -> None:
    path = trial_log_path(experiments_dir)
    new = not path.exists()
    with path.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(COLUMNS)
        w.writerow(
            [
                info.run_id,
                info.started_utc,
                info.git_commit,
                info.config_hash,
                experiment,
                info.scenario,
                strategy,
                json.dumps(parameters, sort_keys=True),
                seed,
                episodes,
            ]
        )


def count_trials(experiments_dir: Path) -> int:
    path = trial_log_path(experiments_dir)
    if not path.exists():
        return 0
    with path.open() as f:
        return max(sum(1 for _ in f) - 1, 0)
