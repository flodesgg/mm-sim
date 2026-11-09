"""The pre-registration gate, the trial log, and the `run` / `experiment` commands."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from mm_sim.analysis.exp_fixed_spread import verdict
from mm_sim.analysis.experiment import (
    ExperimentError,
    check_runnable,
    find_experiment,
    load_experiment,
)
from mm_sim.cli import main
from mm_sim.config import load_config

REPO = Path(__file__).resolve().parents[1]

FRONT = """---
id: EXP-901
title: "test sweep"
status: {status}
approved_by: {approved_by}
approved_on: {approved_on}
scenario: "baseline"
config_hash: "{config_hash}"
decision: null
kind: "fixed_spread_sweep"
strategy: "fixed"
grid:
  half_spread: [0.3, 0.7, 1.5]
seed: 5
episodes: 30
---

# body
"""


def _workspace(tmp_path: Path) -> Path:
    """A copy of the repo's config and scenarios with every output path inside tmp_path."""
    text = (REPO / "config.yaml").read_text()
    for key in ("reports", "experiments", "logs", "play"):
        text = text.replace(f'{key}: "{key}"', f'{key}: "{tmp_path}/{key}"')
    (tmp_path / "config.yaml").write_text(text)
    (tmp_path / "scenarios").mkdir()
    for s in (REPO / "scenarios").glob("*.yaml"):
        (tmp_path / "scenarios" / s.name).write_text(s.read_text())
    (tmp_path / "experiments").mkdir()
    return tmp_path / "config.yaml"


def _write_exp(tmp_path: Path, config: Path, **fields: str) -> Path:
    _, h = load_config(config, "baseline")
    values = {
        "status": "approved",
        "approved_by": '"Nick"',
        "approved_on": "2026-11-09",
        "config_hash": h,
    }
    path = tmp_path / "experiments" / "EXP-901_test.md"
    path.write_text(FRONT.format(**{**values, **fields}))
    return path


def test_gate_refuses_draft_done_and_changed_config(tmp_path: Path) -> None:
    config = _workspace(tmp_path)
    _, h = load_config(config, "baseline")

    check_runnable(load_experiment(_write_exp(tmp_path, config)), h)  # approved: no error

    draft = load_experiment(
        _write_exp(tmp_path, config, status="draft", approved_by="null", approved_on="null")
    )
    with pytest.raises(ExperimentError, match="not approved"):
        check_runnable(draft, h)

    no_name = load_experiment(_write_exp(tmp_path, config, approved_by="null"))
    with pytest.raises(ExperimentError, match="not approved"):
        check_runnable(no_name, h)

    done = load_experiment(_write_exp(tmp_path, config, status="done"))
    with pytest.raises(ExperimentError, match="already run"):
        check_runnable(done, h)

    stale = load_experiment(_write_exp(tmp_path, config, config_hash="000000000000"))
    with pytest.raises(ExperimentError, match="configuration changed"):
        check_runnable(stale, h)


def test_find_experiment_needs_exactly_one_file(tmp_path: Path) -> None:
    config = _workspace(tmp_path)
    with pytest.raises(ExperimentError, match="found 0"):
        find_experiment(tmp_path / "experiments", "EXP-901")
    path = _write_exp(tmp_path, config)
    assert find_experiment(tmp_path / "experiments", "EXP-901") == path


def test_repo_experiment_files_parse() -> None:
    for path in sorted((REPO / "experiments").glob("EXP-*.md")):
        if "template" not in path.name:
            assert load_experiment(path).id == path.name[:7]


def test_cli_experiment_refuses_a_draft(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = _workspace(tmp_path)
    _write_exp(tmp_path, config, status="draft", approved_by="null", approved_on="null")
    assert main(["experiment", "EXP-901", "--config", str(config)]) == 2
    assert "not approved" in capsys.readouterr().err
    assert not (tmp_path / "reports").exists()


def test_cli_experiment_runs_once_and_logs_every_grid_point(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = _workspace(tmp_path)
    _write_exp(tmp_path, config)
    assert main(["experiment", "EXP-901", "--config", str(config)]) == 0
    out = tmp_path / "reports" / "experiments" / "EXP-901"
    for name in ("sweep.csv", "summary.json", "report.md", "pnl_vs_half_spread.png"):
        assert (out / name).stat().st_size > 0
    report = (out / "report.md").read_text()
    assert report.index("## Limitations") < report.index("## Results")
    sweep = pd.read_csv(out / "sweep.csv")
    assert sweep["half_spread"].tolist() == [0.3, 0.7, 1.5]
    log = pd.read_csv(tmp_path / "experiments" / "trial_log.csv")
    assert log["experiment"].tolist() == ["EXP-901"] * 3
    assert json.loads(log["parameters"][1]) == {"half_spread": 0.7}
    capsys.readouterr()
    # the second attempt is refused: the output directory exists
    assert main(["experiment", "EXP-901", "--config", str(config)]) == 2
    assert "already run" in capsys.readouterr().err


def test_cli_run_writes_report_summary_episodes_and_figure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = _workspace(tmp_path)
    args = ["run", "--config", str(config), "--scenario", "baseline", "--strategy", "fixed"]
    assert main([*args, "--episodes", "25", "--seed", "9"]) == 0
    assert "mean P&L (MTM)" in capsys.readouterr().out
    (run_dir,) = (tmp_path / "reports" / "runs").iterdir()
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["seed"] == 9 and summary["episodes"] == 25
    assert summary["run"]["config_hash"] == load_config(config, "baseline")[1]
    assert summary["decomposition_max_abs_error"] < 1e-9
    episodes = pd.read_csv(run_dir / "episodes.csv", index_col="episode")
    assert len(episodes) == 25
    assert summary["pnl_mtm"]["mean"] == pytest.approx(episodes["pnl_mtm"].mean())
    report = (run_dir / "report.md").read_text()
    assert report.index("## Limitations") < report.index("## Results")
    assert "not annualised" in report
    assert (run_dir / "example_episode.png").stat().st_size > 0
    log = pd.read_csv(tmp_path / "experiments" / "trial_log.csv")
    assert len(log) == 1 and log["seed"][0] == 9


def _table(
    z: list[float],
    ratio: list[float],
    std: list[float],
    mean: list[float],
    theory_mean: tuple[float, ...] = (40.0, 60.0, 50.0),
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "half_spread": [0.2, 0.6, 1.0],
            "mean_pnl": mean,
            "theory_mean": list(theory_mean),
            "z_mean": z,
            "std_ratio": ratio,
            "std_pnl": std,
        }
    )


def test_verdict_rule() -> None:
    good = _table([0.5, -1.0, 2.0], [1.0, 0.95, 1.05], [15, 12, 9], [41, 59, 50])
    assert verdict(good)[0] == "CONFIRMED"
    wrong_mean = _table([0.5, -4.0, 2.0], [1.0, 0.95, 1.05], [15, 12, 9], [41, 59, 50])
    assert verdict(wrong_mean)[0] == "REJECTED"
    wrong_std = _table([0.5, -1.0, 2.0], [1.0, 0.8, 1.05], [15, 12, 9], [41, 59, 50])
    assert verdict(wrong_std)[0] == "REJECTED"
    std_rises = _table([0.5, -1.0, 2.0], [1.0, 0.95, 1.05], [9, 12, 15], [41, 59, 50])
    assert verdict(std_rises)[0] == "INCONCLUSIVE"
    best_far_away = _table(
        [0.5, -1.0, 2.0], [1.0, 0.95, 1.05], [15, 12, 9], [41, 39, 60], (60.0, 50.0, 40.0)
    )
    assert verdict(best_far_away)[0] == "INCONCLUSIVE"
