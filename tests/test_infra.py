from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from mm_sim.cli import main
from mm_sim.config import LoggingConfig
from mm_sim.logging_setup import setup_logging
from mm_sim.runinfo import new_run_info

REPO = Path(__file__).resolve().parents[1]


def test_run_info_fields_and_unique_ids(tmp_path: Path) -> None:
    a = new_run_info("abc123abc123", "baseline", repo=tmp_path)
    b = new_run_info("abc123abc123", "baseline", repo=tmp_path)
    assert a.run_id != b.run_id
    assert a.git_commit == "no-git"  # tmp_path is not a repository
    assert a.as_dict()["config_hash"] == "abc123abc123"
    assert a.as_dict()["scenario"] == "baseline"


def test_run_info_reads_git_commit(tmp_path: Path) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    (tmp_path / "f.txt").write_text("x")
    git("add", ".")
    git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "c")
    info = new_run_info("h", "s", repo=tmp_path)
    assert len(info.git_commit) == 12
    assert info.git_dirty is False
    (tmp_path / "f.txt").write_text("y")
    assert new_run_info("h", "s", repo=tmp_path).git_dirty is True


def test_logging_writes_run_id_and_rotates(tmp_path: Path) -> None:
    cfg = LoggingConfig(level="INFO", file="t.log", max_bytes=300, backup_count=2)
    log = setup_logging(cfg, tmp_path, "run-xyz")
    for i in range(30):
        log.info("message number %d", i)
    for h in log.handlers:
        h.flush()
    assert "[run=run-xyz]" in (tmp_path / "t.log").read_text()
    assert (tmp_path / "t.log.1").exists()  # rotation happened
    assert not (tmp_path / "t.log.3").exists()  # backup_count respected
    # idempotent: a second call does not duplicate handlers
    assert len(setup_logging(cfg, tmp_path, "run-2").handlers) == 2


def test_logs_and_data_are_ignored() -> None:
    lines = (REPO / ".gitignore").read_text().splitlines()
    assert "/logs/" in lines
    assert "/data/" in lines


def _config_in(tmp_path: Path) -> Path:
    """Repo config with the log directory redirected into tmp_path."""
    text = (REPO / "config.yaml").read_text().replace('logs: "logs"', f'logs: "{tmp_path}/logs"')
    p = tmp_path / "config.yaml"
    p.write_text(text)
    (tmp_path / "scenarios").mkdir()
    for s in (REPO / "scenarios").glob("*.yaml"):
        (tmp_path / "scenarios" / s.name).write_text(s.read_text())
    return p


def test_cli_check_config_prints_hash(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    p = _config_in(tmp_path)
    assert main(["check-config", "--config", str(p), "--scenario", "baseline"]) == 0
    out = capsys.readouterr().out
    assert "config OK   scenario=baseline" in out
    assert "config_hash " in out
    assert (tmp_path / "logs" / "mm_sim.log").exists()


def test_cli_reports_invalid_config_with_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    p = _config_in(tmp_path)
    p.write_text(p.read_text().replace("sigma: 2.0", "sigma: -1.0"))
    assert main(["check-config", "--config", str(p)]) == 2
    assert "sigma" in capsys.readouterr().err


def test_cli_unknown_scenario_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check-config", "--config", str(_config_in(tmp_path)), "--scenario", "nope"]) == 2
    assert "unknown scenario" in capsys.readouterr().err
