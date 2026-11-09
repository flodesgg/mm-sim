"""What the engine needs from an order flow."""

from __future__ import annotations

from typing import Protocol


class Flow(Protocol):
    """A group of traders that may trade against the market maker's quotes in a step."""

    counterparty: str  # recorded on every fill; the strategy never sees it

    def act(self, t: int, bid: float | None, ask: float | None) -> tuple[bool, bool]:
        """Return (bid is hit, ask is lifted) for step t. A side that is None cannot trade."""
        ...
