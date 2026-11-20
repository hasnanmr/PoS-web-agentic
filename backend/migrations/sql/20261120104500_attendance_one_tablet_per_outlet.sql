-- O3 "Tablet absensi" / K0: an outlet has at most one active (not forgotten) attendance tablet.
-- To replace a tablet the owner first taps "Lupakan perangkat" (POST .../revoke), then makes a
-- new pairing code. Both functions below refuse while the outlet still has an active tablet,
-- raising unique_violation with constraint `attendance_devices_one_active_per_outlet`, which the
-- API maps to 409 `tablet_already_paired`.
--
-- No unique index: outlets that already have several active tablets keep them (nobody is locked
-- out of clocking in); new pairing is blocked until the owner forgets them all. The pairing
-- function locks the outlet row, so two codes used at the same moment cannot both pair.

create or replace function app.create_attendance_pairing_code(p_outlet uuid, p_code_hash text, p_expires_at timestamptz)
returns boolean
language plpgsql volatile security definer set search_path = '' as $$
begin
  if not app.is_owner() or not app.can_access_outlet(p_outlet) then
    raise exception 'owner only' using errcode = 'insufficient_privilege';
  end if;
  if exists (select 1 from app.attendance_devices d
              where d.outlet_id = p_outlet and d.revoked_at is null) then
    raise exception 'this outlet already has an attendance tablet'
      using errcode = 'unique_violation', constraint = 'attendance_devices_one_active_per_outlet';
  end if;
  delete from app.attendance_pairing_codes
   where code_hash = p_code_hash and (used_at is not null or expires_at <= now());
  insert into app.attendance_pairing_codes (code_hash, tenant_id, outlet_id, created_by, expires_at)
  select p_code_hash, o.tenant_id, o.id, app.current_user_id(), p_expires_at
    from app.outlets o where o.id = p_outlet
  on conflict (code_hash) do nothing;
  return found;
end $$;

create or replace function app.pair_attendance_device(p_code_hash text, p_token_hash text)
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
  -- One active tablet per outlet; the lock serialises concurrent pairings of the same outlet.
  -- Raising rolls back the code's used_at, so the code still works once the old tablet is gone.
  perform 1 from app.outlets o where o.id = c.outlet_id for update;
  if exists (select 1 from app.attendance_devices d
              where d.outlet_id = c.outlet_id and d.revoked_at is null) then
    raise exception 'this outlet already has an attendance tablet'
      using errcode = 'unique_violation', constraint = 'attendance_devices_one_active_per_outlet';
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
