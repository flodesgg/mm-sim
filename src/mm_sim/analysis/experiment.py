"""Pre-registered experiments: load the experiment file and refuse to run it unless it is
approved and pinned to the current config hash.

An experiment file is markdown with a YAML front matter. The hypothesis and the numbers that
confirm or reject it are written before the run; the run happens once.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field

from mm_sim.config import StrictModel


class ExperimentError(Exception):
    """The experiment must not run (not approved, already done, or the config changed)."""


class Experiment(StrictModel):
    id: str = Field(pattern=r"^EXP-\d{3}$")
    title: str
    status: Literal["draft", "approved", "done"]
    approved_by: str | None
    approved_on: date | None
    scenario: str
    config_hash: str | None  # the scenario's hash from `mm-sim check-config --scenario ...`
    decision: Literal["CONFIRMED", "REJECTED", "INCONCLUSIVE"] | None
    kind: str  # which analysis runs it (see EXPERIMENT_KINDS in cli.py)
    strategy: str
    grid: dict[str, list[float]]  # strategy parameter -> values to sweep
    # dotted config key -> values to sweep (optional)
    config_grid: dict[str, list[float]] = Field(default_factory=dict)
    seed: int = Field(ge=0)
    episodes: int = Field(ge=1)


def load_experiment(path: Path) -> Experiment:
    text = path.read_text()
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise ExperimentError(f"{path}: missing YAML front matter between '---' lines")
    front = yaml.safe_load(text[4 : text.index("\n---\n", 4)])
    if not isinstance(front, dict):
        raise ExperimentError(f"{path}: front matter must be a mapping")
    return Experiment.model_validate(front)


def find_experiment(experiments_dir: Path, exp_id: str) -> Path:
    matches = sorted(experiments_dir.glob(f"{exp_id}_*.md")) + sorted(
        experiments_dir.glob(f"{exp_id}.md")
    )
    if len(matches) != 1:
        raise ExperimentError(f"expected exactly one file for {exp_id}, found {len(matches)}")
    return matches[0]


def check_runnable(exp: Experiment, current_hash: str) -> None:
    """Raise unless the experiment is approved and pinned to the current config."""
    if exp.status == "done":
        raise ExperimentError(
            f"{exp.id} has already run (status done). A new idea is a new experiment number."
        )
    if exp.status != "approved" or not exp.approved_by or exp.approved_on is None:
        raise ExperimentError(
            f"{exp.id} is not approved (status {exp.status!r}). Nick sets status, approved_by "
            "and approved_on in the experiment file before it runs."
        )
    if exp.config_hash != current_hash:
        raise ExperimentError(
            f"{exp.id} is pinned to config hash {exp.config_hash}, but scenario "
            f"{exp.scenario!r} now hashes to {current_hash}. The configuration changed after "
            "the experiment was written; re-register it."
        )
