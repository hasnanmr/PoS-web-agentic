-- Wave 7c-2: attendance reports (O14), own history (S9/M6), missing clock-out flag (T-118),
-- 45-day selfie purge (T-122).

-- S9 "tablet “Kasir Dago”": staff may see the name of the tablet that recorded their own
-- attendance, but not the device list (owner only, it holds token hashes).
create function app.attendance_device_names(p_ids uuid[])
returns table (id uuid, name text)
language sql stable security definer set search_path = '' as $$
  select d.id, d.name from app.attendance_devices d
  where d.id = any (p_ids) and d.tenant_id = app.current_tenant()
    and app.current_actor() = 'user'
    and (app.is_owner() or exists (
          select 1 from app.attendance_records r
          where r.user_id = app.current_user_id()
            and d.id in (r.clock_in_device_id, r.clock_out_device_id)))
$$;
revoke execute on function app.attendance_device_names(uuid[]) from public;
grant execute on function app.attendance_device_names(uuid[]) to app_backend;

-- The missing clock-out check (app.core.attendance_reports.run_due_checks) scans a tenant's
-- open records on every attendance request until the T-104 scheduler exists.
create index attendance_open_records on app.attendance_records (tenant_id) where status = 'open';

-- Selfie deletion (product owner, 2026-11-20): kept 45 days, then the purge deletes them. The
-- owner may also delete one through DELETE /owner/attendance/{id}/selfies/{in|out} (no screen
-- yet). Staff can never delete a selfie, not even their own.
drop policy purge_only on app.attendance_selfies;
create policy owner_or_purge_delete on app.attendance_selfies as restrictive for delete to app_backend
  using (app.is_owner() or app.current_actor() = 'system');
