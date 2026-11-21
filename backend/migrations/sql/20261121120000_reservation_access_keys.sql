-- T-061 (C12, FR9.5, AC9.12): a booking made on one phone can be opened on another with its
-- booking code + the phone number used for it. That phone gets its own access key, so the
-- first phone's key (`reservations.access_key_hash`) keeps working. Only SHA-256 hashes are
-- stored. The keys stop mattering once the booking is finished (the chat reads upcoming ones).
create table app.reservation_access_keys (
  id              bigint generated always as identity primary key,
  tenant_id       uuid not null,
  outlet_id       uuid not null,
  reservation_id  uuid not null,
  key_hash        text not null unique check (key_hash ~ '^[0-9a-f]{64}$'),
  created_at      timestamptz not null default now(),
  foreign key (reservation_id, outlet_id) references app.reservations (id, outlet_id)
);
create index on app.reservation_access_keys (reservation_id);

alter table app.reservation_access_keys enable row level security;
create policy outlet_scope on app.reservation_access_keys to app_backend
  using      (tenant_id = app.current_tenant() and app.can_access_outlet(outlet_id))
  with check (tenant_id = app.current_tenant() and app.can_access_outlet(outlet_id));
create policy no_device on app.reservation_access_keys as restrictive to app_backend
  using (app.current_actor() is distinct from 'device')
  with check (app.current_actor() is distinct from 'device');
grant select, insert on app.reservation_access_keys to app_backend;
