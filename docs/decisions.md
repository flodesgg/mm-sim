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
