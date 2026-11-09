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


# ---------------------------------------------------------------- EXP-002 kind (heatmap)

HEATMAP_FRONT = """---
id: EXP-902
title: "test heatmap"
status: approved
approved_by: "Nick"
approved_on: 2026-11-09
scenario: "toxic"
config_hash: "{config_hash}"
decision: null
kind: "spread_intensity_heatmap"
strategy: "fixed"
grid:
  half_spread: [0.05, 0.4, 1.0]
config_grid:
  flow.informed.intensity: [0.0, 200.0]
seed: 5
episodes: 30
---
"""


def test_simulated_break_even_by_hand() -> None:
    """Means -10, -2, +6 at h = 0.1, 0.2, 0.4: the zero is a quarter of the way from 0.2 to
    0.4 -> 0.25. Already positive at the first point -> that point. Never positive -> NaN."""
    import math

    import numpy as np

    from mm_sim.analysis.exp_heatmap import simulated_break_even

    h = np.array([0.1, 0.2, 0.4])
    assert simulated_break_even(h, np.array([-10.0, -2.0, 6.0])) == pytest.approx(0.25)
    assert simulated_break_even(h, np.array([1.0, 2.0, 3.0])) == 0.1
    assert math.isnan(simulated_break_even(h, np.array([-3.0, -2.0, -1.0])))


def test_cli_heatmap_experiment_writes_cells_and_break_even(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = _workspace(tmp_path)
    _, h = load_config(config, "toxic")
    (tmp_path / "experiments" / "EXP-902_test.md").write_text(HEATMAP_FRONT.format(config_hash=h))
    assert main(["experiment", "EXP-902", "--config", str(config)]) == 0
    out = tmp_path / "reports" / "experiments" / "EXP-902"
    for name in ("cells.csv", "break_even.csv", "summary.json", "report.md", "heatmap.png"):
        assert (out / name).stat().st_size > 0
    cells = pd.read_csv(out / "cells.csv")
    assert len(cells) == 6
    no_informed = cells[cells["informed_intensity"] == 0]
    assert (no_informed["fills_informed"] == 0).all()
    assert (cells[cells["informed_intensity"] == 200]["fills_informed"] > 0).all()
    be = pd.read_csv(out / "break_even.csv").set_index("informed_intensity")
    assert be.loc[0.0, "break_even_theory"] == 0.0
    assert 0.3 < be.loc[200.0, "break_even_theory"] < 0.6
    log = pd.read_csv(tmp_path / "experiments" / "trial_log.csv")
    assert len(log) == 6
    report = (out / "report.md").read_text()
    assert report.index("## Limitations") < report.index("## Results")


def test_heatmap_verdict_rule_and_suspicious_flag() -> None:
    from mm_sim.analysis.exp_heatmap import verdict as heatmap_verdict

    def cells(z: float, ci_low_below_line: float) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "informed_intensity": [0.0, 0.0, 100.0, 100.0],
                "half_spread": [0.1, 0.5, 0.1, 0.5],
                "z_mean": [0.3, -0.5, z, 1.0],
                "ci_low": [5.0, 30.0, ci_low_below_line, 10.0],
            }
        )

    def be(sim: float) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "informed_intensity": [0.0, 100.0],
                "break_even_simulated": [0.1, sim],
                "break_even_theory": [0.0, 0.30],
            }
        )

    assert heatmap_verdict(cells(1.0, -20.0), be(0.32))[0] == "CONFIRMED"
    assert heatmap_verdict(cells(4.5, -20.0), be(0.32))[0] == "REJECTED"
    assert heatmap_verdict(cells(1.0, -20.0), be(0.40))[0] == "REJECTED"
    assert heatmap_verdict(cells(1.0, -20.0), be(0.09))[0] == "REJECTED"  # also not rising
    decision, _, flags = heatmap_verdict(cells(1.0, 2.0), be(0.32))
    assert len(flags) == 1 and "SUSPICIOUS" in flags[0]  # profit below the break-even line
    assert decision == "CONFIRMED"  # the flag is reported next to the verdict, not hidden


# ---------------------------------------------------------------- EXP-003 / EXP-004 kinds

FRONTIER_FRONT = """---
id: EXP-903
title: "test frontier"
status: approved
approved_by: "Nick"
approved_on: 2026-11-09
scenario: "inventory"
config_hash: "{config_hash}"
decision: null
kind: "inventory_frontier"
strategy: "avellaneda_stoikov"
grid:
  gamma: [0.1, 0.5]
  kappa: [0.05]
seed: 5
episodes: 40
---
"""

LATENCY_FRONT = """---
id: EXP-904
title: "test latency"
status: approved
approved_by: "Nick"
approved_on: 2026-11-09
scenario: "jumpy"
config_hash: "{config_hash}"
decision: null
kind: "latency_sweep"
strategy: "fixed"
grid: {{}}
config_grid:
  engine.requote_every: [1, 5]
seed: 5
episodes: 40
---
"""


def _run_kind(tmp_path: Path, exp_id: str, scenario: str, front: str) -> Path:
    config = _workspace(tmp_path)
    _, h = load_config(config, scenario)
    (tmp_path / "experiments" / f"{exp_id}_test.md").write_text(front.format(config_hash=h))
    assert main(["experiment", exp_id, "--config", str(config)]) == 0
    out = tmp_path / "reports" / "experiments" / exp_id
    report = (out / "report.md").read_text()
    assert report.index("## Limitations") < report.index("## Results")
    assert "## Verdict against the pre-registered hypothesis" in report
    return out


def test_cli_frontier_experiment(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = _run_kind(tmp_path, "EXP-903", "inventory", FRONTIER_FRONT)
    for name in ("frontier.csv", "frontier.png", "terminal_inventory.png", "summary.json"):
        assert (out / name).stat().st_size > 0
    table = pd.read_csv(out / "frontier.csv")
    assert table["strategy"].tolist() == ["avellaneda_stoikov", "avellaneda_stoikov", "skew"]
    # the benchmark quotes the same average spread as the variant (within rounding)
    assert (table["benchmark_quoted_spread"] - table["mean_quoted_spread"]).abs().max() < 0.03
    log = pd.read_csv(tmp_path / "experiments" / "trial_log.csv")
    assert log["strategy"].tolist() == [
        "avellaneda_stoikov", "fixed", "avellaneda_stoikov", "fixed", "skew", "fixed",
    ]  # fmt: skip


def test_cli_latency_experiment(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = _run_kind(tmp_path, "EXP-904", "jumpy", LATENCY_FRONT)
    table = pd.read_csv(out / "latency.csv").set_index("requote_every")
    assert table.loc[1, "pick_offs"] == 0 and table.loc[1, "theory_pick_offs"] == 0
    assert table.loc[5, "pick_offs"] > 1
    assert (out / "latency.png").stat().st_size > 0


def test_frontier_verdict_rule() -> None:
    from mm_sim.analysis.exp_frontier import verdict as frontier_verdict

    def table(ratio_hi: float, diff_lo: float, ce_lo: float, other_hi: float) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "strategy": ["avellaneda_stoikov", "avellaneda_stoikov", "skew", "skew"],
                "value": [0.01, 0.1, 0.01, 0.05],
                "std_ratio_ci_high": [1.05, ratio_hi, 1.02, other_hi],
                "mean_diff_ci_low": [-0.2, diff_lo, -0.1, -0.5],
                "bench_mean": [55.0, 55.0, 55.0, 55.0],
                "ce_diff_ci_low": [-0.1, ce_lo, -0.1, 1.0],
            }
        )

    assert frontier_verdict(table(0.6, -1.0, 2.0, 0.7))[0] == "CONFIRMED"  # small values exempt
    assert frontier_verdict(table(0.8, -1.0, 2.0, 0.7))[0] == "REJECTED"  # cut below 25%
    assert frontier_verdict(table(0.6, -1.0, 2.0, 1.01))[0] == "REJECTED"  # skew 0.05 no cut
    assert frontier_verdict(table(0.6, -9.0, 2.0, 0.7))[0] == "INCONCLUSIVE"  # costs > 15%
    assert frontier_verdict(table(0.6, -1.0, -0.5, 0.7))[0] == "INCONCLUSIVE"  # CE not higher


def test_latency_verdict_rule() -> None:
    from mm_sim.analysis.exp_latency import verdict as latency_verdict

    def table(z: float, means: list[float], z_pick: float, edge_hi: float) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "requote_every": [1, 5, 20],
                "z_mean": [0.2, z, -0.3],
                "mean_pnl": means,
                "z_pick_offs": [0.0, z_pick, 0.5],
                "edge_ci_high": [float("nan"), edge_hi, -0.3],
            }
        )

    assert latency_verdict(table(1.0, [60, 55, 30], 1.0, -0.2))[0] == "CONFIRMED"
    assert latency_verdict(table(4.5, [60, 55, 30], 1.0, -0.2))[0] == "REJECTED"
    assert latency_verdict(table(1.0, [60, 55, 30], -5.0, -0.2))[0] == "REJECTED"
    assert latency_verdict(table(1.0, [60, 61, 30], 1.0, -0.2))[0] == "INCONCLUSIVE"
    assert latency_verdict(table(1.0, [60, 55, 30], 1.0, 0.1))[0] == "INCONCLUSIVE"
