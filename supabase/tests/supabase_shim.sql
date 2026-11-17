-- Minimal stand-ins for objects that exist on Supabase but not on plain PostgreSQL,
-- so CI can run the migrations and tests without the Supabase stack.
-- Never run this against a Supabase database (scripts/db-test.sh skips it when
-- auth.users already exists).

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'supabase_auth_admin') then
    create role supabase_auth_admin nologin;
  end if;
end $$;

create schema if not exists auth;
create table if not exists auth.users (
  id    uuid primary key,
  email text
);
