---
id: EXP-000
title: "Template: copy to EXP-NNN_short_name.md"
status: draft            # draft | approved | done
approved_by: null        # set by Nick, never by the code
approved_on: null        # YYYY-MM-DD
scenario: "baseline"
config_hash: null        # from `uv run mm-sim check-config --scenario <scenario>`
decision: null           # CONFIRMED | REJECTED | INCONCLUSIVE, set once the status is done
---

# EXP-000 — template

Written **before** the run. The code refuses to run an experiment that is not `approved` or
whose `config_hash` differs from the current one. It runs once; a new idea is a new number.

## Hypothesis

One or two sentences, falsifiable.

## Prediction from theory

The formula, its source (`docs/model_notes.md` section), and the predicted numbers.

## Setup

Scenario, strategies, parameter grid, root seed, episodes, steps per episode.

## Numbers that confirm or reject

Stated before the run: what CONFIRMED means, what REJECTED means, and what is INCONCLUSIVE.

## Result

Filled after the run: tables with confidence intervals, paths to the run directory and report.

## Decision

CONFIRMED / REJECTED / INCONCLUSIVE, with one paragraph of reasoning.

## What I learned

About the model, and what depends on its assumptions.
