.PHONY: install run test lint format typecheck check samples docker

install:
	pip install -e ".[dev]"

run:
	uvicorn app.main:app --reload

test:
	pytest --cov=app --cov-report=term-missing

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .

typecheck:
	mypy

# Everything CI runs.
check: lint typecheck test

samples:
	python scripts/make_samples.py

docker:
	docker compose up --build
