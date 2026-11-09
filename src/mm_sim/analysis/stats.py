"""Statistics across episodes. Episodes are independent, so a t-interval on the mean applies."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from numpy.typing import ArrayLike, NDArray
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


def paired_comparison(a: ArrayLike, b: ArrayLike, level: float) -> dict[str, float]:
    """Mean of the per-episode differences a - b for two strategies run on common random
    numbers, with its CI, next to the CI one would get by ignoring the pairing."""
    x, y = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    n = len(x)
    mean, lo, hi = mean_ci(x - y, level)
    unpaired_se = float(np.sqrt(x.var(ddof=1) / n + y.var(ddof=1) / n))
    unpaired_half = float(stats.t.ppf(0.5 + level / 2, 2 * n - 2)) * unpaired_se
    paired_half = (hi - lo) / 2
    return {
        "mean_diff": mean,
        "ci_low": lo,
        "ci_high": hi,
        "unpaired_ci_low": mean - unpaired_half,
        "unpaired_ci_high": mean + unpaired_half,
        "ci_width_ratio": paired_half / unpaired_half,  # < 1: pairing made the CI narrower
        "correlation": float(np.corrcoef(x, y)[0, 1]),
    }


def bootstrap_ci(
    statistic: Callable[[NDArray[np.int64]], float], n: int, level: float, seed: int, samples: int
) -> tuple[float, float]:
    """Percentile bootstrap over episodes. `statistic` receives resampled episode indices, so
    paired quantities (a ratio of two strategies' stds, say) keep their pairing."""
    rng = np.random.default_rng(seed)
    draws = np.array([statistic(rng.integers(0, n, n)) for _ in range(samples)])
    lo, hi = np.quantile(draws, [(1 - level) / 2, (1 + level) / 2])
    return float(lo), float(hi)
