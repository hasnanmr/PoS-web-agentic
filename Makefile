# Local development shortcuts. Run `make help` for the list.
.DEFAULT_GOAL := help
.PHONY: help setup up down api worker admin test lint fmt build check \
        backend-test backend-lint admin-test admin-lint db-reset db-migrate db-new db-test check-migrations openapi \
        audit

# Local service passwords live only in backend/.env (copied from backend/.env.example).
-include backend/.env

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-14s %s\n", $$1, $$2}'

setup: ## Install backend (uv) and admin (pnpm) dependencies, create local env files
	cd backend && uv sync
	cd admin && pnpm install
	@test -f backend/.env || cp backend/.env.example backend/.env
	@test -f admin/.env.local || cp admin/.env.example admin/.env.local

up: ## Start local Postgres and RabbitMQ (docker compose)
	@test -n "$(LOCAL_POSTGRES_PASSWORD)" -a -n "$(LOCAL_RABBITMQ_PASSWORD)" || { echo "LOCAL_*_PASSWORD missing: run make setup or update backend/.env from backend/.env.example"; exit 1; }
	docker compose --env-file backend/.env up -d

down: ## Stop local services
	docker compose --env-file backend/.env down

api: ## Run the FastAPI service with auto-reload on :8000
	cd backend && uv run uvicorn app.main:create_app --factory --reload --port 8000

worker: ## Run the WhatsApp worker process (stub)
	cd backend && uv run python -m app.worker.main

admin: ## Run the admin web app dev server on :5170
	cd admin && pnpm dev

LOCAL_DB_ADMIN_URL ?= postgresql://pos:$(LOCAL_POSTGRES_PASSWORD)@localhost:5432/pos

db-reset: ## Recreate the local docker DB schema: shim, migrations, seed, app_backend password
	@test -n "$(APP_BACKEND_DB_PASSWORD)" || { echo "APP_BACKEND_DB_PASSWORD missing: run make setup or update backend/.env from backend/.env.example"; exit 1; }
	psql "$(LOCAL_DB_ADMIN_URL)" -v ON_ERROR_STOP=1 -q -c "drop schema if exists app cascade; drop schema if exists auth cascade"
	psql "$(LOCAL_DB_ADMIN_URL)" -v ON_ERROR_STOP=1 -q -f supabase/tests/supabase_shim.sql
	psql "$(LOCAL_DB_ADMIN_URL)" -v ON_ERROR_STOP=1 -q -c "drop schema if exists alembic cascade"
	cd backend && MIGRATION_DATABASE_URL="$(LOCAL_DB_ADMIN_URL)" uv run python -m app.tools.migrate
	psql "$(LOCAL_DB_ADMIN_URL)" -v ON_ERROR_STOP=1 -q -f supabase/seed.sql
	psql "$(LOCAL_DB_ADMIN_URL)" -v ON_ERROR_STOP=1 -q -c "alter role app_backend password '$(APP_BACKEND_DB_PASSWORD)'"

db-migrate: ## Apply pending migrations to the local docker DB (Alembic)
	cd backend && MIGRATION_DATABASE_URL="$(LOCAL_DB_ADMIN_URL)" uv run python -m app.tools.migrate

db-new: ## New migration: make db-new name=add_something (SQL file + Alembic revision)
	@test -n "$(name)" || { echo "usage: make db-new name=snake_case_name"; exit 1; }
	scripts/new-migration.sh "$(name)"

db-test: ## Migrations + SQL tests on an EMPTY database (TEST_DB_URL=postgresql://...)
	DATABASE_URL="$(TEST_DB_URL)" scripts/db-test.sh

check-migrations: ## Migration naming and no edits to migrations already on origin/main
	scripts/check-migrations.sh

openapi: ## Regenerate docs/api/openapi.json (API contract)
	cd backend && uv run python -m app.tools.export_openapi

backend-test: ## Backend tests
	cd backend && uv run pytest

backend-lint: ## Backend lint + format check + API contract check
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run python -m app.tools.export_openapi --check

admin-test: ## Admin tests
	cd admin && pnpm test

admin-lint: ## Admin lint + typecheck
	cd admin && pnpm lint && pnpm typecheck

audit: ## Known vulnerabilities in the locked dependencies (OSV; works with any npm registry)
	scripts/check-vulnerabilities.py
	cd admin && pnpm audit --registry https://registry.npmjs.org --audit-level=high

test: backend-test admin-test ## All tests

lint: check-migrations backend-lint admin-lint ## All linters

fmt: ## Format backend code
	cd backend && uv run ruff format . && uv run ruff check --fix .

build: ## Production build of the admin app
	cd admin && pnpm build

check: lint test build ## Everything CI should run
