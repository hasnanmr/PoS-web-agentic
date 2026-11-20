# SME POS + WhatsApp Ordering Platform

POS, order board, reservations, stock, cashflow and WhatsApp ordering for restaurants and
cafes. Monorepo for the pilot.

## Repository layout

```
backend/            FastAPI API service + WhatsApp worker (Python 3.12+, uv)
  app/main.py       API app factory (/healthz, /readyz)
  app/serve.py      production entrypoint (validates config, then starts uvicorn)
  app/worker/       WhatsApp worker process: inbound flows (W1 menu), outbound sender
  app/config.py     environment validation (pydantic-settings)
  tests/            pytest
admin/              Admin web app (React + TypeScript + Vite + Tailwind, pnpm)
  src/app/nav.ts    role-aware navigation (wireframe Sidebar/Owner, Sidebar/Staff)
  src/layout/       app shell: sidebar, page header, mobile bottom nav
  src/pages/        placeholder pages, one per wireframe screen
backend/migrations/ schema migrations: Alembic revisions, each running one plain-SQL file
supabase/           Supabase config, seed.sql, SQL tests (schema, RLS)
design/             wireframes (source of truth for every frontend screen)
docs/               project documentation
docker-compose.yml  local Postgres 16 + RabbitMQ 3 (management UI)
backend/railway.toml, admin/railway.toml  Railway config per service
Makefile            dev / test / lint shortcuts (`make help`)
```

## Specs and design

- [PRD](PRD-SME-Automation-Platform.md)
- [User stories](User-Stories-SME-Automation-Platform.md)
- [Task breakdown](Task-Breakdown-SME-Automation-Platform.md)
- [Wireframe traceability](design/WIREFRAME-TRACEABILITY.md) and previews in `design/previews/`
- [CLAUDE.md](CLAUDE.md): frontend and backend rules, design tokens
- [Domain glossary, rules, and enums](docs/domain/domain-glossary-and-rules.md) (T-001)
- [API boundaries](docs/architecture/api-boundaries.md) (T-002)
- [Screen → endpoint map](docs/architecture/screen-endpoint-map.md): backend contract per wireframe screen
- [Database](supabase/README.md) (T-004)

Frontend screens and the backend endpoints they use must match the wireframes; note the screen
code (e.g. `O2`, `S1`, `M1`) in the route/component file and in the endpoint's router.

## Accounts and roles

- **Platform admin** invites every new owner from the command line (no screen):

  ```bash
  cd backend
  uv run python -m app.cli invite-owner --email owner@cafe.id --invited-by you@platform
  ```

  The owner gets a Supabase invite email, sets a password, signs in with app role
  `owner_pending`, and creates the business on O1. Needs `SUPABASE_URL`,
  `SUPABASE_SERVICE_ROLE_KEY`, and `DATABASE_URL`.
- **Owner** invites staff from O4 (Staf & Akses). There is no public sign-up.

## Database and tests

```bash
make up          # docker compose Postgres + RabbitMQ
make db-reset    # schema (shim + migrations), dummy seed, app_backend password
make check       # migration hygiene, lint, API contract, tests, build
make db-test TEST_DB_URL=postgresql://<user>:<password>@localhost:5432/empty_db
```

The API connects as `app_backend` so row-level security always applies. CI
(`.github/workflows/ci.yml`) runs all of the above against a Postgres 16 service,
including backend integration tests (`TEST_DATABASE_URL`, `TEST_APP_DATABASE_URL`).

## Prerequisites

- Python 3.12+ (3.13 recommended) and [uv](https://docs.astral.sh/uv/)
- Node.js 22+ and pnpm 10
- Docker (optional, for local Postgres and RabbitMQ)

## Getting started

```bash
make setup     # uv sync, pnpm install, copy env templates to backend/.env and admin/.env.local
make up        # optional: Postgres on :5432, RabbitMQ on :5672 (UI on :15672)
```

### Backend

```bash
cd backend
uv run uvicorn app.main:create_app --factory --reload --port 8000   # or: make api
curl localhost:8000/healthz     # liveness
curl localhost:8000/readyz      # readiness: checks DB if DATABASE_URL is set
uv run python -m app.worker.main                                     # or: make worker
```

Configuration comes from environment variables or `backend/.env` (template:
[`backend/.env.example`](backend/.env.example)). `APP_ENV` is one of `local`, `demo`,
`staging`, `production`. Outside `local`, `DATABASE_URL`, `SUPABASE_URL`,
`SUPABASE_JWKS_URL` and `SUPABASE_JWT_ISSUER` are required (`RABBITMQ_URL` and `WHATSAPP_*`
are optional for the API; the WhatsApp worker requires `DATABASE_URL` and
idles without `RABBITMQ_URL` or `WHATSAPP_ACCESS_TOKEN`); the process exits with a list of problems if the configuration is invalid. Default time zone is
`Asia/Jakarta` (WIB). Logs are JSON lines on stdout.

### Admin web app

```bash
cd admin
pnpm dev        # http://localhost:5170  (or: make admin)
pnpm build && pnpm preview   # production build on http://localhost:4170
```

Requires `VITE_API_BASE_URL`, `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` in
`admin/.env.local` (template: [`admin/.env.example`](admin/.env.example)); if any is missing
or invalid the app shows a configuration error screen.

There is no login yet (T-006). In `pnpm dev`, a temporary "Dev · peran" switch at the bottom
of the sidebar toggles Owner/Staf; in any build you can also use `?role=owner` or
`?role=staff`.

## Tests and lint

```bash
make test      # backend pytest + admin vitest
make lint      # ruff (check + format) + eslint + tsc
make check     # lint, test and admin build
make audit     # known vulnerabilities in backend/uv.lock and admin/pnpm-lock.yaml
```

`make audit` asks OSV about every locked package, so it works with any npm registry. Plain
`pnpm audit` does not: it needs an audit endpoint on the configured registry, and a mirror such
as `registry.npmmirror.com` has none, so it errors out instead of auditing. `make audit` runs
`pnpm audit` against `registry.npmjs.org` explicitly for that reason. Advisories that are known
and accepted go in `.github/osv-ignore.txt` with a reason; CI (job `security`) fails on anything
else, so bump the dependency instead.

## Deployment (Railway)

Two Railway services in one project, both deployed by GitHub Actions (`.github/workflows/ci.yml`):

| Service name | Source | Config |
|---|---|---|
| `backend` | `backend/` | `backend/Dockerfile`, `backend/railway.toml` |
| `admin` | `admin/` | `admin/Dockerfile`, `admin/railway.toml` |

On every push to `main` (each merged PR), CI runs first. If it is green:

1. **Snapshot running deployments**: records the backend and admin deployments serving now
   (Railway API). If the API is not usable, the run stops here and nothing changes.
2. **Migrate database (Alembic)**: `python -m app.tools.migrate` applies pending revisions
   from `backend/migrations` to the hosted Supabase database. It prints the current revision
   and the head, and does nothing when the database is already at head.
3. **Deploy backend** and **Deploy admin**: both services are always redeployed. CI stamps
   the commit into each build (`backend/app/BUILD_SHA`, returned as `version` by `/healthz`
   and `/readyz`; `admin/public/version.txt`).
4. **Smoke test production** (`scripts/ci/smoke.sh`), retried for up to 5 minutes:
   - backend `/readyz` is healthy and reports this commit;
   - `/api/v1/me` returns 401 without a token;
   - admin `/` serves the app and `/version.txt` is this commit.
5. **Roll back deployments** (`scripts/ci/rollback.sh`): runs only when the migration
   succeeded and a deploy or the smoke test failed. It rolls **both** services back to the
   snapshot and verifies them with the smoke test. The database is not rolled back
   (migrations are additive and forward-only), and the run stays red.

Runs on `main` queue and never cancel each other. Pull requests and other branches run CI only.

One-time setup:

1. Railway: create the project (region Singapore), add services named exactly `backend` and
   `admin` (RabbitMQ is added later, together with the WhatsApp worker). Set the variables listed in `backend/railway.toml` and
   `admin/railway.toml` (admin `VITE_*` are build-time, so redeploy after changing them).
2. Railway: Project Settings -> Tokens -> create a project token for the production
   environment.
3. GitHub: Settings -> Secrets and variables -> Actions -> new secret `RAILWAY_TOKEN`.
4. Do **not** also connect the services to the GitHub repo in Railway, or each push deploys twice.
5. GitHub: new secret `SUPABASE_DB_URL`, the **session pooler** connection string of the hosted
   project (Supabase dashboard -> Connect -> Session pooler, port 5432, IPv4), with the database
   password filled in: `postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres`.

Migrations must stay additive (new tables/columns, no drops or renames in the same release),
because they are applied before the new backend replaces the old one.

### Migrations (Alembic)

Since 2026-11-18 (product owner decision) migrations run with Alembic instead of the Supabase
CLI. Each revision in `backend/migrations/versions/` runs one plain-SQL file from
`backend/migrations/sql/`, so the schema stays reviewable SQL. Revision ids are the 14-digit
file timestamps; the chain is forward-only.

- New migration: `make db-new name=add_something`, then write the SQL file.
- Local DB: `make db-migrate` (or `make db-reset` to rebuild).
- Any DB: `MIGRATION_DATABASE_URL=<owner URL> uv run python -m app.tools.migrate [--dry-run | --check]`.
- The hosted database was migrated with the Supabase CLI up to `20261118000310`. On the first
  Alembic run, `app.tools.migrate` stamps the newest version found in
  `supabase_migrations.schema_migrations`, then applies only later revisions.
- Alembic keeps its version in schema `alembic` (not exposed by the Data API).
The WhatsApp worker is the Railway service `worker`, deployed by the `deploy-worker` job from
the same build context as the API. Its start command (`python -m app.worker.main`), restart
policy and region are service settings (it does not read `backend/railway.toml`). Variables
are referenced from `backend`, plus `WHATSAPP_ACCESS_TOKEN` and optional
`WHATSAPP_GRAPH_VERSION`; without RabbitMQ or the token it stays on standby. It is not in the smoke test
or the rollback. Connect an
outlet to its Meta number with `uv run python -m app.cli whatsapp-connect --outlet <uuid>
--phone-number-id <id>`, then register `https://<backend>/webhooks/whatsapp` in the Meta app.
