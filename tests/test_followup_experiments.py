"""Follow-up experiments: the independent-seed formula check and the head-to-head comparison."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from test_experiments_and_cli import _workspace

from mm_sim.analysis.exp_formula_check import SEED_STEP, pooled_z
from mm_sim.analysis.exp_formula_check import verdict as formula_verdict
from mm_sim.analysis.exp_head_to_head import verdict as duel_verdict
from mm_sim.cli import main
from mm_sim.config import load_config

FORMULA_FRONT = """---
id: EXP-906
title: "test formula check"
status: approved
approved_by: "Nick"
approved_on: 2026-11-10
scenario: "baseline"
config_hash: "{config_hash}"
decision: null
kind: "independent_seed_check"
strategy: "fixed"
grid: {{}}
seed: 50
episodes: 60
settings:
  std_half_spreads: [0.4, 1.0]
  informed: {{"flow.informed.horizon_steps": 50, "engine.q_max": 200}}
  mean_cells: [[40.0, 0.2], [200.0, 0.6]]
---
"""

DUEL_FRONT = """---
id: EXP-907
title: "test head to head"
status: approved
approved_by: "Nick"
approved_on: 2026-11-10
scenario: "inventory"
config_hash: "{config_hash}"
decision: null
kind: "head_to_head"
strategy: "skew"
grid: {{}}
seed: 51
episodes: 80
settings:
  a: {{"strategy": "skew", "params": {{"half_spread": 0.75, "kappa": 0.2}}}}
  b: {{"strategy": "avellaneda_stoikov", "params": {{"gamma": 0.1}}}}
---
"""


def _run(tmp_path: Path, exp_id: str, scenario: str, front: str) -> Path:
    config = _workspace(tmp_path)
    _, h = load_config(config, scenario)
    (tmp_path / "experiments" / f"{exp_id}_test.md").write_text(front.format(config_hash=h))
    assert main(["experiment", exp_id, "--config", str(config)]) == 0
    out = tmp_path / "reports" / "experiments" / exp_id
    report = (out / "report.md").read_text()
    assert report.index("## Limitations") < report.index("## Results")
    assert report.index("## Results") < report.index("## Verdict against the pre-registered")
    return out


def test_cli_formula_check_uses_an_independent_seed_per_cell(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = _run(tmp_path, "EXP-906", "baseline", FORMULA_FRONT)
    cells = pd.read_csv(out / "cells.csv")
    assert cells["part"].tolist() == ["A_std", "A_std", "B_mean", "B_mean"]
    assert cells["seed"].tolist() == [50 + i * SEED_STEP for i in range(4)]  # all different
    assert cells["informed_intensity"].tolist() == [0.0, 0.0, 40.0, 200.0]
    assert (cells["se"] > 0).all()
    a = cells[cells["part"] == "A_std"]
    # the table is stored with 10 significant digits
    assert ((a["ratio"] - a["simulated"] / a["theory"]).abs() < 1e-8).all()
    log = pd.read_csv(tmp_path / "experiments" / "trial_log.csv")
    assert log["seed"].tolist() == cells["seed"].tolist()
    assert json.loads(log["parameters"][3])["flow.informed.intensity"] == 200.0


def test_formula_check_verdict_and_pooled_z() -> None:
    """Four independent cells with z = 1.6 each: no single cell is beyond 3, but the pooled
    statistic is 1.6 * sqrt(4) = 3.2, which a common bias would produce: REJECTED."""
    assert pooled_z(pd.Series([1.6, 1.6, 1.6, 1.6])) == pytest.approx(3.2)
    assert pooled_z(pd.Series([2.0, -2.0, 1.0, -1.0])) == pytest.approx(0.0)

    def table(z_std: list[float], z_mean: list[float]) -> pd.DataFrame:
        return pd.DataFrame(
            {"part": ["A_std"] * len(z_std) + ["B_mean"] * len(z_mean), "z": z_std + z_mean}
        )

    assert formula_verdict(table([0.5, -1.0, 2.0, -0.3], [1.0, -1.5, 0.2, 0.4]))[0] == "CONFIRMED"
    decision, checks = formula_verdict(table([1.6] * 4, [1.0, -1.5, 0.2, 0.4]))
    assert decision == "REJECTED"
    assert [ok for ok in checks.values()] == [True, False, True, True]
    assert formula_verdict(table([0.5, -1.0, 2.0, -0.3], [0.1, 3.4, 0.2, 0.4]))[0] == "REJECTED"


def test_cli_head_to_head(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = _run(tmp_path, "EXP-907", "inventory", DUEL_FRONT)
    table = pd.read_csv(out / "head_to_head.csv").set_index("measure")
    assert list(table.index) == ["pnl_liquidated", "pnl_mtm"]
    r = table.loc["pnl_liquidated"]
    assert r["a"].startswith("skew") and r["b"].startswith("avellaneda_stoikov")
    assert r["mean_diff"] == pytest.approx(r["mean_a"] - r["mean_b"])
    assert r["std_ratio"] == pytest.approx(r["std_a"] / r["std_b"])
    assert r["std_ratio_ci_low"] <= r["std_ratio"] <= r["std_ratio_ci_high"]
    # liquidation costs something: liquidated mean is below mark-to-market for both
    assert r["mean_a"] < table.loc["pnl_mtm", "mean_a"]
    assert r["mean_b"] < table.loc["pnl_mtm", "mean_b"]
    log = pd.read_csv(tmp_path / "experiments" / "trial_log.csv")
    assert log["strategy"].tolist() == ["skew", "avellaneda_stoikov"]


def test_head_to_head_verdict() -> None:
    def table(diff_lo: float, diff_hi: float, ratio_lo: float, ratio_hi: float) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "measure": ["pnl_liquidated", "pnl_mtm"],
                "mean_diff_ci_low": [diff_lo, -9.0],
                "mean_diff_ci_high": [diff_hi, -8.0],
                "std_ratio_ci_low": [ratio_lo, 2.0],
                "std_ratio_ci_high": [ratio_hi, 3.0],
            }
        )

    assert duel_verdict(table(0.4, 1.6, 0.88, 0.98))[0] == "CONFIRMED"  # the MTM row is ignored
    assert duel_verdict(table(-1.6, -0.4, 0.88, 0.98))[0] == "REJECTED"  # B earns more
    assert duel_verdict(table(0.4, 1.6, 1.02, 1.10))[0] == "REJECTED"  # A is riskier
    assert duel_verdict(table(-0.4, 1.6, 0.88, 0.98))[0] == "INCONCLUSIVE"
    assert duel_verdict(table(0.4, 1.6, 0.95, 1.05))[0] == "INCONCLUSIVE"
