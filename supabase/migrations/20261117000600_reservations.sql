-- T-004: reservations and reservation events.
-- No overlapping active bookings on one table, enforced by the database (FR9.3).

create table app.reservations (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null,
  outlet_id     uuid not null,
  table_id      uuid not null,
  contact_id    uuid,
  guest_name    text,                      -- personal data for phone/in-person bookings
  guest_phone   text,
  party_size    integer not null check (party_size between 1 and 100),
  starts_at     timestamptz not null,
  ends_at       timestamptz not null,
  source        app.reservation_source not null,
  status        app.reservation_status not null default 'booked',
  created_by_actor app.actor_type not null,
  created_by_id uuid,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  unique (id, outlet_id),
  foreign key (outlet_id, tenant_id)  references app.outlets (id, tenant_id),
  foreign key (table_id, outlet_id)   references app.tables (id, outlet_id),
  foreign key (contact_id, tenant_id) references app.whatsapp_contacts (id, tenant_id),
  constraint valid_range check (ends_at > starts_at),
  constraint walk_in_seated check (source <> 'walk_in' or status in ('seated', 'completed', 'cancelled')),
  constraint creator check (created_by_actor in ('system', 'agent') or created_by_id is not null),
  constraint no_overlap exclude using gist (
    table_id with =,
    tstzrange(starts_at, ends_at, '[)') with &&
  ) where (status in ('booked', 'seated'))
);
create index on app.reservations (outlet_id, starts_at);
create index on app.reservations (contact_id) where contact_id is not null;

create table app.reservation_events (
  id              bigint generated always as identity primary key,
  tenant_id       uuid not null,
  outlet_id       uuid not null,
  reservation_id  uuid not null,
  event           text not null,          -- 'created', 'status_changed', 'table_changed', 'rescheduled'
  from_status     app.reservation_status,
  to_status       app.reservation_status,
  data            jsonb not null default '{}'::jsonb,
  actor_type      app.actor_type not null,
  actor_id        uuid,
  created_at      timestamptz not null default now(),
  foreign key (reservation_id, outlet_id) references app.reservations (id, outlet_id),
  constraint event_actor check (actor_type in ('system', 'agent') or actor_id is not null)
);
create index on app.reservation_events (reservation_id, created_at);

create trigger append_only before update or delete on app.reservation_events
  for each row execute function app.reject_update_delete();
create trigger touch before update on app.reservations for each row execute function app.touch_updated_at();
