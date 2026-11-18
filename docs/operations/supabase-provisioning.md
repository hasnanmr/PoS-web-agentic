# Supabase provisioning checklist (T-079)

Status (2026-11-18): the first cloud project is [PoS-web-agentic](https://supabase.com/dashboard/project/igesdngvyyhmbvjclwgi) in Singapore. Its environment designation still needs to be recorded; use separate projects for `demo`, `staging`, and `production` when those environments exist.

Completed on this project: all 11 repository migrations (with matching migration versions), invite-only Auth, the `app.custom_access_token_hook`, 900-second access tokens, `http://localhost:5170` as the Auth Site URL and Redirect URL, and four private Storage buckets. The current JWT signing key is ECC P-256. The admin app's local publishable key and project URL are in the ignored `admin/.env.local` file.

The `app_backend` role password and transaction-pooler URL are in the ignored local `backend/.env`, together with the Supabase URL/JWKS/issuer. A read-only connection as `app_backend` succeeded. Still required before end-to-end owner invitations: set `SUPABASE_SERVICE_ROLE_KEY` in the backend's local/deployment secrets, copy the backend variables to deployment secrets when deployed, and replace the local Auth URL with the hosted admin URL. The legacy HS256 signing key is still listed as a previous key; revoke it after confirming no clients depend on it. Do not run `supabase/seed.sql` on this project.

| Step | Setting | Source of truth |
|---|---|---|
| 1 | Create project, region **Singapore**, Postgres major version recorded in `supabase/config.toml` `[db] major_version` | ADR 0001 |
| 2 | Auth → disable public sign-ups (invite-only) | `config.toml [auth] enable_signup = false` |
| 3 | Auth → JWT signing keys: create an **asymmetric** key (ES256 or RS256), make it current, revoke the legacy shared secret once nothing uses it | T-113, `backend/.env.example` (`SUPABASE_JWKS_URL`, `SUPABASE_JWT_ISSUER`) |
| 4 | Auth → access token expiry 900 s; refresh token rotation on | `config.toml [auth]` |
| 5 | Auth → Hooks → Custom Access Token → Postgres function `app.custom_access_token_hook` | migration `..._auth_roles_hook.sql` |
| 6 | Run migrations: `supabase link --project-ref <ref>` then `supabase db push` (session-mode/direct connection) | `supabase/migrations/` |
| 7 | Set the `app_backend` role password (`alter role app_backend password '…'`), store it only in Railway secrets as `DATABASE_URL` using the **transaction pooler** (port 6543) | Appendix B.4 |
| 8 | Storage → create private buckets `menu-photos`, `qris-images`, `payment-proofs`, `attendance-selfies` with the size/MIME limits in `config.toml` | T-014, T-036, T-122 |
| 9 | API → exposed schemas stay `public`, `graphql_public` (never `app`) | Appendix B.4 |
| 10 | Pilot/production only: Pro plan, daily backups / PITR, and ADR 0001 accepted first | NFR1, T-114 |
| 11 | Platform admin: run `uv run python -m app.cli invite-owner --email … --invited-by …` for each new owner (needs `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`) | T-006 owner invitations |

Secrets never go into the repository. The service role key is used only for the Supabase Auth admin API: owner invitations (platform-admin CLI) and banning deactivated staff (API, T-012). It is never used to read or write tenant data, and lives in Railway secrets / the operator's machine.
