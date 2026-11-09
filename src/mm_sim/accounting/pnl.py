"""Per-episode accounting: P&L, its decomposition, and inventory statistics.

For fill i with market-maker side d_i (+1 bought, -1 sold), price p_i, time t_i and horizon h
(t_i + h clipped to N), the identity

    d_i*(V_T - p_i) =  d_i*(V_{t_i} - p_i)          spread capture
                     + d_i*(V_{t_i+h} - V_{t_i})     short-term move (negative = adverse selection)
                     + d_i*(V_T - V_{t_i+h})         inventory / holding P&L

holds term by term, so  spread capture + adverse selection + inventory P&L - fees  equals the
mark-to-market P&L  cash + q_T * V_T  exactly (tested to 1e-9).
"""

from __future__ import annotations

import numpy as np

from mm_sim.config import Config
from mm_sim.engine.reference import BOUGHT, EpisodeResult
from mm_sim.flow.noise import fill_probability

# Columns of the per-episode table, in order.
METRICS = (
    "pnl_mtm",
    "pnl_liquidated",
    "spread_capture",
    "adverse_selection",
    "inventory_pnl",
    "fees",
    "buys",
    "sells",
    "volume",
    "max_abs_q",
    "mean_abs_q",
    "terminal_q",
    "share_at_limit",
    "noise_capture_expected",
)


def noise_capture_expected(cfg: Config, res: EpisodeResult) -> float:
    """Expected spread capture from noise flow given the quotes that actually stood:
    the sum over steps and sides of distance * p(distance). It ignores the inventory limit
    and informed flow, so it is the theory value only when neither matters."""
    c, dt = cfg.flow.noise, cfg.market.dt
    total = 0.0
    for t in range(cfg.market.n_steps):
        mid = float(res.values[t])
        for distance in (mid - float(res.bids[t]), float(res.asks[t]) - mid):
            if not np.isnan(distance):
                total += distance * fill_probability(distance, c.A, c.k, dt)
    return total


def episode_metrics(cfg: Config, res: EpisodeResult) -> dict[str, float]:
    n = cfg.market.n_steps
    h = cfg.accounting.markout_horizon_steps
    v_end = float(res.values[n])

    spread = adverse = holding = 0.0
    buys = sells = 0
    for f in res.fills:
        v_fill = float(res.values[f.t])
        v_later = float(res.values[min(f.t + h, n)])
        spread += f.side * f.size * (v_fill - f.price)
        adverse += f.side * f.size * (v_later - v_fill)
        holding += f.side * f.size * (v_end - v_later)
        if f.side == BOUGHT:
            buys += f.size
        else:
            sells += f.size

    q_end = int(res.inventory[n])
    pnl_mtm = res.cash + q_end * v_end
    eng = cfg.engine
    liquidation_cost = abs(q_end) * (eng.liq_half_spread + eng.liq_impact * abs(q_end))
    abs_q = np.abs(res.inventory[1:])  # inventory after each step
    return {
        "pnl_mtm": pnl_mtm,
        "pnl_liquidated": pnl_mtm - liquidation_cost,
        "spread_capture": spread,
        "adverse_selection": adverse,
        "inventory_pnl": holding,
        "fees": res.fees,
        "buys": float(buys),
        "sells": float(sells),
        "volume": float(buys + sells),
        "max_abs_q": float(abs_q.max()),
        "mean_abs_q": float(abs_q.mean()),
        "terminal_q": float(q_end),
        "share_at_limit": float((abs_q >= eng.q_max).mean()),
        "noise_capture_expected": noise_capture_expected(cfg, res),
    }
