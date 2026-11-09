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
    "mean_quoted_spread",
    "picked_off",
    "picked_off_edge",
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
    buys = sells = picked_off = 0
    picked_off_edge = 0.0
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
        # picked off: a stale quote filled on the wrong side of the current value
        if f.quote_age > 0 and f.side * (v_fill - f.price) < 0:
            picked_off += f.size
            picked_off_edge += f.side * f.size * (v_fill - f.price)

    q_end = int(res.inventory[n])
    pnl_mtm = res.cash + q_end * v_end
    eng = cfg.engine
    liquidation_cost = abs(q_end) * (eng.liq_half_spread + eng.liq_impact * abs(q_end))
    abs_q = np.abs(res.inventory[1:])  # inventory after each step
    two_sided = ~(np.isnan(res.bids) | np.isnan(res.asks))
    quoted_spread = float((res.asks - res.bids)[two_sided].mean()) if two_sided.any() else np.nan
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
        "mean_quoted_spread": quoted_spread,  # over steps with both sides quoted
        "picked_off": float(picked_off),
        "picked_off_edge": picked_off_edge,  # sum of the (negative) edges of those fills
    }


COUNTERPARTIES = ("noise", "informed")


def markout_columns(cfg: Config) -> list[str]:
    """Per-episode markout columns: fill counts and markout sums per counterparty and horizon."""
    cols = [f"fills_{c}" for c in COUNTERPARTIES]
    cols += [
        f"markout_{c}_{h}" for c in COUNTERPARTIES for h in cfg.accounting.markout_curve_horizons
    ]
    return cols


def markout_sums(cfg: Config, res: EpisodeResult) -> dict[str, float]:
    """For each counterparty and horizon h: the sum over its fills of d * (V_{t+h} - price),
    with t + h clipped to the end. Divided by the fill count this is the markout curve:
    at h = 0 it is the edge at the fill; it falls with h when the flow is informed."""
    n = cfg.market.n_steps
    out = dict.fromkeys(markout_columns(cfg), 0.0)
    for f in res.fills:
        out[f"fills_{f.counterparty}"] += f.size
        for h in cfg.accounting.markout_curve_horizons:
            later = float(res.values[min(f.t + h, n)])
            out[f"markout_{f.counterparty}_{h}"] += f.side * f.size * (later - f.price)
    return out
