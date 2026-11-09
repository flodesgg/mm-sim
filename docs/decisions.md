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
