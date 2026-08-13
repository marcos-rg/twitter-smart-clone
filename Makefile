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
	$(COMPOSE) run --rm backend uv run mypy app tests
	$(COMPOSE) run --rm frontend npm run lint
	$(COMPOSE) run --rm frontend npm run format:check
	$(COMPOSE) run --rm frontend npm run typecheck

test: ## Run backend + frontend test suites inside containers.
	$(COMPOSE) run --rm backend uv run pytest
	$(COMPOSE) run --rm frontend npm run test

seed: ## Populate demo data for local development.
	@echo "No seed script yet: the seed CLI is delivered by TSC-DATA-001."
	@echo "Once available this target will run it inside the backend container."

migrate: ## Apply database migrations.
	@echo "Alembic isn't configured yet: migrations are delivered by TSC-DATA-001."
	@echo "Once available this target will run 'alembic upgrade head' inside the backend container."
