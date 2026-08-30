# Makefile for F.R.I.D.A.Y. v3

.PHONY: ci test lint typecheck bench install setup export-memory distill clean

# Default target
all: ci

# Install dependencies
install:
	pip install -e ".[dev]"

# Run setup wizard
setup:
	python scripts/setup.py

# Lint with Ruff
lint:
	ruff check src/ tests/

# Type check with mypy
typecheck:
	mypy src/friday --ignore-missing-imports

# Run all tests
test:
	pytest tests/ -v --tb=short

# Run specific test suites
test-unit:
	pytest tests/unit -v --tb=short

test-integration:
	pytest tests/integration -v --tb=short

test-eval:
	pytest tests/evaluation -v --tb=short

test-security:
	pytest tests/security -v --tb=short

test-computer:
	pytest tests/computer -v --tb=short

test-memory:
	pytest tests/memory -v --tb=short

test-learning:
	pytest tests/learning -v --tb=short

test-smoke:
	pytest tests/smoke -v --tb=short

# Run model benchmarks
bench:
	python scripts/benchmark_models.py

# Export memory to YAML
export-memory:
	python scripts/export_memory.py

# Distill trajectories to skill candidates
distill:
	python scripts/distill_trajectories.py

# Run full CI pipeline locally
ci: lint typecheck test

# Clean up generated files
clean:
	rm -rf .pytest_cache .mypy_cache __pycache__ */__pycache__ */*/__pycache__
	rm -rf htmlcov .coverage

# Health check
health:
	python scripts/healthcheck.py