from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from mm_sim.config import available_scenarios, config_hash, deep_merge, load_config

REPO = Path(__file__).resolve().parents[1]
REPO_CONFIG = REPO / "config.yaml"


def _raw() -> dict[str, Any]:
    with REPO_CONFIG.open() as f:
        data: dict[str, Any] = yaml.safe_load(f)
    return data


def _write(tmp_path: Path, raw: dict[str, Any], scenarios: dict[str, str] | None = None) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(raw))
    (tmp_path / "scenarios").mkdir(exist_ok=True)
    for name, text in (scenarios or {}).items():
        (tmp_path / "scenarios" / f"{name}.yaml").write_text(text)
    return p


def test_repo_config_is_valid() -> None:
    cfg, h = load_config(REPO_CONFIG)
    assert cfg.project.simulation_only is True
    assert cfg.market.process == "random_walk"
    assert cfg.market.horizon == pytest.approx(1.0)
    assert len(h) == 12
    assert h == cfg.model_hash()


@pytest.mark.parametrize("name", available_scenarios(REPO_CONFIG))
def test_every_repo_scenario_is_valid(name: str) -> None:
    cfg, _ = load_config(REPO_CONFIG, name)
    assert cfg.scenario.name == name


def test_baseline_scenario_exists() -> None:
    assert "baseline" in available_scenarios(REPO_CONFIG)


def test_simulation_only_false_is_rejected(tmp_path: Path) -> None:
    raw = _raw()
    raw["project"]["simulation_only"] = False
    with pytest.raises(ValidationError, match="simulation_only"):
        load_config(_write(tmp_path, raw))


def test_unknown_key_is_rejected(tmp_path: Path) -> None:
    raw = _raw()
    raw["market"]["sigmma"] = 1.0  # typo must not be silently ignored
    with pytest.raises(ValidationError):
        load_config(_write(tmp_path, raw))


def test_unquoted_yaml_boolean_gets_a_clear_error(tmp_path: Path) -> None:
    """`world: off` is parsed by YAML as False; the error must say to quote it."""
    text = REPO_CONFIG.read_text().replace('world: "public_mid"', "world: off")
    assert "world: off" in text
    p = tmp_path / "config.yaml"
    p.write_text(text)
    with pytest.raises(ValidationError, match=r"'world' got the boolean False.*quotes"):
        load_config(p)


def test_boolean_key_gets_a_clear_error(tmp_path: Path) -> None:
    """A bare `on:` key is parsed by YAML as the key True."""
    p = _write(tmp_path, _raw(), {"s": 'scenario: {name: "s", description: "d"}\non: 1\n'})
    with pytest.raises(ValidationError, match="not a string"):
        load_config(p, "s")


def test_informed_probability_above_one_rejected(tmp_path: Path) -> None:
    raw = _raw()
    raw["flow"]["informed"]["intensity"] = 1.01 / raw["market"]["dt"]
    with pytest.raises(ValidationError, match=r"informed\.intensity \* market\.dt"):
        load_config(_write(tmp_path, raw))


def test_jump_probability_above_one_rejected(tmp_path: Path) -> None:
    raw = _raw()
    raw["market"]["jump"]["intensity"] = 1.01 / raw["market"]["dt"]
    with pytest.raises(ValidationError, match=r"jump\.intensity"):
        load_config(_write(tmp_path, raw))


def test_two_point_needs_trades_only_world(tmp_path: Path) -> None:
    raw = _raw()
    raw["market"]["process"] = "two_point"
    with pytest.raises(ValidationError, match="go together"):
        load_config(_write(tmp_path, raw))
    raw["market"]["world"] = "trades_only"
    cfg, _ = load_config(_write(tmp_path, raw))
    assert cfg.market.world == "trades_only"


def test_two_point_values_must_be_ordered(tmp_path: Path) -> None:
    raw = _raw()
    raw["market"]["two_point"]["v_low"] = raw["market"]["two_point"]["v_high"]
    with pytest.raises(ValidationError, match="v_high must be above"):
        load_config(_write(tmp_path, raw))


def test_markout_horizons_must_increase(tmp_path: Path) -> None:
    raw = _raw()
    raw["accounting"]["markout_curve_horizons"] = [0, 5, 2]
    with pytest.raises(ValidationError, match="increasing"):
        load_config(_write(tmp_path, raw))


def test_config_is_frozen() -> None:
    cfg, _ = load_config(REPO_CONFIG)
    with pytest.raises(ValidationError):
        cfg.market.sigma = 3.0  # type: ignore[misc]


def test_deep_merge_overrides_leaves_and_keeps_siblings() -> None:
    base = {"a": {"x": 1, "y": 2}, "b": [1, 2]}
    assert deep_merge(base, {"a": {"y": 9}, "b": [3]}) == {"a": {"x": 1, "y": 9}, "b": [3]}
    assert base == {"a": {"x": 1, "y": 2}, "b": [1, 2]}  # the input is not modified


def test_scenario_overrides_base_and_changes_hash(tmp_path: Path) -> None:
    scenario = 'scenario: {name: "wide", description: "d"}\nmarket: {sigma: 5.0}\n'
    p = _write(tmp_path, _raw(), {"wide": scenario})
    base, h_base = load_config(p)
    wide, h_wide = load_config(p, "wide")
    assert (base.market.sigma, wide.market.sigma) == (2.0, 5.0)
    assert wide.market.dt == base.market.dt  # untouched sibling survives the merge
    assert h_base != h_wide


def test_scenario_name_must_match_file(tmp_path: Path) -> None:
    p = _write(tmp_path, _raw(), {"a": 'scenario: {name: "b", description: "d"}\n'})
    with pytest.raises(ValueError, match=r"must set scenario\.name"):
        load_config(p, "a")


def test_unknown_scenario_lists_available(tmp_path: Path) -> None:
    p = _write(tmp_path, _raw(), {"a": 'scenario: {name: "a", description: "d"}\n'})
    with pytest.raises(FileNotFoundError, match=r"available: \['a'\]"):
        load_config(p, "missing")


def test_hash_ignores_paths_logging_and_key_order(tmp_path: Path) -> None:
    raw = _raw()
    _, h0 = load_config(_write(tmp_path, raw))
    raw["logging"]["level"] = "DEBUG"
    raw["paths"]["logs"] = "elsewhere"
    reordered = dict(reversed(list(raw.items())))
    _, h1 = load_config(_write(tmp_path, reordered))
    assert h0 == h1
    assert config_hash({"a": 1, "b": 2}) == config_hash({"b": 2, "a": 1})


def test_hash_changes_with_a_model_parameter(tmp_path: Path) -> None:
    raw = _raw()
    _, h0 = load_config(_write(tmp_path, raw))
    raw["flow"]["noise"]["k"] = 1.6
    _, h1 = load_config(_write(tmp_path, raw))
    assert h0 != h1
