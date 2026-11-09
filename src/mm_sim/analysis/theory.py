"""Closed-form predictions for the fixed-spread strategy against noise flow only.

Derivations: docs/model_notes.md, section 9. They assume a non-binding inventory limit, no
informed flow, no fees and requoting every step.
"""

from __future__ import annotations

import math

from scipy import integrate, optimize

from mm_sim.config import Config
from mm_sim.flow.noise import fill_probability


def _average_over_tick(f: object, h: float, tick: float) -> float:
    """E[f(h + U)] with U uniform on [0, tick): outward rounding from a continuous mid puts
    each quote between h and h + tick away from it. tick = 0 gives f(h)."""
    assert callable(f)
    if tick == 0:
        return float(f(h))
    value, _ = integrate.quad(f, h, h + tick)
    return float(value) / tick


def fill_probability_per_side(cfg: Config, h: float, tick: float | None = None) -> float:
    c, dt = cfg.flow.noise, cfg.market.dt
    tick = cfg.market.tick_size if tick is None else tick
    return _average_over_tick(lambda d: fill_probability(d, c.A, c.k, dt), h, tick)


def fixed_noise_mean_pnl(cfg: Config, h: float, tick: float | None = None) -> float:
    """Expected episode P&L: N steps, two sides, each earning distance * p(distance).
    With tick = 0 this is N * 2 * h * (1 - exp(-A * exp(-k*h) * dt))."""
    c, dt = cfg.flow.noise, cfg.market.dt
    tick = cfg.market.tick_size if tick is None else tick
    per_side = _average_over_tick(lambda d: d * fill_probability(d, c.A, c.k, dt), h, tick)
    return 2 * cfg.market.n_steps * per_side


def fixed_noise_pnl_std(cfg: Config, h: float) -> float:
    """Std of episode P&L = sqrt(Var(spread capture) + Var(P&L of carried inventory)).

    With p the per-side fill probability and d = h + tick/2 the typical quote distance:
      Var(spread capture)    = N * 2 * d^2 * p * (1 - p)
      Var(inventory P&L)     = sigma^2 * dt * 2 * p * (1 - p) * N * (N + 1) / 2
    The two parts are uncorrelated because value moves are independent of the fills.
    """
    m = cfg.market
    n, d = m.n_steps, h + m.tick_size / 2
    p = fill_probability_per_side(cfg, h)
    var_spread = n * 2 * d * d * p * (1 - p)
    var_inventory = m.sigma**2 * m.dt * 2 * p * (1 - p) * n * (n + 1) / 2
    return math.sqrt(var_spread + var_inventory)


def optimal_fixed_half_spread(cfg: Config, tick: float = 0.0) -> float:
    """The half-spread that maximises the expected P&L (close to 1/k when A*dt is small)."""
    k = cfg.flow.noise.k
    res = optimize.minimize_scalar(
        lambda h: -fixed_noise_mean_pnl(cfg, h, tick), bounds=(1e-6, 20 / k), method="bounded"
    )
    return float(res.x)
