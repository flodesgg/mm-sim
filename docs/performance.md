# Performance

Measured with `uv run mm-sim benchmark` (`make benchmark`) on this machine. Source of every
number below: `reports/benchmark/benchmark.csv` and `reports/benchmark/benchmark.json`
(run id `20261109T221439Z-5bf9ee`, commit `47b3d702865b`).

Machine: Apple Silicon (`arm64`), macOS (Darwin 27.2.0), Python 3.13.15, numpy 2.5.4.
Workload: 1000 episodes × 200 steps = 200,000 simulated steps per row, best of 3 repeats,
single process.

| scenario | strategy | reference engine, steps/s | fast engine, steps/s | speed-up |
|---|---|---|---|---|
| baseline | fixed | 153,621 | 3,049,108 | 19.8× |
| baseline | skew | 122,213 | 3,481,235 | 28.5× |
| baseline | avellaneda_stoikov | 152,457 | 3,531,063 | 23.2× |
| inventory | fixed | 159,414 | 3,586,243 | 22.5× |
| inventory | skew | 157,719 | 3,558,492 | 22.6× |
| inventory | avellaneda_stoikov | 151,681 | 3,549,388 | 23.4× |
| jumpy | fixed | 247,860 | 3,255,915 | 13.1× |
| jumpy | skew | 216,441 | 3,229,046 | 14.9× |
| jumpy | avellaneda_stoikov | 213,463 | 3,049,183 | 14.3× |
| toxic | fixed | 128,259 | 2,284,298 | 17.8× |
| toxic | skew | 141,038 | 2,325,464 | 16.5× |
| toxic | avellaneda_stoikov | 142,019 | 2,377,504 | 16.7× |

In every row the two engines' per-episode tables are equal (the benchmark's
`max_abs_difference` column is 0 when printed to six significant digits; the tests require
all fill counts to be exactly equal and all floats to agree to 1e-9).

## What the two engines are

- **Reference engine** (`src/mm_sim/engine/reference.py`): one episode at a time, one step at
  a time, plain Python. It is the specification: the order of events is pinned by a
  hand-computed test, and every experiment in this repository ran on it.
- **Fast engine** (`src/mm_sim/engine/fast.py`): one Python loop over the 200 steps, each
  operation applied to all episodes at once with numpy. It draws every episode's random
  numbers from the same streams as the reference engine, so the same seed gives the same
  fills.

## What the fast engine does not cover

The two-point world (Glosten–Milgrom, `fixed_prior`, play mode) and the kill switch.
`fast.supports` returns False for those and `mm-sim run --engine fast` refuses them. The
strategies' quote formulas are written a second time inside the fast engine; the equality
tests (`tests/test_fast_engine.py`, including random configurations with binding inventory
limits, fees, latency, informed flow and jumps) are what keeps the two from drifting apart.

## Where the time goes

Reference engine: the Python step loop and the per-step `Observation`. Fast engine: mostly
creating the per-episode random generators (three or four per episode) and stacking their
draws; the vectorised step loop itself is a small part. A larger speed-up would need the
random draws generated in bulk, which would break the property that an episode's numbers do
not depend on which other episodes run.

These numbers are for this laptop on one day; they are not a general claim.
