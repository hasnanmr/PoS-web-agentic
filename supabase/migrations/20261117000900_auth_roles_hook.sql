-- T-113: JWT claim contract, custom access token hook, backend DB role,
-- request-context helpers, and platform-admin owner invitations.
-- Design: Task breakdown Appendix B. Owner invitations: product-owner decision
-- 2026-11-17 ("admin platform invites every new owner").
--
-- Supabase-specific roles (anon, authenticated, supabase_auth_admin) and the
-- auth.users table are referenced only when they exist, so these migrations also
-- run on plain PostgreSQL in CI (with supabase/tests/supabase_shim.sql).

-- Backend role --------------------------------------------------------------
-- FastAPI and workers connect as app_backend: not superuser, not BYPASSRLS, and
-- not the owner of any table, so RLS always applies to it. The password is set
-- out of band (docs/operations/supabase-provisioning.md, step 7).
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'app_backend') then
    create role app_backend login noinherit nosuperuser nocreatedb nocreaterole nobypassrls;
  end if;
end $$;

grant usage on schema app to app_backend;

-- Platform-admin owner invitations -------------------------------------------
-- A platform admin invites each new owner (Supabase invite email). Until the
-- owner completes onboarding (O1, T-010) there is no app.users row and no tenant.
create table app.owner_invitations (
  id            uuid primary key default gen_random_uuid(),
  email         text not null check (email ~* '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
  auth_user_id  uuid not null unique,      -- Supabase Auth user created by the invite
  invited_by    text not null,             -- platform admin identifier (not a tenant user)
  note          text,
  invited_at    timestamptz not null default now(),
  revoked_at    timestamptz,
  accepted_at   timestamptz,               -- set when onboarding creates the tenant
  tenant_id     uuid references app.tenants (id),
  constraint accepted_has_tenant check ((accepted_at is null) = (tenant_id is null))
);
create unique index owner_invitations_open_email on app.owner_invitations (lower(email))
  where accepted_at is null and revoked_at is null;

-- Link app.users to Supabase Auth users when the auth schema exists.
do $$
begin
  if to_regclass('auth.users') is not null then
    alter table app.users
      add constraint users_auth_user_fk foreign key (id) references auth.users (id) on delete cascade;
    alter table app.owner_invitations
      add constraint owner_invitations_auth_user_fk foreign key (auth_user_id) references auth.users (id) on delete cascade;
  end if;
end $$;

-- Request context helpers ------------------------------------------------------
-- The backend sets these per transaction with set_config(..., true) from the
-- verified token or the worker job (Appendix B.4, B.6). Missing values make the
-- helpers return null, so policies return no rows instead of all rows.
create function app.current_tenant() returns uuid
language sql stable as $$ select nullif(current_setting('app.tenant_id', true), '')::uuid $$;

create function app.current_user_id() returns uuid
language sql stable as $$ select nullif(current_setting('app.user_id', true), '')::uuid $$;

create function app.current_actor() returns text
language sql stable as $$ select nullif(current_setting('app.actor', true), '') $$;

create function app.current_device_outlet() returns uuid
language sql stable as $$ select nullif(current_setting('app.device_outlet_id', true), '')::uuid $$;

-- True when the current request may touch outlet `o`. The caller's policy also
-- checks tenant_id = current_tenant(). SECURITY DEFINER (owned by the migration
-- role, which owns the tables and is exempt from their RLS) avoids policy recursion.
create function app.can_access_outlet(o uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from app.outlets ou
    where ou.id = o
      and ou.tenant_id = app.current_tenant()
      and (
        app.current_actor() in ('system', 'agent')
        or (app.current_actor() = 'device' and o = app.current_device_outlet())
        or (app.current_actor() = 'user' and exists (
              select 1 from app.users u
              where u.id = app.current_user_id() and u.tenant_id = ou.tenant_id
                and u.is_active and u.role = 'owner'))
        or (app.current_actor() = 'user' and exists (
              select 1 from app.staff_outlets so
              join app.users u on u.id = so.user_id
              where so.outlet_id = o and so.user_id = app.current_user_id() and u.is_active))
      )
  )
$$;

create function app.is_owner() returns boolean
language sql stable security definer set search_path = '' as $$
  select app.current_actor() = 'user' and exists (
    select 1 from app.users u
    where u.id = app.current_user_id() and u.tenant_id = app.current_tenant()
      and u.is_active and u.role = 'owner')
$$;

-- Cross-tenant lookups (the only ones) -----------------------------------------
-- Webhook: find tenant and outlet from the receiving WhatsApp phone number id
-- before any tenant is known (Appendix B.6). Returns ids only.
create function app.resolve_outlet_by_phone_number_id(p_phone_number_id text)
returns table (tenant_id uuid, outlet_id uuid)
language sql stable security definer set search_path = '' as $$
  select o.tenant_id, o.id from app.outlets o
  where o.whatsapp_phone_number_id = p_phone_number_id and o.is_active
$$;

-- Scheduler poller: claim due jobs across tenants (Appendix A.4, T-104).
create function app.claim_due_jobs(p_limit integer default 100)
returns setof app.scheduled_jobs
language sql volatile security definer set search_path = '' as $$
  with due as (
    select id from app.scheduled_jobs
    where status = 'pending' and run_at <= now()
    order by run_at
    limit p_limit
    for update skip locked
  )
  update app.scheduled_jobs j
     set status = 'enqueued', enqueued_at = now(), attempts = j.attempts + 1
    from due where j.id = due.id
  returning j.*
$$;

-- Platform admin: record an invitation after the Supabase invite call succeeds.
create function app.record_owner_invitation(p_email text, p_auth_user_id uuid, p_invited_by text, p_note text default null)
returns uuid
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_id uuid;
begin
  if exists (select 1 from app.users where id = p_auth_user_id) then
    raise exception 'auth user % already belongs to a tenant', p_auth_user_id using errcode = 'unique_violation';
  end if;
  insert into app.owner_invitations (email, auth_user_id, invited_by, note)
  values (lower(p_email), p_auth_user_id, p_invited_by, p_note)
  returning id into v_id;
  insert into app.audit_events (tenant_id, actor_type, action, entity_type, entity_id, data)
  values (null, 'system', 'owner.invited', 'owner_invitation', v_id::text,
          jsonb_build_object('email', lower(p_email), 'invited_by', p_invited_by));
  return v_id;
end $$;

create function app.revoke_owner_invitation(p_invitation_id uuid, p_invited_by text, p_reason text)
returns void
language plpgsql volatile security definer set search_path = '' as $$
begin
  if coalesce(length(trim(p_reason)), 0) = 0 then
    raise exception 'reason is required' using errcode = 'check_violation';
  end if;
  update app.owner_invitations set revoked_at = now()
  where id = p_invitation_id and accepted_at is null and revoked_at is null;
  if not found then
    raise exception 'no open invitation %', p_invitation_id using errcode = 'no_data_found';
  end if;
  insert into app.audit_events (tenant_id, actor_type, action, entity_type, entity_id, reason, data)
  values (null, 'system', 'owner.invitation_revoked', 'owner_invitation', p_invitation_id::text, p_reason,
          jsonb_build_object('by', p_invited_by));
end $$;

-- API: live check for an invited owner who has not onboarded yet (O1, /me).
create function app.pending_owner_invitation(p_auth_user_id uuid)
returns table (invitation_id uuid, email text, invited_at timestamptz)
language sql stable security definer set search_path = '' as $$
  select id, email, invited_at from app.owner_invitations
  where auth_user_id = p_auth_user_id and accepted_at is null and revoked_at is null
$$;

-- Custom access token hook (Appendix B.2) -------------------------------------
-- Claims: tenant_id + app_role ('owner' | 'staff') for tenant users;
-- app_role 'owner_pending' (no tenant_id) for an invited owner who has not
-- created the business yet (O1). Everyone else is refused.
create function app.custom_access_token_hook(event jsonb) returns jsonb
language plpgsql stable security definer set search_path = '' as $$
declare
  claims  jsonb := event->'claims';
  uid     uuid := (event->>'user_id')::uuid;
  u       record;
begin
  select tenant_id, role, is_active into u from app.users where id = uid;

  if found then
    if not u.is_active then
      return jsonb_build_object('error', jsonb_build_object('http_code', 403, 'message', 'account_inactive'));
    end if;
    claims := jsonb_set(claims, '{tenant_id}', to_jsonb(u.tenant_id::text));
    claims := jsonb_set(claims, '{app_role}', to_jsonb(u.role::text));
    return jsonb_set(event, '{claims}', claims);
  end if;

  if exists (select 1 from app.owner_invitations
             where auth_user_id = uid and accepted_at is null and revoked_at is null) then
    claims := claims - 'tenant_id';
    claims := jsonb_set(claims, '{app_role}', to_jsonb('owner_pending'::text));
    return jsonb_set(event, '{claims}', claims);
  end if;

  return jsonb_build_object('error', jsonb_build_object('http_code', 403, 'message', 'account_not_invited'));
end $$;

revoke execute on function app.custom_access_token_hook(jsonb) from public;
revoke execute on function app.record_owner_invitation(text, uuid, text, text) from public;
revoke execute on function app.revoke_owner_invitation(uuid, text, text) from public;
revoke execute on function app.claim_due_jobs(integer) from public;
revoke execute on function app.resolve_outlet_by_phone_number_id(text) from public;
revoke execute on function app.pending_owner_invitation(uuid) from public;

grant execute on function app.current_tenant(), app.current_user_id(), app.current_actor(),
  app.current_device_outlet(), app.can_access_outlet(uuid), app.is_owner() to app_backend;
grant execute on function app.claim_due_jobs(integer), app.resolve_outlet_by_phone_number_id(text),
  app.pending_owner_invitation(uuid),
  app.record_owner_invitation(text, uuid, text, text), app.revoke_owner_invitation(uuid, text, text)
  to app_backend;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'supabase_auth_admin') then
    grant usage on schema app to supabase_auth_admin;
    grant execute on function app.custom_access_token_hook(jsonb) to supabase_auth_admin;
  end if;
  -- The Data API roles get nothing from schema app.
  if exists (select 1 from pg_roles where rolname = 'anon') then
    revoke all on schema app from anon;
  end if;
  if exists (select 1 from pg_roles where rolname = 'authenticated') then
    revoke all on schema app from authenticated;
  end if;
end $$;
revoke all on schema app from public;
