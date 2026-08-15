.DEFAULT_GOAL := help

COMPOSE := docker compose -f docker-compose.yml -f docker-compose.dev.yml
COMPOSE_E2E := $(COMPOSE) -f docker-compose.e2e.yml

.PHONY: help init up down build ps logs lint test seed migrate e2e-auth

help: ## Show this help.
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/' | sort

init: ## First-time setup: .env, build, start, wait healthy, migrate, seed.
	@test -f .env || cp .env.example .env
	$(COMPOSE) up -d --build
	@echo "Waiting for services to report healthy..."
	@for i in $$(seq 1 30); do \
		statuses=$$($(COMPOSE) ps --format '{{.Service}} {{.State}} {{.Health}}'); \
		echo "$$statuses"; \
		if echo "$$statuses" | awk 'BEGIN { seen=0 } { seen=1; if ($$2 != "running") exit 1; if ($$3 != "" && $$3 != "healthy") exit 1 } END { if (!seen) exit 1 }'; then \
			echo "All services running/healthy."; \
			break; \
		fi; \
		if [ "$$i" = "30" ]; then echo "Timed out waiting for services to become healthy." >&2; $(COMPOSE) logs; exit 1; fi; \
		sleep 5; \
	done
	$(MAKE) migrate
	$(MAKE) seed
	@echo ""
	@echo "Stack is up: frontend http://localhost:5173, backend http://localhost:8000."
	@echo "Image uploads (avatar / tweet images) sign against the internal 'minio' hostname,"
	@echo "so add this line to /etc/hosts or the browser can't resolve the upload URL:"
	@echo "  127.0.0.1 minio"

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
	$(COMPOSE) run --rm frontend sh -c "npm ci && npm run lint && npm run format:check && npm run typecheck"

test: ## Run backend + frontend test suites (with coverage gates) inside containers.
	$(COMPOSE) run --rm backend sh -c "uv run coverage run -m pytest && uv run coverage report"
	$(COMPOSE) run --rm frontend sh -c "npm ci && npm run test:coverage"

seed: ## Populate demo data for local development.
	$(COMPOSE) run --rm backend uv run python -m scripts.seed

migrate: ## Apply database migrations.
	$(COMPOSE) run --rm backend uv run alembic upgrade head

e2e-auth: ## Run the Playwright auth E2E suite on the host against the live stack (starts/stops it).
	@set -eu; \
	trap '$(COMPOSE_E2E) down -v' EXIT; \
	$(COMPOSE_E2E) up -d --build; \
	echo "Waiting for services to report healthy..."; \
	for i in $$(seq 1 30); do \
		statuses=$$($(COMPOSE_E2E) ps --format '{{.Service}} {{.State}} {{.Health}}'); \
		echo "$$statuses"; \
		if echo "$$statuses" | awk 'BEGIN { seen=0 } { seen=1; if ($$2 != "running") exit 1; if ($$3 != "" && $$3 != "healthy") exit 1 } END { if (!seen) exit 1 }'; then \
			echo "All services running/healthy."; \
			break; \
		fi; \
		if [ "$$i" = "30" ]; then echo "Timed out waiting for services to become healthy." >&2; $(COMPOSE_E2E) logs; exit 1; fi; \
		sleep 5; \
	done; \
	$(COMPOSE_E2E) run --rm backend uv run alembic upgrade head; \
	cd frontend && npm ci && npx playwright install --with-deps chromium && npm run e2e:auth
