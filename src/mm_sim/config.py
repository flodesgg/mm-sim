"""Load and validate config.yaml, optionally overridden by a named scenario.

All parameters live in config.yaml and scenarios/*.yaml; code reads them only through
`load_config`. Unknown keys are rejected so a typo cannot silently fall back to a default.
The symbols follow docs/model_notes.md.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DEFAULT_CONFIG_PATH = Path("config.yaml")
SCENARIO_DIR = "scenarios"  # next to the base config file

_YAML_BOOL_HINT = "YAML reads bare yes/no/on/off/true/false as booleans; put the value in quotes"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="before")
    @classmethod
    def _no_accidental_yaml_booleans(cls, data: Any) -> Any:
        """`world: off` would arrive here as False. Fail with a message that says why."""
        if not isinstance(data, dict):
            return data
        for key, value in data.items():
            if not isinstance(key, str):
                raise ValueError(f"key {key!r} is not a string. {_YAML_BOOL_HINT}")
            field = cls.model_fields.get(key)
            if isinstance(value, bool) and field is not None and field.annotation is not bool:
                raise ValueError(f"'{key}' got the boolean {value}. {_YAML_BOOL_HINT}")
        return data


class ProjectConfig(_Strict):
    name: str
    simulation_only: bool

    @field_validator("simulation_only")
    @classmethod
    def _must_be_simulation(cls, v: bool) -> bool:
        if not v:
            raise ValueError("simulation_only must be true: this lab never touches a real market")
        return v


class ScenarioInfo(_Strict):
    name: str = Field(pattern=r"^[a-z0-9_]+$")
    description: str


class PathsConfig(_Strict):
    reports: Path
    experiments: Path
    logs: Path
    play: Path


class LoggingConfig(_Strict):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    file: str = "mm_sim.log"
    max_bytes: int = Field(gt=0)
    backup_count: int = Field(ge=0)


class JumpConfig(_Strict):
    """Used only by the jump_diffusion process: a jump with probability intensity*dt per step."""

    intensity: float = Field(ge=0)  # lambda_J, jumps per unit of time
    size: float = Field(ge=0)  # J: the jump is +-J ("fixed") or N(0, J^2) ("normal")
    size_dist: Literal["fixed", "normal"]


class TwoPointConfig(_Strict):
    """Used only by the two_point process: V = v_high with probability p_high, else v_low."""

    v_high: float
    v_low: float
    p_high: float = Field(gt=0, lt=1)

    @model_validator(mode="after")
    def _ordered(self) -> TwoPointConfig:
        if self.v_high <= self.v_low:
            raise ValueError("two_point.v_high must be above two_point.v_low")
        return self


class MarketConfig(_Strict):
    process: Literal["random_walk", "jump_diffusion", "two_point"]
    world: Literal["public_mid", "trades_only"]  # what the market maker observes
    s0: float = Field(gt=0)  # initial value V_0
    sigma: float = Field(ge=0)  # volatility per sqrt(unit of time)
    dt: float = Field(gt=0)  # length of one step
    n_steps: int = Field(ge=1)  # N; the horizon is T = N*dt
    tick_size: float = Field(gt=0)
    jump: JumpConfig
    two_point: TwoPointConfig

    @property
    def horizon(self) -> float:
        return self.n_steps * self.dt

    @model_validator(mode="after")
    def _consistent(self) -> MarketConfig:
        if self.jump.intensity * self.dt > 1:
            raise ValueError("market.jump.intensity * market.dt must be <= 1 (a probability)")
        if (self.process == "two_point") != (self.world == "trades_only"):
            raise ValueError(
                "market.process 'two_point' and market.world 'trades_only' go together: "
                "the other processes need the public mid"
            )
        return self


class NoiseFlowConfig(_Strict):
    """A side at distance d from the mid fills with probability 1 - exp(-A*exp(-k*d)*dt)."""

    A: float = Field(ge=0)
    k: float = Field(gt=0)


class InformedFlowConfig(_Strict):
    intensity: float = Field(ge=0)  # lambda_I, arrivals per unit of time
    horizon_steps: int = Field(ge=1)  # the informed trader knows V at t + horizon_steps
    threshold: float = Field(ge=0)  # c_I: minimum edge before it trades


class GlostenMilgromFlowConfig(_Strict):
    mu: float = Field(ge=0, le=1)  # probability that the arriving trader is informed


class FlowConfig(_Strict):
    noise: NoiseFlowConfig
    informed: InformedFlowConfig
    glosten_milgrom: GlostenMilgromFlowConfig


class EngineConfig(_Strict):
    requote_every: int = Field(ge=1)  # the strategy requotes every this many steps (latency)
    q_max: int = Field(ge=1)  # inventory limit in lots, enforced by the engine
    maker_fee: float  # per lot; negative = rebate
    kill_switch_loss: float | None = Field(gt=0)  # stop quoting below -loss; null = no switch
    liq_half_spread: float = Field(ge=0)  # cost per lot of closing the final inventory
    liq_impact: float = Field(ge=0)  # extra cost per lot, per lot of final inventory


class AccountingConfig(_Strict):
    markout_horizon_steps: int = Field(ge=1)  # h in the P&L decomposition
    markout_curve_horizons: list[int] = Field(min_length=1)

    @field_validator("markout_curve_horizons")
    @classmethod
    def _sorted_unique(cls, v: list[int]) -> list[int]:
        if any(h < 0 for h in v) or sorted(set(v)) != v:
            raise ValueError("markout_curve_horizons must be non-negative, increasing, unique")
        return v


class AnalysisConfig(_Strict):
    episodes: int = Field(ge=1)
    seed: int = Field(ge=0)  # root seed; every episode and component gets a spawned stream
    ci_level: float = Field(gt=0.5, lt=1)
    cara_gamma: float = Field(gt=0)  # risk aversion in the certainty equivalent


# Sections that change simulation results. Paths and logging do not.
MODEL_SECTIONS = ("market", "flow", "engine", "accounting", "strategies", "analysis")


class Config(_Strict):
    project: ProjectConfig
    scenario: ScenarioInfo
    paths: PathsConfig
    logging: LoggingConfig
    market: MarketConfig
    flow: FlowConfig
    engine: EngineConfig
    accounting: AccountingConfig
    # strategy name -> parameters; each strategy validates its own block (strategies/ registry)
    strategies: dict[str, dict[str, object]]
    analysis: AnalysisConfig

    @model_validator(mode="after")
    def _cross_checks(self) -> Config:
        if self.flow.informed.intensity * self.market.dt > 1:
            raise ValueError("flow.informed.intensity * market.dt must be <= 1 (a probability)")
        return self

    def model_hash(self) -> str:
        """Hash of everything that changes simulation results. Every output carries it, and a
        pre-registered experiment pins it: a run with a different value is refused."""
        dumped = self.model_dump(mode="json")
        return config_hash({k: dumped[k] for k in MODEL_SECTIONS})


def config_hash(raw: dict[str, object]) -> str:
    """Stable short hash of a config mapping (key order independent)."""
    canonical = json.dumps(raw, sort_keys=True, default=str).encode()
    return hashlib.sha256(canonical).hexdigest()[:12]


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """`override` wins; nested mappings are merged key by key, everything else is replaced."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_mapping(path: Path) -> dict[str, Any]:
    with path.open() as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: top level must be a mapping")
    return raw


def scenario_path(config_path: Path, scenario: str) -> Path:
    return config_path.parent / SCENARIO_DIR / f"{scenario}.yaml"


def available_scenarios(config_path: Path | str = DEFAULT_CONFIG_PATH) -> list[str]:
    return sorted(p.stem for p in (Path(config_path).parent / SCENARIO_DIR).glob("*.yaml"))


def load_config(
    path: Path | str = DEFAULT_CONFIG_PATH, scenario: str | None = None
) -> tuple[Config, str]:
    """Read the base config, apply the scenario's overrides, validate, and hash.

    Returns the config and its model hash. Raises on any invalid value.
    """
    p = Path(path)
    raw = _read_mapping(p)
    if scenario is not None:
        sp = scenario_path(p, scenario)
        if not sp.is_file():
            raise FileNotFoundError(
                f"unknown scenario {scenario!r}; available: {available_scenarios(p)}"
            )
        raw = deep_merge(raw, _read_mapping(sp))
    cfg = Config.model_validate(raw)
    if scenario is not None and cfg.scenario.name != scenario:
        raise ValueError(
            f"{scenario}.yaml must set scenario.name to {scenario!r}, got {cfg.scenario.name!r}"
        )
    return cfg, cfg.model_hash()
