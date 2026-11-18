-- T-004: tenants, outlets, users, staff assignments, drawers, tables, devices, audit.
-- Every operational record carries tenant_id and outlet_id. Composite foreign keys
-- (outlet_id, tenant_id) -> outlets(id, tenant_id) make cross-tenant links impossible.

create table app.tenants (
  id          uuid primary key default gen_random_uuid(),
  name        text not null check (length(trim(name)) between 1 and 120),
  type        app.tenant_type not null,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create table app.outlets (
  id                       uuid primary key default gen_random_uuid(),
  tenant_id                uuid not null references app.tenants (id),
  name                     text not null check (length(trim(name)) between 1 and 120),
  address                  text,
  -- Default WIB (decision 2026-11-17). Only Indonesian zones are allowed.
  timezone                 text not null default 'Asia/Jakarta'
                           check (timezone in ('Asia/Jakarta', 'Asia/Makassar', 'Asia/Jayapura')),
  whatsapp_phone           text unique check (whatsapp_phone ~ '^\+?[0-9]{8,15}$'),
  whatsapp_phone_number_id text unique,          -- Meta phone number id
  whatsapp_catalog_id      text,
  -- O3/O12: connection and catalog sync status shown per outlet.
  whatsapp_status          text not null default 'not_started'
                           check (whatsapp_status in ('not_started', 'pending_verification', 'connected', 'error')),
  catalog_synced_at        timestamptz,
  -- Order number prefix shown as #A-1036 (S2, O11); unique per tenant.
  order_prefix             text not null default 'A' check (order_prefix ~ '^[A-Z]{1,3}$'),
  payment_mode             app.payment_mode not null default 'pay_first',
  delivery_fee             bigint not null default 0 check (delivery_fee >= 0),
  -- PB1: off by default, rate decided per outlet by the owner (rate still TBD).
  pb1_enabled              boolean not null default false,
  pb1_rate_bps             integer check (pb1_rate_bps between 1 and 1000),
  unpaid_timeout_minutes   integer not null default 15 check (unpaid_timeout_minutes between 1 and 1440),
  attendance_grace_minutes integer not null default 60 check (attendance_grace_minutes between 0 and 720),
  qris_image_path          text,                 -- private Supabase Storage object path (T-014)
  is_active                boolean not null default true,
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now(),
  unique (id, tenant_id),
  unique (tenant_id, order_prefix),
  constraint pb1_rate_required check (not pb1_enabled or pb1_rate_bps is not null)
);
create index on app.outlets (tenant_id);

create table app.outlet_opening_hours (
  outlet_id   uuid not null,
  tenant_id   uuid not null,
  weekday     smallint not null check (weekday between 1 and 7),  -- ISO: 1 = Monday
  opens_at    time not null,
  closes_at   time not null,   -- closes_at <= opens_at means the outlet closes after midnight
  primary key (outlet_id, weekday),
  foreign key (outlet_id, tenant_id) references app.outlets (id, tenant_id) on delete cascade
);

create table app.reservation_settings (
  outlet_id                 uuid primary key,
  tenant_id                 uuid not null,
  is_enabled                boolean not null default false,
  bookable_from             time not null default '10:00',
  bookable_until            time not null default '20:00',
  default_duration_minutes  integer not null default 90 check (default_duration_minutes between 15 and 600),
  booking_window_days       integer not null default 14 check (booking_window_days between 0 and 365),
  max_party_size            integer not null default 10 check (max_party_size between 1 and 100),
  reminder_offset_minutes   integer not null default 120 check (reminder_offset_minutes between 0 and 2880),
  cancellation_cutoff_minutes integer not null default 120 check (cancellation_cutoff_minutes between 0 and 2880),
  updated_at                timestamptz not null default now(),
  foreign key (outlet_id, tenant_id) references app.outlets (id, tenant_id) on delete cascade
);

-- users.id equals auth.users.id (Supabase Auth). The FK to auth.users is added
-- in T-113 so these migrations also run on plain PostgreSQL for CI.
create table app.users (
  id           uuid primary key,
  tenant_id    uuid not null references app.tenants (id),
  email        text not null check (email ~* '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
  display_name text not null,
  role         app.user_role not null,
  is_active    boolean not null default true,
  invited_at   timestamptz,
  invitation_accepted_at timestamptz,   -- null = still 'Diundang' (O4)
  deactivated_at timestamptz,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  unique (id, tenant_id)
);
create unique index users_email_key on app.users (lower(email));
create index on app.users (tenant_id);

create table app.staff_outlets (
  user_id    uuid not null,
  outlet_id  uuid not null,
  tenant_id  uuid not null,
  created_at timestamptz not null default now(),
  primary key (user_id, outlet_id),
  foreign key (user_id, tenant_id)   references app.users (id, tenant_id) on delete cascade,
  foreign key (outlet_id, tenant_id) references app.outlets (id, tenant_id) on delete cascade
);
create index on app.staff_outlets (outlet_id);

create table app.cash_drawers (
  id         uuid primary key default gen_random_uuid(),
  tenant_id  uuid not null,
  outlet_id  uuid not null,
  name       text not null check (length(trim(name)) between 1 and 60),
  is_active  boolean not null default true,
  created_at timestamptz not null default now(),
  unique (outlet_id, name),
  unique (id, outlet_id),
  foreign key (outlet_id, tenant_id) references app.outlets (id, tenant_id)
);

create table app.tables (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null,
  outlet_id    uuid not null,
  name         text not null check (length(trim(name)) between 1 and 30),
  capacity     integer not null check (capacity between 1 and 100),
  area         text,
  is_bookable  boolean not null default true,
  qr_token     text not null unique default replace(gen_random_uuid()::text, '-', ''),
  is_active    boolean not null default true,
  created_at   timestamptz not null default now(),
  unique (outlet_id, name),
  unique (id, outlet_id),
  foreign key (outlet_id, tenant_id) references app.outlets (id, tenant_id)
);

-- Outlet attendance tablets (FR5.6, T-121).
create table app.attendance_devices (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null,
  outlet_id     uuid not null,
  name          text not null,
  paired_by     uuid not null references app.users (id),
  paired_at     timestamptz not null default now(),
  last_seen_at  timestamptz,
  revoked_at    timestamptz,
  revoked_by    uuid references app.users (id),
  unique (id, outlet_id),
  foreign key (outlet_id, tenant_id) references app.outlets (id, tenant_id)
);

create table app.attendance_pairing_codes (
  code_hash   text primary key,               -- store a hash, never the code
  tenant_id   uuid not null,
  outlet_id   uuid not null,
  created_by  uuid not null references app.users (id),
  expires_at  timestamptz not null,
  used_at     timestamptz,
  foreign key (outlet_id, tenant_id) references app.outlets (id, tenant_id)
);

-- Generic audit trail for administrative actions (settings, staff, replay of
-- dead letters, etc.). Domain events (orders, reservations, attendance) have
-- their own event tables. outlet_id is null for tenant-level actions.
create table app.audit_events (
  id          bigint generated always as identity primary key,
  tenant_id   uuid references app.tenants (id),
  outlet_id   uuid,
  actor_type  app.actor_type not null,
  actor_id    uuid,                            -- user or device id; null for system/agent
  action      text not null,                   -- e.g. 'outlet.updated', 'dlq.replayed'
  entity_type text not null,
  entity_id   text,
  reason      text,
  data        jsonb not null default '{}'::jsonb,
  created_at  timestamptz not null default now(),
  constraint audit_actor_id check (actor_type in ('system', 'agent') or actor_id is not null)
);
create index on app.audit_events (tenant_id, created_at desc);

create trigger touch before update on app.tenants  for each row execute function app.touch_updated_at();
create trigger touch before update on app.outlets  for each row execute function app.touch_updated_at();
create trigger touch before update on app.users    for each row execute function app.touch_updated_at();
create trigger touch before update on app.reservation_settings for each row execute function app.touch_updated_at();
