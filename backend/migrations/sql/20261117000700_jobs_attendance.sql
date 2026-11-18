-- T-004: scheduled jobs (Appendix A.4) and staff attendance (FR5.1–FR5.7).

create table app.scheduled_jobs (
  id            bigint generated always as identity primary key,
  job_key       text not null unique,      -- idempotency key, e.g. 'unpaid_timeout:<order_id>'
  type          app.scheduled_job_type not null,
  tenant_id     uuid references app.tenants (id),
  outlet_id     uuid,
  run_at        timestamptz not null,
  status        app.scheduled_job_status not null default 'pending',
  payload       jsonb not null default '{}'::jsonb,
  attempts      integer not null default 0,
  last_error    text,
  enqueued_at   timestamptz,
  finished_at   timestamptz,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
-- Poller query: due pending jobs, FOR UPDATE SKIP LOCKED (T-104).
create index scheduled_jobs_due on app.scheduled_jobs (run_at) where status = 'pending';

create table app.attendance_records (
  id                 uuid primary key default gen_random_uuid(),
  tenant_id          uuid not null,
  outlet_id          uuid not null,
  user_id            uuid not null,
  status             app.attendance_record_status not null default 'open',
  clock_in_at        timestamptz not null,
  clock_in_device_id uuid not null,
  clock_in_photo_path text,                -- null after the 30-day purge (FR5.7)
  clock_out_at       timestamptz,
  clock_out_device_id uuid,
  clock_out_photo_path text,
  flagged_at         timestamptz,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  unique (id, outlet_id),
  foreign key (outlet_id, tenant_id) references app.outlets (id, tenant_id),
  foreign key (user_id, tenant_id)   references app.users (id, tenant_id),
  foreign key (clock_in_device_id, outlet_id)  references app.attendance_devices (id, outlet_id),
  foreign key (clock_out_device_id, outlet_id) references app.attendance_devices (id, outlet_id),
  constraint clock_out_after_in check (clock_out_at is null or clock_out_at > clock_in_at),
  constraint closed_has_clock_out check (status <> 'closed' or clock_out_at is not null)
);
-- One open record per staff member (FR5.1). Flagged records do not block a new clock-in (FR5.3).
create unique index attendance_one_open on app.attendance_records (user_id) where status = 'open';
create index on app.attendance_records (outlet_id, clock_in_at);

-- Append-only attendance history; corrections keep the original values (FR5.4).
create table app.attendance_events (
  id           bigint generated always as identity primary key,
  tenant_id    uuid not null,
  outlet_id    uuid not null,
  record_id    uuid not null,
  type         app.attendance_event_type not null,
  data         jsonb not null default '{}'::jsonb,   -- old/new values for corrections
  reason       text,
  actor_type   app.actor_type not null,
  actor_id     uuid,
  created_at   timestamptz not null default now(),
  foreign key (record_id, outlet_id) references app.attendance_records (id, outlet_id),
  constraint correction_reason check (type <> 'correction' or coalesce(length(trim(reason)), 0) > 0),
  constraint event_actor check (actor_type in ('system', 'agent') or actor_id is not null)
);
create index on app.attendance_events (record_id, created_at);

create trigger append_only before update or delete on app.attendance_events
  for each row execute function app.reject_update_delete();
create trigger touch before update on app.scheduled_jobs     for each row execute function app.touch_updated_at();
create trigger touch before update on app.attendance_records for each row execute function app.touch_updated_at();
