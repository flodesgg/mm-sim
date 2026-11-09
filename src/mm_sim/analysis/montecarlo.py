"""Monte Carlo runner: many independent episodes of one strategy -> one row per episode."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from mm_sim.accounting.pnl import METRICS, episode_metrics, markout_columns, markout_sums
from mm_sim.config import AnalysisConfig, Config
from mm_sim.engine.reference import simulate_episode
from mm_sim.strategies.base import Strategy


def with_run_settings(cfg: Config, seed: int | None, episodes: int | None) -> Config:
    """The config with the run's root seed and episode count (command-line overrides)."""
    a = cfg.analysis
    new = AnalysisConfig(
        episodes=a.episodes if episodes is None else episodes,
        seed=a.seed if seed is None else seed,
        ci_level=a.ci_level,
        cara_gamma=a.cara_gamma,
        bootstrap_samples=a.bootstrap_samples,
    )
    return cfg.model_copy(update={"analysis": new})


def run_monte_carlo(
    cfg: Config, strategy: Strategy, episodes: Iterable[int] | None = None
) -> pd.DataFrame:
    """Run the episodes (default 0 .. analysis.episodes - 1) and return their metrics,
    indexed by episode number. A row depends only on (seed, episode), not on the order."""
    order = list(range(cfg.analysis.episodes) if episodes is None else episodes)
    rows = []
    for e in order:
        res = simulate_episode(cfg, strategy, e)
        rows.append({**episode_metrics(cfg, res), **markout_sums(cfg, res)})
    columns = [*METRICS, *markout_columns(cfg)]
    return pd.DataFrame(rows, index=pd.Index(order, name="episode"), columns=columns)
