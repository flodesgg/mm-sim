"""Timing of the two engines on the same work, with a check that they agree."""

from __future__ import annotations

import time

from mm_sim.analysis.montecarlo import run_monte_carlo
from mm_sim.config import Config
from mm_sim.engine.fast import run_monte_carlo_fast
from mm_sim.strategies.base import build_strategy


def benchmark_pair(cfg: Config, strategy: str, repeats: int) -> dict[str, float]:
    """Best-of-`repeats` wall time of each engine for analysis.episodes episodes, in simulated
    steps per second, and the largest difference between their per-episode tables."""
    built, _ = build_strategy(cfg, strategy)
    steps = cfg.analysis.episodes * cfg.market.n_steps
    best = {"reference": float("inf"), "fast": float("inf")}
    tables = {}
    for _ in range(repeats):
        start = time.perf_counter()
        tables["reference"] = run_monte_carlo(cfg, built)
        best["reference"] = min(best["reference"], time.perf_counter() - start)
        start = time.perf_counter()
        tables["fast"] = run_monte_carlo_fast(cfg, strategy)
        best["fast"] = min(best["fast"], time.perf_counter() - start)
    diff = (tables["reference"] - tables["fast"]).abs().max().max()
    return {
        "steps": float(steps),
        "reference_steps_per_sec": steps / best["reference"],
        "fast_steps_per_sec": steps / best["fast"],
        "speedup": best["reference"] / best["fast"],
        "max_abs_difference": float(diff),
    }
