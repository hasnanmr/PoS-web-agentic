# Database (Supabase Postgres)

Supabase config, seed data, and the SQL test suites. **Schema migrations moved to Alembic** in `backend/migrations/` (2026-11-18): each revision runs one plain-SQL file from `backend/migrations/sql/`. They target Supabase Postgres but also run on plain PostgreSQL 16+ so CI can test them without the Supabase stack.

| Path | Purpose |
|---|---|
| `../backend/migrations/` | Schema (Alembic + SQL), in order. Never edit a migration that has run on a shared environment; add a new one (`make db-new name=…`). |
| `tests/rls.sql` | RLS isolation, privileges, token hook (T-005, T-113). |
| `tests/schema_smoke.sql` | Constraint tests (append-only, no double booking, one open shift/bill/attendance record, cross-tenant FKs, PB1 setting). Runs in a transaction and rolls back. |
| `seed.sql` | Dummy data only (NFR1). |
| `config.toml` | Local Supabase CLI config. Hand-written; verify against `supabase init` before first use. |

## Run against plain Postgres

```bash
createdb sme_test
DATABASE_URL=postgresql://postgres@localhost:5432/sme_test scripts/db-test.sh
```

## Run with the Supabase CLI (once installed)

```bash
supabase start          # local stack (no migrations here any more)
cd backend && MIGRATION_DATABASE_URL=postgresql://postgres:postgres@localhost:54322/postgres \
  uv run python -m app.tools.migrate     # schema via Alembic
# Hosted project: migrations run from CI on every merge to main (job "Migrate database").
```

## Conventions

- All business tables live in schema `app` (not exposed to the Data API).
- Every operational table carries `tenant_id` and `outlet_id`; composite foreign keys `(outlet_id, tenant_id)` stop cross-tenant links.
- Money is `bigint` whole rupiah. PB1 rate is `pb1_rate_bps` (1000 = 10%), off by default.
- Instants are `timestamptz`; outlets default to `Asia/Jakarta` (WIB).
- Append-only tables (`ledger_entries`, `stock_movements`, `order_events`, `reservation_events`, `attendance_events`) reject UPDATE and DELETE with a trigger.
- RLS is enabled on every `app` table (T-005). The API and workers connect as `app_backend` (no BYPASSRLS, owns nothing) and set `app.tenant_id`, `app.user_id`, `app.actor`, `app.device_outlet_id` per transaction (T-113). Cross-tenant lookups exist only as SECURITY DEFINER functions: token hook, outlet-by-phone resolver, due-job claim, owner invitations.
- Append-only tables have no UPDATE/DELETE grant for `app_backend`; stock levels (`outlet_stock`) are read-only and change only through `stock_movements`.
- `tests/rls.sql` covers tenant/outlet isolation, privileges, and the token hook; `tests/supabase_shim.sql` stands in for Supabase roles and `auth.users` on plain PostgreSQL.
