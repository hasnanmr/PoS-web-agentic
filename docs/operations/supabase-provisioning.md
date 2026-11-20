# Supabase provisioning checklist (T-079)

Status (2026-11-18): [PoS-web-agentic-staging](https://supabase.com/dashboard/project/igesdngvyyhmbvjclwgi) in Singapore is the **staging/demo** project on the Free plan. It has no client users. The dashboard's `main PRODUCTION` branch badge is Supabase's branch label, not this application's environment designation. Use separate projects if demo and production environments are created later. Do not put real customer data here.

Completed on this project: repository migrations through `20261118000200_catalog_functions.sql` plus `20261118000250_harden_function_access.sql` (with matching migration versions), invite-only Auth, the `app.custom_access_token_hook`, 900-second access tokens, `http://localhost:5170` as the Auth Site URL and Redirect URL, and four private Storage buckets. The current JWT signing key is ECC P-256. The previous HS256 key is revoked; legacy `anon` and `service_role` API keys are disabled. Security Advisor showed zero errors and zero warnings after hardening; its single informational item is the intentionally policy-free `app.owner_invitations` table, which is accessed through restricted functions. The admin app's local publishable key and project URL are in the ignored `admin/.env.local` file.

The `app_backend` role password and transaction-pooler URL are in the ignored local `backend/.env`, together with the Supabase URL/JWKS/issuer and a new secret API key for Auth admin operations. A read-only connection as `app_backend` and an Auth admin API request succeeded. When deployed, copy backend variables to deployment secrets and replace the local Auth URL with the hosted admin URL. Free is appropriate for this disposable staging demo; backups/PITR and the production readiness gates in step 10 are required before pilot or production use. Do not run `supabase/seed.sql` on this project.

| Step | Setting | Source of truth |
|---|---|---|
| 1 | Create project, region **Singapore**, Postgres major version recorded in `supabase/config.toml` `[db] major_version` | ADR 0001 |
| 2 | Auth → disable public sign-ups (invite-only) | `config.toml [auth] enable_signup = false` |
| 3 | Auth → JWT signing keys: create an **asymmetric** key (ES256 or RS256), make it current, revoke the legacy shared secret once nothing uses it | T-113, `backend/.env.example` (`SUPABASE_JWKS_URL`, `SUPABASE_JWT_ISSUER`) |
| 4 | Auth → access token expiry 900 s; refresh token rotation on | `config.toml [auth]` |
| 5 | Auth → Hooks → Custom Access Token → Postgres function `app.custom_access_token_hook` | migration `..._auth_roles_hook.sql` |
| 6 | Migrations run from CI on every merge to `main` (Alembic, job "Migrate database"). Set the GitHub secret `SUPABASE_DB_URL` to the session pooler URL (port 5432) with the `postgres` role. By hand: `MIGRATION_DATABASE_URL=… uv run python -m app.tools.migrate` | `backend/migrations/` |
| 7 | Set the `app_backend` role password (`alter role app_backend password '…'`), store it only in Railway secrets as `DATABASE_URL` using the **transaction pooler** (port 6543) | Appendix B.4 |
| 8 | Storage → create private buckets `menu-photos`, `qris-images`, `payment-proofs`, `attendance-selfies` with the size/MIME limits in `config.toml` | T-014, T-036, T-122 |
| 9 | API → exposed schemas stay `public`, `graphql_public` (never `app`) | Appendix B.4 |
| 10 | Pilot/production only: Pro plan, daily backups / PITR, and ADR 0001 accepted first | NFR1, T-114 |
| 11 | Platform admin: run `uv run python -m app.cli invite-owner --email … --invited-by …` for each new owner (needs `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`) | T-006 owner invitations |

Secrets never go into the repository. The service role (secret) key is used only for the Supabase Auth admin API, namely owner invitations (platform-admin CLI) and banning deactivated staff (API, T-012), and for private Storage objects: menu photo upload, signed URLs and removal (API, T-132). It is never used to read or write tenant table data, and lives in Railway secrets / the operator's machine.

## Deploy note: sample menu for existing tenants

The sample menu (FR2.12) is seeded only when an owner completes onboarding, so tenants created before Wave 2 get none. `app.seed_sample_menu` is not idempotent (it collides on `stock_items (tenant_id, name)`), so do not call it for a tenant that already has a menu or ingredients. For a demo tenant that has neither, run once as the database owner:

```sql
select app.seed_sample_menu('<tenant_id>', '<outlet_id>')
where not exists (select 1 from app.products where tenant_id = '<tenant_id>')
  and not exists (select 1 from app.stock_items where tenant_id = '<tenant_id>');
```
