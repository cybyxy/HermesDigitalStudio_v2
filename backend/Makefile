.PHONY: test lint cov clean

test:
	uv run python -m pytest tests/ -v --tb=short

cov:
	uv run python -m pytest tests/ -v --tb=short --cov=src/backend --cov-report=term --cov-report=html

lint:
	uv run ruff check src/backend/

clean:
	rm -rf .pytest_cache htmlcov .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
