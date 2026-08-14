.DEFAULT_GOAL := help

COMPOSE := docker compose -f docker-compose.yml -f docker-compose.dev.yml

.PHONY: help up down build ps logs lint test seed migrate

help: ## Show this help.
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/' | sort

up: ## Build (if needed) and start the full local stack in the background.
	$(COMPOSE) up -d --build

down: ## Stop the stack. Named volumes (Postgres/Redis/MinIO data) are kept.
	$(COMPOSE) down

build: ## (Re)build the backend and frontend dev images.
	$(COMPOSE) build

ps: ## Show container status, including health.
	$(COMPOSE) ps

logs: ## Follow logs for every service.
	$(COMPOSE) logs -f

lint: ## Run backend + frontend formatting/lint/type checks inside containers.
	$(COMPOSE) run --rm backend uv run ruff check .
	$(COMPOSE) run --rm backend uv run black --check .
	$(COMPOSE) run --rm backend uv run mypy app tests scripts
	$(COMPOSE) run --rm frontend sh -c "npm ci && npm run lint"
	$(COMPOSE) run --rm frontend sh -c "npm ci && npm run format:check"
	$(COMPOSE) run --rm frontend sh -c "npm ci && npm run typecheck"

test: ## Run backend + frontend test suites (with coverage gates) inside containers.
	$(COMPOSE) run --rm backend sh -c "uv run coverage run -m pytest && uv run coverage report"
	$(COMPOSE) run --rm frontend sh -c "npm ci && npm run test:coverage"

seed: ## Populate demo data for local development.
	$(COMPOSE) run --rm backend uv run python -m scripts.seed

migrate: ## Apply database migrations.
	$(COMPOSE) run --rm backend uv run alembic upgrade head
