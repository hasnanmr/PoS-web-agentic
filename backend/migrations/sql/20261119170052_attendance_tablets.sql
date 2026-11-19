-- Wave 7c: outlet attendance tablets and the attendance domain (T-116, T-121, T-122).
--
-- K0 pairing: the owner creates a one-time 6-digit code (O3); the tablet trades it for a device
-- token (only its hash is stored). Every tablet request resolves the token through a SECURITY
-- DEFINER function, then runs as actor 'device' scoped to one outlet.
-- K1–K4: the tablet lists the outlet's staff and records clock in / clock out with a required
-- selfie. PoC demo: selfies are stored in the database (JPEG/WebP, max 2 MB), like the QRIS
-- image; the move to a private Supabase Storage bucket with signed URLs is a follow-up.

-- Device session ----------------------------------------------------------------------------
alter table app.attendance_devices add column token_hash text unique;

create function app.current_device_id() returns uuid
language sql stable set search_path = '' as $$
  select nullif(current_setting('app.device_id', true), '')::uuid
$$;

-- Selfies (T-122) -----------------------------------------------------------------------------
create table app.attendance_selfies (
  id           uuid primary key,
  tenant_id    uuid not null,
  outlet_id    uuid not null,
  device_id    uuid not null,
  content_type text not null check (content_type in ('image/jpeg', 'image/webp')),
  image        bytea not null check (octet_length(image) between 1 and 2097152),
  created_at   timestamptz not null default now(),
  foreign key (outlet_id, tenant_id) references app.outlets (id, tenant_id),
  foreign key (device_id, outlet_id) references app.attendance_devices (id, outlet_id)
);
create index on app.attendance_selfies (created_at);

-- Each clock-in and clock-out keeps its selfie; the 30-day purge deletes the photo and the
-- record stays (FR5.7), so the link goes null.
alter table app.attendance_records
  add column clock_in_selfie_id  uuid unique references app.attendance_selfies (id) on delete set null,
  add column clock_out_selfie_id uuid unique references app.attendance_selfies (id) on delete set null,
  add constraint selfies_differ check (clock_in_selfie_id <> clock_out_selfie_id);

-- Definer helpers -------------------------------------------------------------------------------
-- True when `p_user` is an active staff member assigned to `p_outlet` in the current tenant.
create function app.is_outlet_staff(p_user uuid, p_outlet uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from app.staff_outlets so
    join app.users u on u.id = so.user_id
    where so.user_id = p_user and so.outlet_id = p_outlet
      and u.tenant_id = app.current_tenant() and u.is_active and u.role = 'staff')
$$;

-- K1: staff of the tablet's outlet (the tablet cannot read app.users itself). `has_attendance`
-- = the person has clocked in before at any outlet, so K3 shows the first-use privacy notice.
create function app.device_outlet_staff()
returns table (user_id uuid, display_name text, has_attendance boolean)
language sql stable security definer set search_path = '' as $$
  select u.id, u.display_name,
         exists (select 1 from app.attendance_records r where r.user_id = u.id)
  from app.staff_outlets so
  join app.users u on u.id = so.user_id
  where app.current_actor() = 'device'
    and so.outlet_id = app.current_device_outlet()
    and u.tenant_id = app.current_tenant()
    and u.is_active and u.role = 'staff'
  order by u.display_name
$$;

-- O3 "+ Pairing tablet baru": store a new code hash. Expired or used codes with the same hash
-- (any tenant) are removed first; false when an active code already has this hash, and the
-- caller draws another code.
create function app.create_attendance_pairing_code(p_outlet uuid, p_code_hash text, p_expires_at timestamptz)
returns boolean
language plpgsql volatile security definer set search_path = '' as $$
begin
  if not app.is_owner() or not app.can_access_outlet(p_outlet) then
    raise exception 'owner only' using errcode = 'insufficient_privilege';
  end if;
  delete from app.attendance_pairing_codes
   where code_hash = p_code_hash and (used_at is not null or expires_at <= now());
  insert into app.attendance_pairing_codes (code_hash, tenant_id, outlet_id, created_by, expires_at)
  select p_code_hash, o.tenant_id, o.id, app.current_user_id(), p_expires_at
    from app.outlets o where o.id = p_outlet
  on conflict (code_hash) do nothing;
  return found;
end $$;

-- K0 "Hubungkan tablet": trade an unused, unexpired code for a device (one-time). No tenant is
-- known yet, so this is a definer function. Returns no row for a wrong, used, or expired code.
create function app.pair_attendance_device(p_code_hash text, p_token_hash text)
returns table (device_id uuid, tenant_id uuid, outlet_id uuid, device_name text,
               outlet_name text, timezone text)
language plpgsql volatile security definer set search_path = '' as $$
#variable_conflict use_column
declare
  c app.attendance_pairing_codes;
  v_id uuid;
  v_name text;
begin
  update app.attendance_pairing_codes p set used_at = now()
   where p.code_hash = p_code_hash and p.used_at is null and p.expires_at > now()
     and exists (select 1 from app.outlets o where o.id = p.outlet_id and o.is_active)
  returning p.* into c;
  if not found then
    return;
  end if;
  select 'Tablet ' || (count(*) + 1) into v_name
    from app.attendance_devices d where d.outlet_id = c.outlet_id;
  insert into app.attendance_devices (tenant_id, outlet_id, name, paired_by, token_hash, last_seen_at)
  values (c.tenant_id, c.outlet_id, v_name, c.created_by, p_token_hash, now())
  returning id into v_id;
  insert into app.audit_events (tenant_id, outlet_id, actor_type, actor_id, action, entity_type, entity_id, data)
  values (c.tenant_id, c.outlet_id, 'device', v_id, 'attendance_device.paired', 'attendance_device',
          v_id::text, jsonb_build_object('name', v_name, 'code_created_by', c.created_by));
  return query
    select v_id, c.tenant_id, c.outlet_id, v_name, o.name, o.timezone
      from app.outlets o where o.id = c.outlet_id;
end $$;

-- Every tablet request: find the device by token hash (any tenant). `revoked` is true once the
-- owner revoked it ("Cabut") or the outlet was deactivated. Updates last_seen_at at most once a
-- minute (O3 "aktif 2 menit lalu").
create function app.resolve_attendance_device(p_token_hash text)
returns table (device_id uuid, tenant_id uuid, outlet_id uuid, device_name text,
               outlet_name text, timezone text, revoked boolean)
language plpgsql volatile security definer set search_path = '' as $$
#variable_conflict use_column
begin
  update app.attendance_devices d set last_seen_at = now()
   where d.token_hash = p_token_hash and d.revoked_at is null
     and (d.last_seen_at is null or d.last_seen_at < now() - interval '1 minute');
  return query
    select d.id, d.tenant_id, d.outlet_id, d.name, o.name, o.timezone,
           d.revoked_at is not null or not o.is_active
      from app.attendance_devices d
      join app.outlets o on o.id = d.outlet_id
     where d.token_hash = p_token_hash;
end $$;

revoke execute on function app.is_outlet_staff(uuid, uuid) from public;
revoke execute on function app.device_outlet_staff() from public;
revoke execute on function app.create_attendance_pairing_code(uuid, text, timestamptz) from public;
revoke execute on function app.pair_attendance_device(text, text) from public;
revoke execute on function app.resolve_attendance_device(text) from public;
grant execute on function app.current_device_id(), app.is_outlet_staff(uuid, uuid),
  app.device_outlet_staff(), app.create_attendance_pairing_code(uuid, text, timestamptz),
  app.pair_attendance_device(text, text), app.resolve_attendance_device(text)
  to app_backend;

-- RLS ------------------------------------------------------------------------------------------
-- A tablet session may only list its outlet's staff and record attendance (T-121). The outlet
-- policies alone would let it read the outlet's orders, so every other table refuses the
-- 'device' actor. New tables must add the same policy (see supabase/tests/rls.sql).
do $$
declare
  t text;
begin
  for t in
    select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'app' and c.relkind = 'r' and c.relrowsecurity
       and c.relname not in ('outlets', 'attendance_records', 'attendance_events')
  loop
    execute format($p$
      create policy no_device on app.%I as restrictive to app_backend
        using (app.current_actor() is distinct from 'device')
        with check (app.current_actor() is distinct from 'device')
    $p$, t);
  end loop;
end $$;

-- Devices and pairing codes: owner (O3) and workers only; tablets go through the functions.
create policy owner_only on app.attendance_devices as restrictive to app_backend
  using (app.is_owner() or app.current_actor() = 'system')
  with check (app.is_owner() or app.current_actor() = 'system');
create policy owner_only on app.attendance_pairing_codes as restrictive to app_backend
  using (app.is_owner() or app.current_actor() = 'system')
  with check (app.is_owner() or app.current_actor() = 'system');

-- Records: staff read only their own (S9); the tablet clocks in only assigned staff, with its own
-- device id; staff tokens never write (clock in/out happens only on the tablet). Owner corrects,
-- the scheduler flags, the tablet clocks out. Nobody deletes.
create policy own_or_manager_read on app.attendance_records as restrictive for select to app_backend
  using (app.is_owner() or app.current_actor() in ('system', 'device')
         or user_id = app.current_user_id());
create policy device_clock_in on app.attendance_records as restrictive for insert to app_backend
  with check (app.current_actor() = 'device'
              and clock_in_device_id = app.current_device_id()
              and app.is_outlet_staff(user_id, outlet_id));
create policy managed_update on app.attendance_records as restrictive for update to app_backend
  using (app.is_owner() or app.current_actor() in ('system', 'device'))
  with check (app.is_owner() or app.current_actor() in ('system', 'device'));
revoke delete on app.attendance_records from app_backend;

create policy via_record on app.attendance_events as restrictive for select to app_backend
  using (exists (select 1 from app.attendance_records r where r.id = record_id));
create policy managed_insert on app.attendance_events as restrictive for insert to app_backend
  with check (app.is_owner() or app.current_actor() in ('system', 'device'));

-- Selfies: the tablet uploads (and reads back only its own uploads to link them); the owner and
-- the staff member in the photo read them; only the purge job deletes.
alter table app.attendance_selfies enable row level security;
create policy outlet_scope on app.attendance_selfies to app_backend
  using      (tenant_id = app.current_tenant() and app.can_access_outlet(outlet_id))
  with check (tenant_id = app.current_tenant() and app.can_access_outlet(outlet_id));
create policy selfie_read on app.attendance_selfies as restrictive for select to app_backend
  using (app.is_owner() or app.current_actor() = 'system'
         or (app.current_actor() = 'device' and device_id = app.current_device_id())
         or exists (select 1 from app.attendance_records r
                    where r.user_id = app.current_user_id()
                      and attendance_selfies.id in (r.clock_in_selfie_id, r.clock_out_selfie_id)));
create policy device_upload on app.attendance_selfies as restrictive for insert to app_backend
  with check (app.current_actor() = 'device' and device_id = app.current_device_id());
create policy purge_only on app.attendance_selfies as restrictive for delete to app_backend
  using (app.current_actor() = 'system');
grant select, insert, delete on app.attendance_selfies to app_backend;
