-- T-004: bills, orders, items, events, payments, proofs, shifts, ledger.
-- Money is bigint whole rupiah; totals are not rounded (decision 2026-11-17).

create table app.cashier_shifts (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null,
  outlet_id        uuid not null,
  drawer_id        uuid not null,
  status           app.cashier_shift_status not null default 'open',
  opened_by        uuid not null references app.users (id),
  opened_at        timestamptz not null default now(),
  starting_cash    bigint not null check (starting_cash >= 0),
  closed_by        uuid references app.users (id),
  closed_at        timestamptz,
  counted_cash     bigint check (counted_cash >= 0),
  count_breakdown  jsonb,               -- S8: {"100000": 12, "50000": 6, ..., "coins": 4400}
  expected_cash    bigint,
  difference       bigint,              -- counted - expected; negative = shortage
  unique (id, outlet_id),
  foreign key (outlet_id, tenant_id) references app.outlets (id, tenant_id),
  foreign key (drawer_id, outlet_id) references app.cash_drawers (id, outlet_id),
  constraint closed_fields check (
    (status = 'open'   and closed_at is null and counted_cash is null) or
    (status = 'closed' and closed_at is not null and closed_by is not null
                       and counted_cash is not null and expected_cash is not null and difference is not null))
);
-- One open shift per drawer (FR11.7).
create unique index cashier_shifts_one_open on app.cashier_shifts (drawer_id) where status = 'open';

create table app.bills (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null,
  outlet_id     uuid not null,
  table_id      uuid,
  guest_name    text,
  status        app.bill_status not null default 'open',
  opened_at     timestamptz not null default now(),
  opened_by_actor app.actor_type not null,
  opened_by_id  uuid,
  closed_at     timestamptz,
  closed_by     uuid references app.users (id),
  subtotal      bigint check (subtotal >= 0),   -- snapshot at close
  pb1_rate_bps  integer,
  pb1_amount    bigint check (pb1_amount >= 0),
  total         bigint check (total >= 0),
  unique (id, outlet_id),
  foreign key (outlet_id, tenant_id) references app.outlets (id, tenant_id),
  foreign key (table_id, outlet_id)  references app.tables (id, outlet_id),
  constraint table_or_guest check (table_id is not null or guest_name is not null)
);
-- A table has at most one open bill (FR10.6, AC10.7).
create unique index bills_one_open_per_table on app.bills (table_id) where status = 'open' and table_id is not null;

create table app.orders (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null,
  outlet_id        uuid not null,
  order_no         integer not null,          -- per-outlet running number shown as #A-1036
  channel          app.order_channel not null,
  type             app.order_type not null,
  -- Flow is fixed at creation (AC10.10): pay_first or open_bill for dine-in.
  payment_mode     app.payment_mode not null,
  status           app.order_status not null,
  payment_status   app.payment_status not null default 'unpaid',
  contact_id       uuid,
  table_id         uuid,
  bill_id          uuid,
  delivery_address text,                      -- personal data: cleared on anonymization
  subtotal         bigint not null check (subtotal >= 0),
  pb1_rate_bps     integer check (pb1_rate_bps between 1 and 1000),  -- null = PB1 off
  pb1_amount       bigint not null default 0 check (pb1_amount >= 0),
  delivery_fee     bigint not null default 0 check (delivery_fee >= 0),
  total            bigint not null check (total = subtotal + pb1_amount + delivery_fee),
  created_by_actor app.actor_type not null,
  created_by_id    uuid,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  unique (outlet_id, order_no),
  unique (id, tenant_id),
  unique (id, outlet_id),
  foreign key (outlet_id, tenant_id)  references app.outlets (id, tenant_id),
  foreign key (contact_id, tenant_id) references app.whatsapp_contacts (id, tenant_id),
  foreign key (table_id, outlet_id)   references app.tables (id, outlet_id),
  foreign key (bill_id, outlet_id)    references app.bills (id, outlet_id),
  constraint channel_type check (
    (channel = 'whatsapp_online' and type in ('delivery', 'pickup') and payment_mode = 'pay_first') or
    (channel = 'whatsapp_table'  and type = 'dine_in' and table_id is not null) or
    (channel = 'counter'         and type in ('dine_in', 'takeaway'))),
  constraint delivery_fields check (
    (type = 'delivery') or (delivery_fee = 0 and delivery_address is null)),
  constraint open_bill_only_dine_in check (bill_id is null or (type = 'dine_in' and payment_mode = 'open_bill')),
  constraint completed_requires_paid check (status <> 'completed' or payment_status in ('paid', 'refunded')),
  constraint creator check (created_by_actor in ('system', 'agent') or created_by_id is not null)
);
create index on app.orders (outlet_id, status, created_at desc);
create index on app.orders (outlet_id, created_at);
create index on app.orders (bill_id) where bill_id is not null;

create table app.order_items (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null,
  outlet_id   uuid not null,
  order_id    uuid not null,
  product_id  uuid not null,
  name        text not null,                 -- snapshot
  unit_price  bigint not null check (unit_price >= 0),     -- snapshot of outlet price
  quantity    integer not null check (quantity between 1 and 999),
  line_total  bigint not null check (line_total >= 0),     -- (unit_price + add-ons) * quantity
  note        text,
  unique (id, tenant_id),
  foreign key (order_id, outlet_id)   references app.orders (id, outlet_id) on delete cascade,
  foreign key (product_id, tenant_id) references app.products (id, tenant_id)
);
create index on app.order_items (order_id);

create table app.order_item_addons (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null,
  order_item_id    uuid not null,
  addon_option_id  uuid not null,
  name             text not null,            -- snapshot
  price            bigint not null check (price >= 0),
  foreign key (order_item_id, tenant_id)   references app.order_items (id, tenant_id) on delete cascade,
  foreign key (addon_option_id, tenant_id) references app.addon_options (id, tenant_id)
);

-- Append-only order history: status changes, payment changes, reversals (FR10.2, FR1.6).
create table app.order_events (
  id               bigint generated always as identity primary key,
  tenant_id        uuid not null,
  outlet_id        uuid not null,
  order_id         uuid not null,
  event            text not null,             -- 'status_changed', 'payment_changed', 'reversed', 'proof_rejected', ...
  from_status      app.order_status,
  to_status        app.order_status,
  from_payment     app.payment_status,
  to_payment       app.payment_status,
  reason           text,
  data             jsonb not null default '{}'::jsonb,   -- e.g. {"method":"cash","amount":70000} or {"ingredients":"waste"}
  actor_type       app.actor_type not null,
  actor_id         uuid,
  created_at       timestamptz not null default now(),
  foreign key (order_id, outlet_id) references app.orders (id, outlet_id),
  constraint reason_required check (event not in ('reversed', 'proof_rejected') or coalesce(length(trim(reason)), 0) > 0),
  constraint event_actor check (actor_type in ('system', 'agent') or actor_id is not null)
);
create index on app.order_events (order_id, created_at);

alter table app.stock_movements
  add foreign key (order_id) references app.orders (id);

create table app.payments (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    uuid not null,
  outlet_id    uuid not null,
  order_id     uuid,
  bill_id      uuid,
  method       app.payment_method not null,
  amount       bigint not null check (amount > 0),
  cash_received bigint,
  change_due   bigint,
  shift_id     uuid,
  confirmed_by uuid not null references app.users (id),
  confirmed_at timestamptz not null default now(),
  foreign key (outlet_id, tenant_id) references app.outlets (id, tenant_id),
  foreign key (order_id, outlet_id)  references app.orders (id, outlet_id),
  foreign key (bill_id, outlet_id)   references app.bills (id, outlet_id),
  foreign key (shift_id, outlet_id)  references app.cashier_shifts (id, outlet_id),
  constraint one_target check ((order_id is null) <> (bill_id is null)),
  constraint cash_fields check (
    (method = 'cash' and shift_id is not null and cash_received >= amount and change_due = cash_received - amount) or
    (method = 'qris' and cash_received is null and change_due is null))
);
-- An order or bill is paid once, in full (FR10.6).
create unique index payments_order_key on app.payments (order_id) where order_id is not null;
create unique index payments_bill_key  on app.payments (bill_id)  where bill_id is not null;

create table app.payment_proofs (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null,
  outlet_id     uuid not null,
  order_id      uuid not null,
  storage_path  text not null,               -- private bucket object
  meta_media_id text,
  status        app.payment_proof_status not null default 'pending',
  received_at   timestamptz not null default now(),
  reviewed_by   uuid references app.users (id),
  reviewed_at   timestamptz,
  rejection_reason text,
  foreign key (order_id, outlet_id) references app.orders (id, outlet_id),
  constraint review_fields check (
    (status = 'pending'  and reviewed_by is null) or
    (status = 'accepted' and reviewed_by is not null and reviewed_at is not null) or
    (status = 'rejected' and reviewed_by is not null and reviewed_at is not null
                         and coalesce(length(trim(rejection_reason)), 0) > 0))
);
create index on app.payment_proofs (outlet_id, status);

-- Append-only ledger (FR3.1). Signed amount: + money in, - money out.
create table app.ledger_entries (
  id                bigint generated always as identity primary key,
  tenant_id         uuid not null,
  outlet_id         uuid not null,
  type              app.ledger_entry_type not null,
  amount            bigint not null check (amount <> 0),
  payment_method    app.payment_method,
  order_id          uuid,
  bill_id           uuid,
  payment_id        uuid references app.payments (id),
  shift_id          uuid,
  reverses_entry_id bigint references app.ledger_entries (id),
  description       text,
  business_date     date not null,          -- outlet-local date
  actor_type        app.actor_type not null,
  actor_id          uuid,
  created_at        timestamptz not null default now(),
  foreign key (outlet_id, tenant_id) references app.outlets (id, tenant_id),
  foreign key (order_id, outlet_id)  references app.orders (id, outlet_id),
  foreign key (bill_id, outlet_id)   references app.bills (id, outlet_id),
  foreign key (shift_id, outlet_id)  references app.cashier_shifts (id, outlet_id),
  constraint reversal_ref check ((type = 'reversal') = (reverses_entry_id is not null)),
  constraint expense_desc check (type <> 'expense' or (coalesce(length(trim(description)), 0) > 0 and amount < 0)),
  constraint ledger_actor check (actor_type in ('system', 'agent') or actor_id is not null)
);
create index on app.ledger_entries (outlet_id, business_date);
create index on app.ledger_entries (order_id) where order_id is not null;

create trigger append_only before update or delete on app.ledger_entries
  for each row execute function app.reject_update_delete();
create trigger append_only before update or delete on app.order_events
  for each row execute function app.reject_update_delete();
create trigger touch before update on app.orders for each row execute function app.touch_updated_at();
