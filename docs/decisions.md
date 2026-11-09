# Decisions

One line per decision or bug fix, newest last. Format: date — decision — reason.

- 2026-11-09 — Base parameters follow the simulation section of Avellaneda & Stoikov (2008)
  (`s0=100, T=1, dt=0.005, sigma=2, A=140, k=1.5`) — a known reference point; verification
  status is recorded in `model_notes.md`.
- 2026-11-09 — Base tick size is 0.01, and theory checks (EXP-001) use the actual rounded quote
  distances, not the nominal half-spread — outward rounding from a continuous mid widens the
  effective spread, so comparing against the nominal `h` would show a false mismatch.
- 2026-11-09 — The decomposition horizon (`accounting.markout_horizon_steps`) and the informed
  traders' horizon (`flow.informed.horizon_steps`) are separate parameters, equal by default —
  one is how the analyst measures, the other is what the informed trader knows.
- 2026-11-09 — In the two-point world an informed trader trades only at a profit (buys only if
  `ask < V`, sells only if `bid > V`) — it matters only when a quote is outside `[V_L, V_H]`,
  which a human can do in play mode; an informed trader would not buy above the known value.
- 2026-11-09 — CLI uses `argparse`, as in paper-lab — no extra dependency, same style.
- 2026-11-09 — One config hash (`Config.model_hash`): the validated model sections (market,
  flow, engine, accounting, strategies, analysis) after the scenario merge; paths and logging
  are excluded — the hash must change exactly when simulation results can change.
- 2026-11-09 — Strategy parameters are a free mapping in the root schema and are validated by
  each strategy's own schema — adding a strategy stays a one-file job.
- 2026-11-09 — A side at the inventory limit at the start of a step is closed for the whole
  step (instead of checking fill by fill) — `|q| <= q_max` then holds whatever the order of
  fills, and the rule is one sentence.
- 2026-11-09 — Noise fills use uniform draws fixed before the episode, one per step and side —
  gives common random numbers across strategies and makes "a wider quote never gets more
  fills" an exact property.
- 2026-11-09 — The config hash covers the scenario only; the root seed and episode count of a
  run are recorded next to it in every output — `--seed`/`--episodes` on the command line
  must not make the hash differ from what `check-config` prints and experiments pin.
- 2026-11-09 — EXP-001's theory averages the closed form over the tick offset
  (`delta = h + U`, `U ~ Uniform[0, tick)`) — follows the earlier decision to compare against
  actual rounded distances.
- 2026-11-09 — EXP-001 states the optimum as `h* = 0.744`, not `1/k = 0.667` — `A*dt = 0.7`
  is not small in the baseline, so the small-dt approximation in the build prompt is off by
  about 12%; the exact maximiser of the same formula is used.
- 2026-11-09 — Experiments run on a seed never used while building (EXP-001: 101) — the
  stage's acceptance run at seed 1 shows one point of the curve before pre-registration.
- 2026-11-09 — Process error: commit `067bb5c7b737` was made with `make check` red (six
  package docstrings not formatted; no code difference). The check and the commit were chained
  in one shell line that ignored the exit code. Fixed in the next commit; from now on
  `make check && git commit`, never `;`. The Stage A acceptance run records that commit, whose
  simulation code is identical to the fixed one.
- 2026-11-09 — Bug found before it was used: the first closed form for P&L with informed flow
  ignored that noise fills are selected (they happen when no informed trader took the quote).
  A smoke run on seed 4242 disagreed by 14 standard errors; the selection term was added and
  `test_simulated_mean_matches_theory_with_informed_flow` now guards it.
- 2026-11-09 — Scenario `toxic` uses an informed horizon of 50 steps and `q_max = 200` — with
  the base horizon of 10 the informed edge is too small to move the break-even spread across
  the grid; the wide limit keeps the closed form applicable. Invented numbers, approved by
  Nick through EXP-002.
- 2026-11-09 — Scenario `two_point` uses tick 0.0001 and `q_max = 1000` — outward rounding
  adds half a tick of profit per fill to Glosten–Milgrom quotes, and a binding limit would
  break the Bayes update.
- 2026-11-09 — New strategy `fixed_prior` (fixed quotes around the prior mean) — the `fixed`
  strategy needs a public mid, which the two-point world does not have, and Stage B needs a
  naive benchmark there.
- 2026-11-09 — In the future-scramble test the informed traders keep their knowledge of the
  original path — otherwise their trades before step `t` change with the scramble and an
  inventory-dependent strategy would fail the test without looking ahead.
- 2026-11-09 — The regression test compares only the columns stored in the fixture — markout
  columns were added to the per-episode table; the stored values must not move, and the
  fixture was not regenerated.
- 2026-11-09 — `clairvoyant` is not in the strategy registry — the CLI and experiments cannot
  run it; only tests construct it.
- 2026-11-09 — **Delegation.** Nick left the build running overnight ("продолжай делать все
  сам, оставляю тебя на ночь"). From EXP-002 on, experiments are approved under that delegation,
  not by Nick, and say so in `approved_by`; model choices that were Nick's to make are made
  under the same delegation and marked "(delegated)" below. Unchanged: each experiment is
  written and committed before it runs, runs once, and the hard constraints of the build
  prompt hold (simulation only, repo private, Stage G not started).
- 2026-11-09 — (delegated) Scenario `inventory`: liquidation cost `0.5 + 0.05*|q|` per lot —
  without a cost liquidated and mark-to-market P&L are equal and "judged on liquidated P&L"
  means nothing; the size is invented.
- 2026-11-09 — (delegated) Scenario `jumpy`: jumps of +-1.0 at rate 5 per unit time, requote
  every 5 steps, `q_max = 200` — a jump larger than the half-spread 0.75 puts a stale quote
  through the value; invented.
- 2026-11-09 — (delegated) EXP-003 thresholds (std cut of at least 25%, mean cost at most 15%)
  set under the delegation, not by Nick, from the direction and rough size reported in Avellaneda & Stoikov (2008),
  Table 1 — the build prompt reserved these numbers for Nick.
- 2026-11-09 — A pick-off is a fill on a quote posted at an earlier step with a negative edge
  at the fill — measurable per fill without knowing why the value moved; in the jump scenario
  most of them follow a jump (tested).
- 2026-11-09 — The jump stream is separate from the diffusion stream — a jump scenario and its
  no-jump twin share the diffusion path, and adding the stream did not change any earlier
  result (regression fixture unchanged).
- 2026-11-09 — `fixed`, `skew` and `avellaneda_stoikov` pull the side that would breach the
  inventory limit — the build prompt asks strategies to do so; fills are unchanged because the
  engine enforced the limit already.
- 2026-11-09 — `mm-sim reproduce` reruns a finished experiment on its own seed and grid,
  requires the regenerated table to equal the stored one, and adds nothing to the trial log —
  "run once" forbids re-rolling an experiment with new choices; a deterministic rebuild that
  must give the same numbers is a check, not a new trial. The pinned config hash may differ by
  then (strategies were added to `config.yaml`); equality of the numbers is the stronger test.
- 2026-11-09 — Experiment reports gained a "representative grid point" section (decomposition,
  markouts, inventory histogram, example episode); EXP-001..004 were rebuilt with `reproduce`
  to get it, numbers identical to the original runs.
- 2026-11-09 — SUSPICIOUS thresholds: Glosten–Milgrom is flagged at |mean| > 4 standard errors
  (a 95% CI excludes zero in 5% of honest runs, which would cry wolf); profit below break-even
  uses EXP-002's margin 0.05; the clairvoyant control quotes the strategy's average
  half-spread and is compared on 200 paired episodes.
- 2026-11-09 — (delegated) Robustness is a pre-registered experiment (EXP-005), not an ad-hoc
  script, with variants `sigma = 4`, `k = 3`, jumps of 1.0 at rate 5 — it compares strategies,
  so the build prompt's rule applies; variant values are invented.
- 2026-11-09 — Kind-specific experiment settings live in the experiment file's `settings`
  block — robustness variants are parameters and must not be hard-coded.
- 2026-11-09 — Play mode makes the human a `Strategy` (`HumanStrategy`, not registered) whose
  `quote` asks for input; the game is one episode of the reference engine — no second market
  implementation can drift from the simulations.
- 2026-11-09 — A new game draws a fresh random seed unless `--seed` is given, and the seed is
  saved with the game — otherwise every game would have the same value and traders; any game
  can be replayed.
- 2026-11-09 — A quote that exceeds the time limit is pulled for that round (no quotes), and
  counted — a slow market maker is out of the market, it is not given a default quote.
- 2026-11-09 — The Glosten–Milgrom reference in the game summary is computed from the trades
  the player saw and ignores no-trade rounds — it is the standard GM update; the summary says
  that a round without a trade is also informative.
- 2026-11-09 — (delegated) Play scenarios: easy (20 rounds, 20% informed, no time limit),
  medium (30 rounds, 40%, 20 s), hard (40 rounds, 60%, V 98/102, prior 0.35, 10 s) — invented
  difficulty levels.
- 2026-11-09 — `play` settings (`time_limit_sec`) are a config section outside the model hash —
  they cannot change a simulation result.
