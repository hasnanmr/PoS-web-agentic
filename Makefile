# Local development shortcuts. Run `make help` for the list.
.DEFAULT_GOAL := help
.PHONY: help setup up down api worker admin test lint fmt build check \
        backend-test backend-lint admin-test admin-lint

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-14s %s\n", $$1, $$2}'

setup: ## Install backend (uv) and admin (pnpm) dependencies, create local env files
	cd backend && uv sync
	cd admin && pnpm install
	@test -f backend/.env || cp backend/.env.example backend/.env
	@test -f admin/.env.local || cp admin/.env.example admin/.env.local

up: ## Start local Postgres and RabbitMQ (docker compose)
	docker compose up -d

down: ## Stop local services
	docker compose down

api: ## Run the FastAPI service with auto-reload on :8000
	cd backend && uv run uvicorn app.main:create_app --factory --reload --port 8000

worker: ## Run the WhatsApp worker process (stub)
	cd backend && uv run python -m app.worker.main

admin: ## Run the admin web app dev server on :5173
	cd admin && pnpm dev

backend-test: ## Backend tests
	cd backend && uv run pytest

backend-lint: ## Backend lint + format check
	cd backend && uv run ruff check . && uv run ruff format --check .

admin-test: ## Admin tests
	cd admin && pnpm test

admin-lint: ## Admin lint + typecheck
	cd admin && pnpm lint && pnpm typecheck

test: backend-test admin-test ## All tests

lint: backend-lint admin-lint ## All linters

fmt: ## Format backend code
	cd backend && uv run ruff format . && uv run ruff check --fix .

build: ## Production build of the admin app
	cd admin && pnpm build

check: lint test build ## Everything CI should run
