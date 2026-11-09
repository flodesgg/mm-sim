.PHONY: check check-all lint typecheck test test-all fmt figures benchmark

# Fast gate, run after every stage. Look at its real exit code: never pipe it into tail/head.
check: lint typecheck test

# Everything, including tests marked slow.
check-all: lint typecheck test-all

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

typecheck:
	uv run mypy

test:
	uv run pytest -m "not slow"

test-all:
	uv run pytest

fmt:
	uv run ruff format src tests
	uv run ruff check --fix src tests

# Rebuild every experiment report and figure from scratch (same seeds), and fail if any
# stored number does not reproduce.
figures:
	uv run mm-sim reproduce all

benchmark:
	uv run mm-sim benchmark
