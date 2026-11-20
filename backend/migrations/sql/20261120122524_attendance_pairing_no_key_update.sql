-- attendance_pairing_no_key_update (PR #35 review, notes 1 and 2)
--
-- 1. Lock the outlet with `for no key update` instead of `for update`: `for update` conflicts with
--    the `for key share` lock taken by every FK insert into outlets (orders, shifts, ...), so
--    pairing would serialise against unrelated short transactions. Same serialisation for
--    pairings, without that interference.
-- 2. Name the tablet from the *active* devices only. Counting every device meant a replacement
--    tablet became "Tablet 2", "Tablet 3", ... while the outlet only ever has one active tablet.
--
-- Same signature as in 20261119170052 / 20261120104500, so `create or replace` keeps the existing
-- grants (revoke from public, grant to app_backend).

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
  -- `no key update` gives that serialisation without clashing with FK `for key share` locks.
  -- Raising rolls back the code's used_at, so the code still works once the old tablet is gone.
  perform 1 from app.outlets o where o.id = c.outlet_id for no key update;
  if exists (select 1 from app.attendance_devices d
              where d.outlet_id = c.outlet_id and d.revoked_at is null) then
    raise exception 'this outlet already has an attendance tablet'
      using errcode = 'unique_violation', constraint = 'attendance_devices_one_active_per_outlet';
  end if;
  -- Only active devices count: forgotten tablets must not push the number up (under the
  -- one-tablet rule the replacement is named "Tablet 1", like the tablet it replaces).
  select 'Tablet ' || (count(*) + 1) into v_name
    from app.attendance_devices d where d.outlet_id = c.outlet_id and d.revoked_at is null;
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
