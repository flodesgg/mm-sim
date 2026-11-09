"""Stage E: the interactive game runs on the reference engine and is reproducible."""

from __future__ import annotations

import io
import os
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from rich.console import Console
from test_engine_steps import ScriptedStrategy
from test_experiments_and_cli import _workspace

from mm_sim.analysis.montecarlo import with_run_settings
from mm_sim.cli import main
from mm_sim.config import Config, load_config
from mm_sim.engine import reference
from mm_sim.play import game
from mm_sim.play.game import GameAborted, parse_quotes, round_table, run_game
from mm_sim.play.history import load_history, save_game
from mm_sim.strategies import REGISTRY, Quotes

REPO = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).parent / "fixtures" / "play_game_seed11.csv"

# 20 rounds for two_point_easy; includes two bad inputs that must be asked again
MOVES = ["99.6 100.4", "99.6 100.4", "abc", "100.5 100.2", "99.8 100.6", "99.9 100.7",
         "100.0 100.8", "100.1 100.9", *["100.2 101.0"] * 14]  # fmt: skip
QUOTES = [Quotes(*parse_quotes(m)) for m in MOVES if m not in ("abc", "100.5 100.2")]


def _cfg(scenario: str = "two_point_easy") -> Config:
    return load_config(REPO / "config.yaml", scenario)[0]


def _reader(lines: list[str]) -> Callable[[str], str]:
    it = iter(lines)

    def read(prompt: str) -> str:
        try:
            return next(it)
        except StopIteration as e:
            raise EOFError from e

    return read


def _console() -> Console:
    return Console(file=io.StringIO(), width=120)


def test_parse_quotes() -> None:
    assert parse_quotes("99.6 100.4") == (99.6, 100.4)
    assert parse_quotes("  99,6   100,4 ") == (99.6, 100.4)  # comma decimals
    for bad in ("", "100", "a b", "100.4 99.6", "100 100", "1 2 3", "nan 100"):
        with pytest.raises(ValueError, match=r"bid|numbers"):
            parse_quotes(bad)


def test_the_game_is_the_reference_engine() -> None:
    """No second implementation: the game calls the reference engine's `run_episode`, the
    human is not a registered strategy, and a scripted playthrough gives exactly the fills of
    running the engine directly with the same quotes."""
    assert game.run_episode is reference.run_episode
    assert game.build_flows is reference.build_flows
    assert "human" not in REGISTRY

    cfg = _cfg()
    console = _console()
    played = run_game(cfg, 11, _reader(MOVES), console)

    direct_cfg = with_run_settings(cfg, 11, 1)
    values = reference.episode_values(direct_cfg, 0)
    direct = reference.run_episode(
        direct_cfg, ScriptedStrategy(QUOTES), values, reference.build_flows(direct_cfg, 0, values)
    )
    assert played.episode.fills == direct.fills and len(direct.fills) > 5
    assert played.episode.cash == direct.cash
    np.testing.assert_array_equal(played.episode.bids, direct.bids)

    out = console.file.getvalue()  # type: ignore[attr-defined]
    assert "type two numbers: bid ask" in out and "the bid must be below the ask" in out
    assert "From informed traders" in out
    # the true value is revealed only after the last round's trade has been shown
    assert out.index("The value was") > out.rindex("-> a trader")


def test_scripted_playthrough_matches_the_stored_outcome() -> None:
    """Seed 11, the moves above. Regenerate only on purpose:
    MM_SIM_REGENERATE_FIXTURES=1 uv run pytest -k stored_outcome  (say why in the commit)."""
    result = run_game(_cfg(), 11, _reader(MOVES), _console())
    if os.environ.get("MM_SIM_REGENERATE_FIXTURES") == "1":
        result.rounds.to_csv(FIXTURE, index=False, float_format="%.10g")
    stored = pd.read_csv(FIXTURE, keep_default_na=False, na_values=["nan"])
    pd.testing.assert_frame_equal(
        result.rounds.reset_index(drop=True), stored, check_dtype=False, rtol=1e-9, atol=1e-9
    )
    s = result.summary
    assert s["true_value"] == 99.0
    assert s["pnl"] == pytest.approx(-7.0)
    assert (s["pnl_informed"], s["pnl_noise"]) == pytest.approx((-5.0, -2.0))
    assert (s["fills_informed"], s["fills_noise"]) == (5, 15)
    assert s["pnl_informed"] + s["pnl_noise"] == pytest.approx(s["pnl"])
    assert s["mean_spread"] == pytest.approx(0.8)


def test_round_table_shows_glosten_milgrom_quotes_from_the_same_tape() -> None:
    """mu = 0.2, V = 99/101, prior 1/2: first GM quotes 99.8 / 100.2. After the first trade
    (a sell) the posterior is 0.5*0.4 / (0.5*0.4 + 0.5*0.6) = 0.4 and the GM quotes are
    bid = 99 + 2 * 0.4*0.4/(0.4*0.4 + 0.6*0.6) = 99.6154, ask = 99 + 2 * 0.24/0.48 = 100.0."""
    result = run_game(_cfg(), 11, _reader(MOVES), _console())
    rows = round_table(with_run_settings(_cfg(), 11, 1), result.episode)
    assert (rows.loc[0, "gm_bid"], rows.loc[0, "gm_ask"]) == pytest.approx((99.8, 100.2))
    assert rows.loc[0, "trade_side"] == -1 and rows.loc[0, "counterparty"] == "informed"
    assert rows.loc[1, "gm_posterior"] == pytest.approx(0.4)
    assert (rows.loc[1, "gm_bid"], rows.loc[1, "gm_ask"]) == pytest.approx((99.615385, 100.0))
    # running P&L is marked at the last trade price, not at the true value
    assert rows.loc[0, "pnl_marked_at_last_trade"] == pytest.approx(0.0)
    assert rows.loc[1, "pnl_marked_at_last_trade"] == pytest.approx(0.8)
    assert rows["fill_pnl_at_true_value"].sum() == pytest.approx(result.summary["pnl"])


def test_quitting_aborts_the_game() -> None:
    with pytest.raises(GameAborted):
        run_game(_cfg(), 11, _reader(["99.6 100.4", "q"]), _console())
    with pytest.raises(GameAborted):  # input closed (Ctrl-D)
        run_game(_cfg(), 11, _reader(["99.6 100.4"]), _console())


def test_time_limit_pulls_the_quotes() -> None:
    """two_point_medium allows 20 s per quote. A fake clock makes the answer to round 2 take
    25 s: no quotes that round, no trade, and the timeout is counted."""
    cfg = _cfg("two_point_medium")
    assert cfg.play.time_limit_sec == 20.0
    times = iter([0.0, 1.0, 10.0, 35.0] + [100.0] * 200)
    result = run_game(cfg, 3, _reader(["99.6 100.4"] * 30), _console(), clock=lambda: next(times))
    assert result.summary["timeouts"] == 1
    assert np.isnan(result.episode.bids[1]) and np.isnan(result.episode.asks[1])
    assert not np.isnan(result.episode.bids[0]) and not np.isnan(result.episode.bids[2])
    assert all(f.t != 1 for f in result.episode.fills)
    assert result.summary["rounds_quoted"] == 29


def test_play_needs_a_two_point_scenario() -> None:
    with pytest.raises(ValueError, match="two_point"):
        run_game(_cfg("baseline"), 1, _reader([]), _console())


def test_games_are_saved_and_stats_plotted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = _workspace(tmp_path)
    cfg, h = load_config(config, "two_point_easy")
    assert main(["play-stats", "--config", str(config)]) == 0
    assert "No games yet" in capsys.readouterr().out

    for stamp, seed in (("20261109T230000Z", 11), ("20261109T230500Z", 12)):
        result = run_game(cfg, seed, _reader(["99.6 100.4"] * 20), _console())
        path = save_game(cfg, h, result, stamp)
        assert path == tmp_path / "play" / "games" / f"{stamp}.csv"
        assert len(pd.read_csv(path)) == 20
    history = load_history(cfg)
    assert history["seed"].tolist() == [11, 12]
    assert history["scenario"].tolist() == ["two_point_easy"] * 2
    assert history["config_hash"].tolist() == [h, h]

    assert main(["play-stats", "--config", str(config)]) == 0
    assert "2 games" in capsys.readouterr().out
    assert (tmp_path / "play" / "progress.png").stat().st_size > 0


def test_cli_play_saves_a_game(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = _workspace(tmp_path)
    monkeypatch.setattr(Console, "input", lambda self, prompt="": "99.5 100.5")
    args = ["play", "--config", str(config), "--scenario", "two_point_easy", "--seed", "5"]
    assert main(args) == 0
    (saved,) = (tmp_path / "play" / "games").iterdir()
    assert len(pd.read_csv(saved)) == 20
    history = pd.read_csv(tmp_path / "play" / "history.csv")
    assert history["seed"].tolist() == [5] and history["rounds_quoted"].tolist() == [20]

    monkeypatch.setattr(Console, "input", lambda self, prompt="": "q")
    assert main(args) == 0
    assert len(list((tmp_path / "play" / "games").iterdir())) == 1  # an aborted game is not saved
