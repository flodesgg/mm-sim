"""Markout curves: the average d * (V_{t+h} - price) per fill, by counterparty and horizon.

The average is over all fills of all episodes (sum of markouts / number of fills). Its
confidence interval treats episodes, not fills, as the independent units (fills inside one
episode share the same value path): the standard ratio-estimator formula.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from mm_sim.accounting.pnl import COUNTERPARTIES
from mm_sim.config import Config


def ratio_ci(sums: pd.Series, counts: pd.Series, level: float) -> tuple[float, float, float]:
    """R = sum(sums) / sum(counts) with a CI from the episode-level residuals sums - R*counts."""
    total = float(counts.sum())
    if total == 0:
        return float("nan"), float("nan"), float("nan")
    ratio = float(sums.sum()) / total
    n = len(sums)
    resid = sums.to_numpy(dtype=float) - ratio * counts.to_numpy(dtype=float)
    se = float(resid.std(ddof=1)) / (np.sqrt(n) * float(counts.mean())) if n > 1 else float("nan")
    half = float(stats.t.ppf(0.5 + level / 2, n - 1)) * se if n > 1 else float("nan")
    return ratio, ratio - half, ratio + half


def markout_curve(cfg: Config, episodes: pd.DataFrame) -> pd.DataFrame:
    """One row per (counterparty, horizon): mean markout per fill, its CI, number of fills."""
    rows = []
    for c in COUNTERPARTIES:
        counts = episodes[f"fills_{c}"]
        for h in cfg.accounting.markout_curve_horizons:
            mean, lo, hi = ratio_ci(episodes[f"markout_{c}_{h}"], counts, cfg.analysis.ci_level)
            rows.append(
                {
                    "counterparty": c,
                    "horizon": h,
                    "markout": mean,
                    "ci_low": lo,
                    "ci_high": hi,
                    "fills": int(counts.sum()),
                }
            )
    return pd.DataFrame(rows)
