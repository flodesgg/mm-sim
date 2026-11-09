"""Stage D: report structure, SUSPICIOUS checks, reproduction, robustness."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from helpers import make_cfg
from test_experiments_and_cli import FRONT, HEATMAP_FRONT, _workspace

from mm_sim.analysis import suspicious
from mm_sim.analysis.exp_robustness import _status, labels, verdict
from mm_sim.analysis.montecarlo import run_monte_carlo, with_run_settings
from mm_sim.cli import main
from mm_sim.config import load_config
from mm_sim.reports.sections import decomposition_error
from mm_sim.strategies import build_strategy

SECTION_ORDER = [
    "## Limitations",
    "## Setup",
    "## Results",
    "## Representative grid point in detail",
    "### P&L decomposition",
    "### Markouts by counterparty",
    "## Verdict against the pre-registered hypothesis",
    "## What depends on the model's assumptions",
]

ROBUSTNESS_FRONT = """---
id: EXP-905
title: "test robustness"
status: approved
approved_by: "Nick"
approved_on: 2026-11-09
scenario: "baseline"
config_hash: "{config_hash}"
decision: null
kind: "robustness"
strategy: "fixed"
grid: {{}}
seed: 5
episodes: 60
settings:
  variants:
    base: {{}}
    sigma_high: {{"market.sigma": 4.0}}
  spread_factor: 3.0
  informed: {{"flow.informed.intensity": 120.0, "flow.informed.horizon_steps": 50}}
  narrow_half_spread: 0.1
  inventory: {{"engine.liq_half_spread": 0.5, "engine.liq_impact": 0.05}}
  as_gamma: 0.1
  skew_kappa: 0.05
  latency: {{"engine.q_max": 200}}
  slow_requote: 5
---
"""


def _run_experiment(tmp_path: Path, exp_id: str, scenario: str, front: str) -> tuple[Path, Path]:
    config = _workspace(tmp_path)
    _, h = load_config(config, scenario)
    exp_file = tmp_path / "experiments" / f"{exp_id}_test.md"
    exp_file.write_text(front.format(config_hash=h, status="approved", approved_by='"Nick"',
                                     approved_on="2026-11-09"))  # fmt: skip
    assert main(["experiment", exp_id, "--config", str(config)]) == 0
    return config, exp_file


def _mark_done(tmp_path: Path, exp_file: Path, exp_id: str) -> None:
    out = tmp_path / "reports" / "experiments" / exp_id
    decision = json.loads((out / "summary.json").read_text())["decision"]
    text = exp_file.read_text().replace("status: approved", "status: done")
    exp_file.write_text(text.replace("decision: null", f'decision: "{decision}"'))


@pytest.mark.parametrize(
    ("exp_id", "scenario", "front"),
    [("EXP-901", "baseline", FRONT), ("EXP-902", "toxic", HEATMAP_FRONT),
     ("EXP-905", "baseline", ROBUSTNESS_FRONT)],
)  # fmt: skip
def test_experiment_reports_follow_the_fixed_section_order(
    tmp_path: Path, exp_id: str, scenario: str, front: str, capsys: pytest.CaptureFixture[str]
) -> None:
    _run_experiment(tmp_path, exp_id, scenario, front)
    out = tmp_path / "reports" / "experiments" / exp_id
    report = (out / "report.md").read_text()
    positions = [report.index(heading) for heading in SECTION_ORDER]
    assert positions == sorted(positions)
    for figure in ("markouts.png", "example_episode.png", "inventory_histogram.png"):
        assert (out / figure).stat().st_size > 0
        assert f"({figure})" in report


def test_reproduce_rebuilds_and_verifies_a_finished_experiment(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config, exp_file = _run_experiment(tmp_path, "EXP-901", "baseline", FRONT)
    out = tmp_path / "reports" / "experiments" / "EXP-901"
    log = tmp_path / "experiments" / "trial_log.csv"
    # not finished yet: reproduce refuses
    assert main(["reproduce", "EXP-901", "--config", str(config)]) == 2
    _mark_done(tmp_path, exp_file, "EXP-901")
    original_run = json.loads((out / "summary.json").read_text())["run"]
    stored, lines_before = (out / "sweep.csv").read_text(), log.read_text()
    (out / "pnl_vs_half_spread.png").unlink()  # a lost figure comes back

    assert main(["reproduce", "EXP-901", "--config", str(config)]) == 0
    assert "reproduced" in capsys.readouterr().out
    assert (out / "sweep.csv").read_text() == stored  # byte-identical numbers
    assert (out / "pnl_vs_half_spread.png").stat().st_size > 0
    assert log.read_text() == lines_before  # a reproduction is not a new trial
    summary = json.loads((out / "summary.json").read_text())
    assert summary["run"] == original_run == summary["original_run"]
    assert summary["reproduction"]["largest_relative_difference"] == 0.0

    # a stored table that the code cannot regenerate is reported, and left untouched
    tampered = pd.read_csv(out / "sweep.csv")
    tampered.loc[0, "mean_pnl"] += 1.0
    tampered.to_csv(out / "sweep.csv", index=False)
    assert main(["reproduce", "EXP-901", "--config", str(config)]) == 1
    assert "did NOT reproduce" in capsys.readouterr().err
    assert pd.read_csv(out / "sweep.csv").loc[0, "mean_pnl"] == tampered.loc[0, "mean_pnl"]
    assert not out.with_name("EXP-901.reproduce").exists()


def test_cli_robustness_experiment(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _run_experiment(tmp_path, "EXP-905", "baseline", ROBUSTNESS_FRONT)
    out = tmp_path / "reports" / "experiments" / "EXP-905"
    table = pd.read_csv(out / "robustness.csv")
    assert set(table["conclusion"]) == {"K1a", "K1b", "K2", "K3a", "K3b", "K4"}
    assert set(table["variant"]) == {"base", "sigma_high"}
    assert set(table["status"]) <= {"holds", "flipped", "unresolved"}
    k2 = table[table["conclusion"] == "K2"]
    assert (k2["ci_high"] < 0).all() and (k2["status"] == "holds").all()
    log = pd.read_csv(tmp_path / "experiments" / "trial_log.csv")
    assert len(log) == 2 * 10  # ten runs per variant
    assert json.loads(log["parameters"][0])["variant"] == "base"


def test_robustness_status_labels_and_verdict() -> None:
    assert _status(0.5, 1.5, +1) == "holds"
    assert _status(-1.5, -0.5, +1) == "flipped"
    assert _status(-0.5, 0.5, +1) == "unresolved"
    assert _status(-1.5, -0.5, -1) == "holds"
    assert _status(0.5, 1.5, -1) == "flipped"

    def table(k4_status: str) -> pd.DataFrame:
        rows = []
        for key in ("K1a", "K1b", "K2", "K3a", "K3b", "K4"):
            for variant in ("base", "other"):
                status = k4_status if (key, variant) == ("K4", "other") else "holds"
                rows.append({"conclusion": key, "variant": variant, "status": status})
        return pd.DataFrame(rows)

    assert verdict(table("holds"))[0] == "CONFIRMED"
    assert labels(table("flipped"))["K4"] == "fragile"
    assert verdict(table("flipped"))[0] == "REJECTED"
    assert labels(table("unresolved"))["K4"] == "unresolved"
    assert verdict(table("unresolved"))[0] == "INCONCLUSIVE"


# ---------------------------------------------------------------- SUSPICIOUS checks


def _episodes(scenario_overrides: dict, strategy: str, n: int = 150, **params: float):
    cfg = with_run_settings(make_cfg(**scenario_overrides), 6, n)
    built, full = build_strategy(cfg, strategy, params or None)
    return cfg, full, run_monte_carlo(cfg, built)


TOXIC = {"flow": {"informed": {"intensity": 200.0, "horizon_steps": 50}}, "engine": {"q_max": 200}}
TWO_POINT = {
    "market": {"process": "two_point", "world": "trades_only", "n_steps": 100, "tick_size": 1e-4},
    "engine": {"q_max": 1000},
}


def test_honest_runs_raise_no_flag() -> None:
    for overrides, strategy, params in (
        ({}, "fixed", {}),
        ({}, "skew", {}),
        ({}, "avellaneda_stoikov", {}),
        (TOXIC, "fixed", {"half_spread": 0.05}),
        (TWO_POINT, "glosten_milgrom", {}),
        (TWO_POINT, "fixed_prior", {}),
    ):
        cfg, full, ep = _episodes(overrides, strategy, **params)
        checks = suspicious.run_checks(cfg, strategy, full, ep)
        assert [c.name for c in checks if not c.ok] == [], (strategy, [c.detail for c in checks])
        assert any("clairvoyant" in c.name for c in checks)


def test_decomposition_flag() -> None:
    _, _, ep = _episodes({}, "fixed", n=20)
    assert suspicious.check_decomposition(ep).ok
    broken = ep.copy()
    broken.loc[3, "spread_capture"] += 0.01  # an accounting bug of one cent in one episode
    assert decomposition_error(broken) == pytest.approx(0.01)
    assert not suspicious.check_decomposition(broken).ok


def test_profit_below_break_even_is_flagged() -> None:
    cfg, full, ep = _episodes(TOXIC, "fixed", half_spread=0.05)
    check = suspicious.check_break_even(cfg, "fixed", full, ep)
    assert check is not None and check.ok  # it loses money, as it should
    lucky = ep.copy()
    lucky["pnl_mtm"] = lucky["pnl_mtm"].abs() + 10.0  # a "result" that cannot be right
    flagged = suspicious.check_break_even(cfg, "fixed", full, lucky)
    assert flagged is not None and not flagged.ok
    # no closed form with latency or without informed flow: the check does not apply
    assert suspicious.check_break_even(make_cfg(), "fixed", {"half_spread": 0.05}, ep) is None
    assert suspicious.check_break_even(cfg, "skew", full, ep) is None


def test_glosten_milgrom_profit_is_flagged() -> None:
    _, _, ep = _episodes(TWO_POINT, "glosten_milgrom")
    ok = suspicious.check_glosten_milgrom("glosten_milgrom", ep)
    assert ok is not None and ok.ok
    biased = ep.copy()
    biased["pnl_mtm"] += 1.0  # a market maker that should break even but earns 1.0 per episode
    flagged = suspicious.check_glosten_milgrom("glosten_milgrom", biased)
    assert flagged is not None and not flagged.ok
    assert suspicious.check_glosten_milgrom("fixed_prior", biased) is None


def test_beating_the_clairvoyant_is_flagged() -> None:
    cfg, _, ep = _episodes({}, "fixed")
    assert suspicious.check_clairvoyant(cfg, ep).ok
    impossible = ep.copy()
    impossible["pnl_mtm"] += 1000.0
    check = suspicious.check_clairvoyant(cfg, impossible)
    assert not check.ok and "not a strategy" in check.detail


def test_run_report_lists_sanity_checks_in_order(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = _workspace(tmp_path)
    args = ["run", "--config", str(config), "--scenario", "two_point", "--episodes", "60"]
    assert main([*args, "--strategy", "glosten_milgrom", "--seed", "4"]) == 0
    (run_dir,) = (tmp_path / "reports" / "runs").iterdir()
    report = (run_dir / "report.md").read_text()
    order = ["## Limitations", "## Setup", "## Results", "## P&L decomposition",
             "## Markouts by counterparty", "## Sanity checks", "## Figures"]  # fmt: skip
    positions = [report.index(h) for h in order]
    assert positions == sorted(positions)
    assert "- ok: Glosten-Milgrom mean profit is zero" in report
    assert "SUSPICIOUS**:" not in report
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["suspicious"] == [] and len(summary["checks"]) == 3
    assert np.isfinite(summary["pnl_mtm"]["mean"])
