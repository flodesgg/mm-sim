"""True-value processes. Each returns the whole path V_0 .. V_N (length N + 1) for one episode."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from mm_sim.config import MarketConfig


def random_walk_path(cfg: MarketConfig, rng: np.random.Generator) -> NDArray[np.float64]:
    """V_{t+1} = V_t + sigma * sqrt(dt) * Z with Z ~ N(0, 1), starting at s0."""
    steps = cfg.sigma * np.sqrt(cfg.dt) * rng.standard_normal(cfg.n_steps)
    path = np.empty(cfg.n_steps + 1)
    path[0] = cfg.s0
    path[1:] = cfg.s0 + np.cumsum(steps)
    return path


def two_point_path(cfg: MarketConfig, rng: np.random.Generator) -> NDArray[np.float64]:
    """V is drawn once (v_high with probability p_high, else v_low) and never moves."""
    tp = cfg.two_point
    v = tp.v_high if rng.random() < tp.p_high else tp.v_low
    return np.full(cfg.n_steps + 1, v)


def value_path(cfg: MarketConfig, rng: np.random.Generator) -> NDArray[np.float64]:
    if cfg.process == "random_walk":
        return random_walk_path(cfg, rng)
    if cfg.process == "two_point":
        return two_point_path(cfg, rng)
    raise NotImplementedError(f"value process {cfg.process!r} is not implemented yet")
