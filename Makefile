.PHONY: setup test lint

setup:
	python -m pip install -e ".[dev]"

test:
	python -m pytest

lint:
	ruff check .
