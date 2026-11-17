# Supabase provisioning checklist (T-079)

Status: **config only** — accounts are not created yet (2026-11-17). Run this list when the Supabase account exists. One project per environment: `demo`, `staging`, `production`.

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
