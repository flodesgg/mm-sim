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
