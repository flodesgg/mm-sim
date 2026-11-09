# mm-sim — a market-making simulator lab

A small, readable simulator for learning market making by building it: a simulated asset, a
market maker that posts a bid and an ask, and simulated order flow from uninformed (noise)
traders and from informed traders who know where the price is going.

**Simulation only.** No exchange, no broker, no orders, no API keys, no real money. Every
conclusion in this repository is a conclusion about the model, not about real markets.

## Status

Stages A to C are done: a reference engine with noise and informed traders, jumps and
requote latency; fixed, skew, Avellaneda–Stoikov and Glosten–Milgrom strategies; exact P&L
accounting with markout curves; Monte Carlo with paired comparisons; four pre-registered
experiments.
See [STATUS.md](STATUS.md).

## Results so far (statements about the model)

| Experiment | Question | Result | File |
|---|---|---|---|
| EXP-001 | Fixed spread against noise traders only: does mean P&L follow the closed form, and where is the best half-spread? | CONFIRMED. Mean P&L within 2.1 standard errors of the formula at all 10 half-spreads (1000 episodes each, seed 101). Best grid point h = 0.7: mean 61.70, 95% CI [60.91, 62.49]; theory optimum 0.744, not 1/k = 0.667. | [report](reports/experiments/EXP-001/report.md), [pre-registration](experiments/EXP-001_fixed_spread_noise_only.md) |
| EXP-002 | How wide must a fixed spread be to break even as informed traders arrive more often? | CONFIRMED. Mean P&L within 3.1 standard errors of the formula in all 70 cells (1000 episodes each, seed 202). Simulated break-even half-spread rises from 0.064 (informed arrival probability 0.2 per step) to 0.396 (1.0 per step); predicted 0.071 to 0.433. Informed traders know the value 50 steps ahead, an invented number. | [report](reports/experiments/EXP-002/report.md), [pre-registration](experiments/EXP-002_spread_vs_informed_intensity.md) |
| EXP-003 | What does inventory management buy, against fixed quotes with the same average spread (paired on the same random numbers)? | CONFIRMED. Avellaneda–Stoikov with γ = 0.1 cuts the std of liquidated P&L to 0.417 of the benchmark's (95% CI [0.374, 0.464]; 1000 episodes, seed 303). Mark-to-market it costs about 5.7% of mean P&L; with the (invented) liquidation cost its mean is 1.40 higher [0.54, 2.26]. A simple skew does at least as well here. | [report](reports/experiments/EXP-003/report.md), [pre-registration](experiments/EXP-003_inventory_frontier.md) |
| EXP-004 | What do stale quotes cost when the price jumps? | CONFIRMED. Requoting every 5 steps instead of every step: mean P&L 54.70 [53.47, 55.93] against 61.30 [60.23, 62.38], with 5.66 pick-offs per episode losing 0.35 each; every 20 steps: 30.07 (1000 episodes, seed 404). Matches the closed form. | [report](reports/experiments/EXP-004/report.md), [pre-registration](experiments/EXP-004_latency_and_jumps.md) |
| EXP-005 | Do these conclusions survive other assumptions (σ doubled, k doubled, jumps)? | CONFIRMED. All six conclusions keep their sign with a CI excluding zero in all four variants; none is `fragile`. Sizes change a lot: doubling σ triples the loss of a narrow spread to informed flow. | [report](reports/experiments/EXP-005/report.md), [pre-registration](experiments/EXP-005_robustness.md) |

EXP-002 to EXP-005 were approved under delegation during an overnight run, not by Nick. The number of variants tried is the number of lines in `experiments/trial_log.csv`.

## Questions the lab will answer (with plots and confidence intervals)

1. How does the width of the quoted spread trade off fill rate against profit per fill?
2. How much does adverse selection cost, and how wide must the spread be to break even as the
   share of informed traders grows?
3. How does inventory management (quote skew, inventory limits, Avellaneda–Stoikov) change the
   mean and the risk of P&L?
4. How do stale quotes get picked off after price jumps?

## Rules of the lab

- Every number in this README and in `docs/` comes from a file produced by the code here.
- Experiments that compare strategies are written down in `experiments/EXP-NNN.md` and approved
  **before** they run; the code refuses to run an experiment whose config hash has changed.
- Every report starts with its limitations.
- Formulas from papers are derived and tested; anything not checked against the source is
  labelled `from memory, unverified` in [docs/model_notes.md](docs/model_notes.md).

## Use

```bash
uv sync                                        # Python 3.13 environment from the lockfile
make check                                     # ruff, mypy --strict, fast tests
uv run mm-sim check-config --scenario baseline # print the validated config and its hash
uv run mm-sim run --scenario baseline --strategy fixed --episodes 1000 --seed 1
                                               # -> reports/runs/<run_id>/report.md
uv run mm-sim experiment EXP-001               # runs only if approved and the config hash matches
uv run mm-sim reproduce EXP-001                # rebuild a finished experiment, verify its numbers
uv run mm-sim play --scenario two_point_easy   # quote against informed and noise traders yourself
uv run mm-sim play-stats                       # your progress over the saved games
```

## Layout

| Path | Content |
|---|---|
| `config.yaml`, `scenarios/` | all parameters; scenarios override the base config |
| `src/mm_sim/engine/reference.py` | the reference engine: one episode, step by step (start reading here) |
| `src/mm_sim/` | `market/`, `flow/`, `strategies/`, `accounting/`, `analysis/`, `reports/`, `cli` |
| `tests/` | pytest + hypothesis |
| `experiments/` | pre-registered experiments and the trial log |
| `reports/` | generated reports and figures |
| `docs/` | [model notes](docs/model_notes.md), [concepts](docs/concepts.md), [decisions](docs/decisions.md) |
