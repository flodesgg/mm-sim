from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from mm_sim.config import Config, deep_merge

REPO = Path(__file__).resolve().parents[1]


def make_cfg(**overrides: Any) -> Config:
    """The repo's base config with nested overrides, e.g. make_cfg(market={"sigma": 0.0})."""
    with (REPO / "config.yaml").open() as f:
        raw: dict[str, Any] = yaml.safe_load(f)
    return Config.model_validate(deep_merge(raw, overrides))
