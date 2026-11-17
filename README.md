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
railway.toml        Railway config for the backend API service
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
`SUPABASE_JWKS_URL`, `SUPABASE_JWT_ISSUER` and `RABBITMQ_URL` are required; the process
exits with a list of problems if the configuration is invalid. Default time zone is
`Asia/Jakarta` (WIB). Logs are JSON lines on stdout.

### Admin web app

```bash
cd admin
pnpm dev        # http://localhost:5173  (or: make admin)
pnpm build && pnpm preview   # production build on http://localhost:4173
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

## Deployment (not set up yet)

Supabase (Postgres + Auth) and Railway are not provisioned; the repo only contains config.
The backend API deploys to Railway from `backend/Dockerfile` (see `railway.toml`). The
WhatsApp worker will be a separate Railway service using the same image with start command
`python -m app.worker.main`.
