.PHONY: install dev lint format typecheck test run clean help docker-up docker-down

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*##"}; {printf "  %-12s %s\n", $$1, $$2}'

install:  ## Install production dependencies
	uv sync

dev:  ## Install all dependencies including dev tools
	uv sync --group dev

lint:  ## Check code style and errors with Ruff
	uv run ruff check src tests

format:  ## Auto-format code with Ruff
	uv run ruff format src tests

typecheck:  ## Run mypy static type checker
	uv run mypy src

test:  ## Run test suite with pytest
	uv run pytest

run:  ## Start the bot
	uv run python -m support_platform.main

clean:  ## Remove all cache directories
	uv run ruff clean
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null; true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null; true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null; true

docker-up:  ## Build and start backend + Postgres
	docker compose up --build

docker-down:  ## Stop and remove containers (Postgres data volume kept)
	docker compose down
