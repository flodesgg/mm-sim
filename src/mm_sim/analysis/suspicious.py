"""SUSPICIOUS checks: results that most likely mean a bug. Look for the bug before believing
the result.

  1. the P&L decomposition does not add up;
  2. the fixed strategy earns money below the theoretical break-even half-spread;
  3. a Glosten-Milgrom market maker whose mean profit is clearly not zero;
  4. a real strategy that beats the `clairvoyant` control, which cheats by seeing the future.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from mm_sim.analysis import theory
from mm_sim.analysis.montecarlo import run_monte_carlo
from mm_sim.analysis.stats import mean_ci, paired_comparison
from mm_sim.config import Config
from mm_sim.reports.sections import IDENTITY_TOLERANCE, decomposition_error
from mm_sim.strategies.clairvoyant import Clairvoyant

BREAK_EVEN_MARGIN = 0.05  # same margin as EXP-002
GM_Z_LIMIT = 4.0  # |mean| / standard error above this is not chance
CLAIRVOYANT_EPISODES = 200


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool  # False = SUSPICIOUS
    detail: str


def check_decomposition(episodes: pd.DataFrame) -> Check:
    err = decomposition_error(episodes)
    return Check("P&L decomposition adds up", err <= IDENTITY_TOLERANCE, f"largest error {err:.2e}")


def check_break_even(
    cfg: Config, strategy: str, params: dict[str, object], episodes: pd.DataFrame
) -> Check | None:
    """Applies to `fixed` with informed flow and no latency (where the closed form holds)."""
    if strategy != "fixed" or cfg.flow.informed.intensity == 0 or cfg.engine.requote_every != 1:
        return None
    h = float(params["half_spread"])  # type: ignore[arg-type]
    be = theory.break_even_half_spread(cfg)
    _, lo, _ = mean_ci(episodes["pnl_mtm"], cfg.analysis.ci_level)
    below = h < be - BREAK_EVEN_MARGIN
    return Check(
        "no profit below the break-even half-spread",
        not (below and lo > 0),
        f"half-spread {h:g}, theoretical break-even {be:.3f}, lower end of the P&L CI {lo:.3f}",
    )


def check_glosten_milgrom(strategy: str, episodes: pd.DataFrame) -> Check | None:
    if strategy != "glosten_milgrom":
        return None
    pnl = episodes["pnl_mtm"]
    se = float(pnl.std(ddof=1)) / float(np.sqrt(len(pnl)))
    z = float(pnl.mean()) / se if se > 0 else 0.0
    return Check(
        "Glosten-Milgrom mean profit is zero",
        abs(z) <= GM_Z_LIMIT,
        f"mean {float(pnl.mean()):.4f}, {z:.2f} standard errors from zero (limit {GM_Z_LIMIT:g})",
    )


def check_clairvoyant(cfg: Config, episodes: pd.DataFrame) -> Check:
    """Run the cheating control on the first episodes of the same seed, quoting the same
    average half-spread, and compare mark-to-market P&L episode by episode."""
    n = min(len(episodes), CLAIRVOYANT_EPISODES)
    half = float(episodes["mean_quoted_spread"].mean()) / 2
    lookahead = max(10, cfg.flow.informed.horizon_steps)
    cheat = run_monte_carlo(cfg, Clairvoyant(half, lookahead), range(n))["pnl_mtm"]
    real = episodes["pnl_mtm"].iloc[:n]
    diff = paired_comparison(real.to_numpy(), cheat.to_numpy(), cfg.analysis.ci_level)
    return Check(
        "the strategy does not beat the clairvoyant control",
        not diff["ci_low"] > 0,
        f"strategy minus clairvoyant over {n} episodes: {diff['mean_diff']:.2f} "
        f"[{diff['ci_low']:.2f}, {diff['ci_high']:.2f}] (clairvoyant mean "
        f"{float(cheat.mean()):.2f}; a control that sees the future, not a strategy)",
    )


def run_checks(
    cfg: Config, strategy: str, params: dict[str, object], episodes: pd.DataFrame
) -> list[Check]:
    checks = [
        check_decomposition(episodes),
        check_break_even(cfg, strategy, params, episodes),
        check_glosten_milgrom(strategy, episodes),
        check_clairvoyant(cfg, episodes),
    ]
    return [c for c in checks if c is not None]
