# SME POS + WhatsApp Ordering Platform

POS, order board, reservations, stock, cashflow and WhatsApp ordering for restaurants and
cafes. Monorepo for the pilot.

## Repository layout

```
backend/            FastAPI API service + WhatsApp worker (Python 3.12+, uv)
  app/main.py       API app factory (/healthz, /readyz)
  app/serve.py      production entrypoint (validates config, then starts uvicorn)
  app/worker/       WhatsApp worker process entrypoint (separate process; stub for now)
  app/config.py     environment validation (pydantic-settings)
  tests/            pytest
admin/              Admin web app (React + TypeScript + Vite + Tailwind, pnpm)
  src/app/nav.ts    role-aware navigation (wireframe Sidebar/Owner, Sidebar/Staff)
  src/layout/       app shell: sidebar, page header, mobile bottom nav
  src/pages/        placeholder pages, one per wireframe screen
supabase/migrations/ plain SQL schema migrations (no Alembic)
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
`SUPABASE_JWKS_URL` and `SUPABASE_JWT_ISSUER` are required (`RABBITMQ_URL` is optional until
the WhatsApp worker exists); the process exits with a list of problems if the configuration is invalid. Default time zone is
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
```

## Deployment (Railway)

Two Railway services in one project, both deployed by GitHub Actions (`.github/workflows/ci.yml`):

| Service name | Source | Config |
|---|---|---|
| `backend` | `backend/` | `backend/Dockerfile`, `backend/railway.toml` |
| `admin` | `admin/` | `admin/Dockerfile`, `admin/railway.toml` |

On every push to `main`, CI runs first; if it is green, only the service whose files changed
is redeployed (`backend/**` or `supabase/**` -> backend, `admin/**` -> admin). Pull requests
and other branches run CI only.

One-time setup:

1. Railway: create the project (region Singapore), add services named exactly `backend` and
   `admin` (RabbitMQ is added later, together with the WhatsApp worker). Set the variables listed in `backend/railway.toml` and
   `admin/railway.toml` (admin `VITE_*` are build-time, so redeploy after changing them).
2. Railway: Project Settings -> Tokens -> create a project token for the production
   environment.
3. GitHub: Settings -> Secrets and variables -> Actions -> new secret `RAILWAY_TOKEN`.
4. Do **not** also connect the services to the GitHub repo in Railway, or each push deploys twice.

Database migrations (`supabase/migrations/`) are not applied by this pipeline; apply them to
the hosted Supabase project before merging a backend change that depends on them.
The WhatsApp worker will be a separate Railway service using the backend image with start
command `python -m app.worker.main`.
