# Database (Supabase Postgres)

Plain SQL migrations in Supabase CLI format. They target Supabase Postgres but also run on plain PostgreSQL 16+ so CI can test them without the Supabase stack.

| Path | Purpose |
|---|---|
| `migrations/` | Schema, in order. Never edit a migration that has run on a shared environment; add a new one. |
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
supabase start          # local stack, applies migrations + seed.sql
supabase db reset       # re-apply from scratch
supabase link --project-ref <ref> && supabase db push   # hosted project (after T-079)
```

## Conventions

- All business tables live in schema `app` (not exposed to the Data API).
- Every operational table carries `tenant_id` and `outlet_id`; composite foreign keys `(outlet_id, tenant_id)` stop cross-tenant links.
- Money is `bigint` whole rupiah. PB1 rate is `pb1_rate_bps` (1000 = 10%), off by default.
- Instants are `timestamptz`; outlets default to `Asia/Jakarta` (WIB).
- Append-only tables (`ledger_entries`, `stock_movements`, `order_events`, `reservation_events`, `attendance_events`) reject UPDATE and DELETE with a trigger.
- Not yet included: RLS policies and grants (T-005), `app_backend` role, auth hook, and the FK from `app.users.id` to `auth.users` (T-113).
