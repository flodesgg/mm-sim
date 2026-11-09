"""Closed-form predictions for the fixed-spread strategy against noise flow only.

Derivations: docs/model_notes.md, section 9. They assume a non-binding inventory limit, no
informed flow, no fees and requoting every step.
"""

from __future__ import annotations

import math

from scipy import integrate, optimize, stats

from mm_sim.config import Config
from mm_sim.flow.noise import fill_probability


def _normal_pdf(z: float) -> float:
    return math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)


def _normal_sf(z: float) -> float:
    """1 - Phi(z)."""
    return 0.5 * math.erfc(z / math.sqrt(2))


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


def fixed_mean_pnl_with_informed(cfg: Config, h: float) -> float:
    """Expected episode P&L of the fixed strategy with noise AND informed traders
    (docs/model_notes.md, section 10). Per step t and per side, with d = h + tick/2,
    pi = lambda_I * dt, s_t = sigma * sqrt(dt * min(h_I, N - t)) and z = (d + c_I) / s_t:

        informed loss  = pi * (s_t * phi(z) - d * Q(z))       E[(move - d); move > d + c_I]
        noise gain     = p(d) * (d * (1 - pi * Q(z)) + pi * s_t * phi(z))

    The noise gain has two parts. The side is free for noise only if no informed trader took
    it (factor 1 - pi*Q). And those are the steps without a large adverse move, so a noise
    fill is followed by a move that is favourable on average (the pi * s_t * phi(z) term).
    where Q = 1 - Phi. Assumes the inventory limit does not bind and requoting every step.
    """
    m, inf, c = cfg.market, cfg.flow.informed, cfg.flow.noise
    d = h + m.tick_size / 2
    pi = inf.intensity * m.dt
    p_noise = fill_probability(d, c.A, c.k, m.dt)
    total = 0.0
    for t in range(m.n_steps):
        s_t = m.sigma * math.sqrt(m.dt * min(inf.horizon_steps, m.n_steps - t))
        if pi > 0 and s_t > 0:
            z = (d + inf.threshold) / s_t
            q = _normal_sf(z)
            tail = s_t * _normal_pdf(z)  # E[move; move > d + c_I]
            loss = pi * (tail - d * q)
        else:
            q, loss, tail = 0.0, 0.0, 0.0
        total += 2 * (p_noise * (d * (1 - pi * q) + pi * tail) - loss)
    return total


def break_even_half_spread(cfg: Config, h_max: float = 5.0) -> float:
    """The smallest half-spread at which the expected P&L with informed flow is zero.
    0 when there are no informed traders; NaN if the P&L is negative up to h_max."""
    if cfg.flow.informed.intensity == 0:
        return 0.0
    tick = cfg.market.tick_size
    lo = 0.0
    if fixed_mean_pnl_with_informed(cfg, lo) >= 0:
        return 0.0
    h = tick
    while h <= h_max:
        if fixed_mean_pnl_with_informed(cfg, h) >= 0:
            return float(optimize.brentq(lambda x: fixed_mean_pnl_with_informed(cfg, x), lo, h))
        lo, h = h, h + tick * 5
    return float("nan")


def _stale_move_components(cfg: Config, lag: int) -> list[tuple[float, float, float]]:
    """Distribution of the value move over `lag` steps as a normal mixture:
    a list of (weight, mean shift, std). Diffusion gives N(0, sigma^2 * lag * dt); K jumps
    (Binomial(lag, lambda_J*dt)) add +-J each (fixed) or N(0, K*J^2) (normal)."""
    m = cfg.market
    diffusion_var = m.sigma**2 * lag * m.dt
    p_jump = m.jump.intensity * m.dt if m.process == "jump_diffusion" else 0.0
    components = []
    for k_jumps in range(lag + 1):
        w = float(stats.binom.pmf(k_jumps, lag, p_jump)) if lag > 0 else 1.0
        if w < 1e-14:
            continue
        if m.jump.size_dist == "normal":
            components.append((w, 0.0, math.sqrt(diffusion_var + k_jumps * m.jump.size**2)))
        else:
            for ups in range(k_jumps + 1):
                w_sign = float(stats.binom.pmf(ups, k_jumps, 0.5))
                shift = m.jump.size * (2 * ups - k_jumps)
                components.append((w * w_sign, shift, math.sqrt(diffusion_var)))
    return components


def _expect_over_move(cfg: Config, lag: int, f: object, kink: float | None = None) -> float:
    """E[f(D)] for the value move D over `lag` steps."""
    assert callable(f)
    total = 0.0
    for w, shift, std in _stale_move_components(cfg, lag):
        if std == 0:
            total += w * float(f(shift))
            continue
        points = None
        if kink is not None and abs((kink - shift) / std) < 8:
            points = [(kink - shift) / std]
        value, _ = integrate.quad(
            lambda z, shift=shift, std=std: f(shift + std * z) * _normal_pdf(z),
            -8,
            8,
            points=points,
            limit=200,
        )
        total += w * float(value)
    return total


def _lag_counts(cfg: Config) -> dict[int, int]:
    """How many of the N steps have quotes of each age (age = t % requote_every)."""
    every = cfg.engine.requote_every
    counts: dict[int, int] = {}
    for t in range(cfg.market.n_steps):
        counts[t % every] = counts.get(t % every, 0) + 1
    return counts


def latency_mean_pnl(cfg: Config, h: float) -> float:
    """Expected episode P&L of the fixed strategy against noise flow when it requotes only
    every `requote_every` steps (docs/model_notes.md, section 13). A quote of age j stands at
    distance d - D_j from the current mid on one side and d + D_j on the other, where D_j is
    the value move since it was posted; a fill at distance x earns x (which may be negative):

        E[P&L] = sum over steps of 2 * E[ g(d - D_age) ],   g(x) = x * p(x)
    """
    c, m = cfg.flow.noise, cfg.market
    d = h + m.tick_size / 2

    def g(move: float) -> float:
        return (d - move) * fill_probability(d - move, c.A, c.k, m.dt)

    return sum(2 * n * _expect_over_move(cfg, lag, g) for lag, n in _lag_counts(cfg).items())


def latency_pick_offs(cfg: Config, h: float) -> float:
    """Expected number of pick-offs per episode: fills on a stale quote (age > 0) that the
    value has moved through (D > d), two sides."""
    c, m = cfg.flow.noise, cfg.market
    d = h + m.tick_size / 2

    def hit(move: float) -> float:
        return fill_probability(d - move, c.A, c.k, m.dt) if move > d else 0.0

    return sum(
        2 * n * _expect_over_move(cfg, lag, hit, kink=d)
        for lag, n in _lag_counts(cfg).items()
        if lag > 0
    )
