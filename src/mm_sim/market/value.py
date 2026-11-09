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


def jump_increments(cfg: MarketConfig, rng: np.random.Generator) -> NDArray[np.float64]:
    """The jump added to each of the N value moves: with probability lambda_J * dt a jump of
    +-J (sign 50/50) or N(0, J^2), otherwise 0. Element t is the jump in the move V_t -> V_{t+1}."""
    j = cfg.jump
    happens = rng.random(cfg.n_steps) < j.intensity * cfg.dt
    if j.size_dist == "fixed":
        sizes = np.where(rng.random(cfg.n_steps) < 0.5, j.size, -j.size)
    else:
        sizes = j.size * rng.standard_normal(cfg.n_steps)
    return np.where(happens, sizes, 0.0)


def jump_diffusion_path(
    cfg: MarketConfig, rng: np.random.Generator, jump_rng: np.random.Generator
) -> NDArray[np.float64]:
    """The random walk plus jumps. The diffusion part uses the same stream as `random_walk`,
    so a jump scenario and its no-jump twin share the diffusion path."""
    path = random_walk_path(cfg, rng)
    path[1:] += np.cumsum(jump_increments(cfg, jump_rng))
    return path


def value_path(
    cfg: MarketConfig, rng: np.random.Generator, jump_rng: np.random.Generator | None = None
) -> NDArray[np.float64]:
    if cfg.process == "random_walk":
        return random_walk_path(cfg, rng)
    if cfg.process == "two_point":
        return two_point_path(cfg, rng)
    if cfg.process == "jump_diffusion":
        if jump_rng is None:
            raise ValueError("jump_diffusion needs the jump stream")
        return jump_diffusion_path(cfg, rng, jump_rng)
    raise NotImplementedError(f"value process {cfg.process!r} is not implemented yet")
