# mm-sim — a market-making simulator lab

A small, readable simulator for learning market making by building it: a simulated asset, a
market maker that posts a bid and an ask, and simulated order flow from uninformed (noise)
traders and from informed traders who know where the price is going.

**Simulation only.** No exchange, no broker, no orders, no API keys, no real money. Every
conclusion in this repository is a conclusion about the model, not about real markets.

## Status

Stage 0 (skeleton) is done: configuration, run metadata, logging and the quality gate. There
is no simulator yet and therefore **no results**. See [STATUS.md](STATUS.md) for the roadmap.

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
```

## Layout

| Path | Content |
|---|---|
| `config.yaml`, `scenarios/` | all parameters; scenarios override the base config |
| `src/mm_sim/` | `config`, `runinfo`, `logging_setup`, `cli`; model packages are filled stage by stage |
| `tests/` | pytest + hypothesis |
| `experiments/` | pre-registered experiments and the trial log |
| `reports/` | generated reports and figures |
| `docs/` | [model notes](docs/model_notes.md), [concepts](docs/concepts.md), [decisions](docs/decisions.md) |
