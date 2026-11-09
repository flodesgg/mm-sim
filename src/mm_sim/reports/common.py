"""Pieces shared by every report: the limitations block and small formatting helpers."""

from __future__ import annotations

from mm_sim.runinfo import RunInfo

LIMITATIONS = """\
## Limitations (read first)

Everything below is a statement about a **model**, not about real markets.

- Fill probability is an assumed exponential function of the quote's distance from the mid.
- Orders are one lot. There is no order book, no queue position and no competing market maker.
- The market maker sees the true value as a public mid price (in the `public_mid` world).
- Strategies that use the volatility `sigma` or the flow parameter `k` are given the true values.
- Informed traders' horizon and threshold are invented parameters, not calibrated to data.
- No hedging, no correlated instruments. Latency exists only through `requote_every`.
- Parameters are not calibrated to any market; P&L units are arbitrary.
"""


def setup_lines(info: RunInfo, seed: int, episodes: int, trials: int) -> str:
    dirty = " (uncommitted changes)" if info.git_dirty else ""
    return (
        f"- scenario: `{info.scenario}`, config hash `{info.config_hash}`\n"
        f"- run id `{info.run_id}`, git commit `{info.git_commit}`{dirty}\n"
        f"- root seed {seed}, {episodes} episodes\n"
        f"- variants tried so far in this repository (lines in `experiments/trial_log.csv`): "
        f"{trials}\n"
    )


def fmt(x: float, digits: int = 3) -> str:
    return f"{x:.{digits}f}"
