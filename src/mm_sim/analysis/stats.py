"""Statistics across episodes. Episodes are independent, so a t-interval on the mean applies."""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike
from scipy import special, stats


def mean_ci(x: ArrayLike, level: float) -> tuple[float, float, float]:
    """Mean and its two-sided confidence interval (Student t)."""
    a = np.asarray(x, dtype=float)
    mean = float(a.mean())
    if len(a) < 2:
        return mean, float("nan"), float("nan")
    se = float(a.std(ddof=1)) / float(np.sqrt(len(a)))
    half = float(stats.t.ppf(0.5 + level / 2, len(a) - 1)) * se
    return mean, mean - half, mean + half


def certainty_equivalent(x: ArrayLike, gamma: float) -> float:
    """CARA certainty equivalent CE = -(1/gamma) * ln E[exp(-gamma * X)], via log-sum-exp."""
    a = np.asarray(x, dtype=float)
    return float(-(special.logsumexp(-gamma * a) - np.log(len(a))) / gamma)


def summarize(x: ArrayLike, level: float, cara_gamma: float) -> dict[str, float]:
    """Summary of a per-episode P&L sample."""
    a = np.asarray(x, dtype=float)
    mean, lo, hi = mean_ci(a, level)
    std = float(a.std(ddof=1)) if len(a) > 1 else float("nan")
    q05 = float(np.quantile(a, 0.05))
    return {
        "n": float(len(a)),
        "mean": mean,
        "ci_low": lo,
        "ci_high": hi,
        "std": std,
        "sharpe_per_episode": mean / std if std and std > 0 else float("nan"),  # not annualised
        "q05": q05,
        "es05": float(a[a <= q05].mean()),  # expected shortfall: mean of the worst 5%
        "p_loss": float((a < 0).mean()),
        "certainty_equivalent": certainty_equivalent(a, cara_gamma),
    }
