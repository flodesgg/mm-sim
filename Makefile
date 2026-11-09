.PHONY: check check-all lint typecheck test test-all fmt

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
