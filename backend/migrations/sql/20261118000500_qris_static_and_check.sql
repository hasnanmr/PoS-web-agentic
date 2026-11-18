-- PoC demo: static QRIS per outlet (O3 "QRIS statis outlet") and the staff cross-check of
-- QRIS payments against the receiving account, from the Order Board (S2).

-- O3: the outlet's static QRIS image, uploaded by the owner and shown at the counter (S1)
-- and when a bill is closed (S5) so the customer can scan it. Stored in the database for the
-- PoC (PNG/JPG, max 2 MB); moving it to Supabase Storage (outlets.qris_image_path) is a
-- follow-up.
create table app.outlet_qris (
  outlet_id    uuid primary key,
  tenant_id    uuid not null,
  filename     text not null check (length(filename) between 1 and 200),
  content_type text not null check (content_type in ('image/png', 'image/jpeg')),
  image        bytea not null check (octet_length(image) between 1 and 2097152),
  uploaded_by  uuid not null references app.users (id),
  uploaded_at  timestamptz not null default now(),
  foreign key (outlet_id, tenant_id) references app.outlets (id, tenant_id) on delete cascade
);

alter table app.outlet_qris enable row level security;
-- Staff of the outlet read it (they show it to customers); only the owner writes it.
create policy outlet_scope on app.outlet_qris to app_backend
  using      (tenant_id = app.current_tenant() and app.can_access_outlet(outlet_id))
  with check (tenant_id = app.current_tenant() and app.can_access_outlet(outlet_id) and app.is_owner());
grant select, insert, update on app.outlet_qris to app_backend;

-- S2: "Saya sudah menemukan transaksi ini di akun merchant QRIS". A QRIS payment taken at
-- the counter or when closing a bill is recorded at once (the order goes to the kitchen);
-- staff confirm it later against the receiving account. One check per payment, append-only.
create table app.qris_checks (
  payment_id  uuid primary key references app.payments (id),
  tenant_id   uuid not null,
  outlet_id   uuid not null,
  checked_by  uuid not null references app.users (id),
  checked_at  timestamptz not null default now(),
  foreign key (outlet_id, tenant_id) references app.outlets (id, tenant_id)
);

alter table app.qris_checks enable row level security;
create policy outlet_scope on app.qris_checks to app_backend
  using      (tenant_id = app.current_tenant() and app.can_access_outlet(outlet_id))
  with check (tenant_id = app.current_tenant() and app.can_access_outlet(outlet_id));
grant select, insert on app.qris_checks to app_backend;
