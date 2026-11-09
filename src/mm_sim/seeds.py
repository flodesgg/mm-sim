"""Random streams. One root seed per run; every (episode, component) pair gets its own stream.

A stream depends only on (root seed, episode index, component name), never on which episodes
ran before or on how many ran in parallel. Two strategies run on the same root seed therefore
see the same value path and the same arriving traders (common random numbers).
"""

from __future__ import annotations

import numpy as np

# Fixed positions: adding a component appends to this tuple and never renumbers the others.
COMPONENTS = ("value", "noise_fills", "informed_arrivals", "trader_types", "jumps")


def component_rng(root_seed: int, episode: int, component: str) -> np.random.Generator:
    """The generator for one random component of one episode."""
    key = (episode, COMPONENTS.index(component))
    return np.random.default_rng(np.random.SeedSequence(root_seed, spawn_key=key))
