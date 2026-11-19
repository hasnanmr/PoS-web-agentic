-- T-125: purchase orders and supplier debt (PRD FR3.5–FR3.12, FR4.10; glossary §7a).
-- Screens: O15 (list/detail/suppliers), O16/S12 (Buka PO), O17 (dashboard cards), S10, S11.
--
-- Cash basis: opening, checking, or closing a PO never posts to the ledger. Each supplier
-- payment posts one `expense` ledger entry (linked through purchase_order_id) on the payment
-- date. Receipts and payments are append-only. Cached totals on the PO (`amount_paid`,
-- `received_quantity` on lines, `status`, `payment_status`) are written by the service in the
-- same transaction as the append-only row they summarise.

create type app.po_payment_term   as enum ('pay_later', 'pay_in_advance');
create type app.po_status         as enum ('open', 'difference_found', 'closed', 'cancelled');
create type app.po_payment_status as enum ('unpaid', 'partially_paid', 'paid');

-- Suppliers (tenant-level, owner-managed; staff read them for the S12 dropdown) ----------------
create table app.suppliers (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references app.tenants (id),
  name        text not null check (length(trim(name)) between 1 and 120),
  phone       text check (phone is null or length(trim(phone)) between 1 and 30),
  note        text check (note is null or length(note) <= 300),
  is_active   boolean not null default true,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  unique (id, tenant_id)
);
create unique index suppliers_name_key on app.suppliers (tenant_id, lower(trim(name)));
create trigger touch before update on app.suppliers for each row execute function app.touch_updated_at();

-- Purchase orders ------------------------------------------------------------------------------
create table app.purchase_orders (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       uuid not null,
  outlet_id       uuid not null,
  po_no           integer not null check (po_no > 0),   -- per outlet, shown as PO-A-0012
  supplier_id     uuid not null,
  ordered_on      date not null,                         -- outlet-local
  payment_term    app.po_payment_term not null,
  due_date        date,                                  -- pay_later
  expected_date   date,                                  -- pay_in_advance
  note            text check (note is null or length(note) <= 300),
  status          app.po_status not null default 'open',
  total           bigint not null check (total > 0),     -- sum of line subtotals at open
  -- What the outlet owes in the end: the total, or received x unit price after the owner
  -- closes a pay-later PO with a difference (decided, US-060).
  amount_payable  bigint not null,
  amount_paid     bigint not null default 0,
  payment_status  app.po_payment_status not null default 'unpaid',
  created_by      uuid not null references app.users (id),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  closed_at       timestamptz,
  closed_by       uuid references app.users (id),
  close_note      text,
  cancelled_at    timestamptz,
  cancelled_by    uuid references app.users (id),
  cancel_reason   text,
  unique (outlet_id, po_no),
  unique (id, outlet_id),
  unique (id, tenant_id),
  foreign key (outlet_id, tenant_id)   references app.outlets (id, tenant_id),
  foreign key (supplier_id, tenant_id) references app.suppliers (id, tenant_id),
  constraint term_dates check (
    (payment_term = 'pay_later'      and due_date is not null      and expected_date is null
                                     and due_date >= ordered_on) or
    (payment_term = 'pay_in_advance' and expected_date is not null and due_date is null
                                     and expected_date >= ordered_on)),
  constraint payable_range check (amount_payable between 0 and total),
  constraint paid_range check (amount_paid between 0 and amount_payable),
  constraint payment_status_matches check (
    (payment_status = 'unpaid'         and amount_paid = 0 and amount_payable > 0) or
    (payment_status = 'partially_paid' and amount_paid > 0 and amount_paid < amount_payable) or
    (payment_status = 'paid'           and amount_paid = amount_payable)),
  constraint closed_fields check (
    (status = 'closed') = (closed_at is not null and closed_by is not null)),
  constraint cancelled_fields check (
    (status = 'cancelled') = (cancelled_at is not null and cancelled_by is not null
                              and coalesce(length(trim(cancel_reason)), 0) > 0)),
  constraint cancel_only_unpaid check (status <> 'cancelled' or amount_paid = 0),
  constraint advance_paid_before_close check (
    status <> 'closed' or payment_term = 'pay_later' or payment_status = 'paid')
);
create index purchase_orders_list on app.purchase_orders (tenant_id, created_at desc, id desc);
create index purchase_orders_outlet on app.purchase_orders (outlet_id, created_at desc, id desc);
create index purchase_orders_unpaid on app.purchase_orders (tenant_id, due_date)
  where status <> 'cancelled' and payment_status <> 'paid';
create trigger touch before update on app.purchase_orders for each row execute function app.touch_updated_at();

-- Staff may record receipts and close a matching PO, so they update the PO row; everything
-- about money, the supplier, terms, cancellation, and close notes is owner-only (FR1.5). The
-- API checks the role; this trigger makes the database refuse it from a staff session too.
-- A closed or cancelled PO never reopens; a closed pay-later PO still takes payments.
create function app.purchase_order_guard() returns trigger
language plpgsql as $$
declare
  privileged boolean := app.is_owner() or app.current_actor() = 'system';
begin
  if old.status in ('closed', 'cancelled') and new.status <> old.status then
    raise exception 'a % purchase order cannot change status', old.status
      using errcode = 'check_violation';
  end if;
  if old.status = 'cancelled' and (new.amount_paid, new.amount_payable) is distinct from (old.amount_paid, old.amount_payable) then
    raise exception 'a cancelled purchase order takes no payments' using errcode = 'check_violation';
  end if;
  if (new.tenant_id, new.outlet_id, new.po_no, new.ordered_on, new.total, new.created_by, new.created_at)
     is distinct from (old.tenant_id, old.outlet_id, old.po_no, old.ordered_on, old.total, old.created_by, old.created_at) then
    raise exception 'purchase order identity and total cannot change' using errcode = 'check_violation';
  end if;
  if not privileged and (
       (new.supplier_id, new.payment_term, new.due_date, new.expected_date, new.note,
        new.amount_payable, new.amount_paid, new.payment_status,
        new.cancelled_at, new.cancelled_by, new.cancel_reason, new.close_note)
       is distinct from
       (old.supplier_id, old.payment_term, old.due_date, old.expected_date, old.note,
        old.amount_payable, old.amount_paid, old.payment_status,
        old.cancelled_at, old.cancelled_by, old.cancel_reason, old.close_note)
       or new.status = 'cancelled') then
    raise exception 'only the owner can change payments, terms, or cancel a purchase order'
      using errcode = 'insufficient_privilege';
  end if;
  return new;
end $$;
create trigger guard before update on app.purchase_orders
  for each row execute function app.purchase_order_guard();
create trigger no_delete before delete on app.purchase_orders
  for each row execute function app.reject_update_delete();

-- Lines: a stock item (adds stock on receipt, converted to base units) or free text ---------------
create table app.purchase_order_lines (
  id                uuid primary key default gen_random_uuid(),
  tenant_id         uuid not null,
  outlet_id         uuid not null,
  purchase_order_id uuid not null,
  line_no           smallint not null check (line_no between 1 and 50),
  stock_item_id     uuid,
  item_name         text not null check (length(trim(item_name)) between 1 and 120),  -- snapshot
  quantity          numeric(14,3) not null check (quantity > 0),       -- in `unit`
  unit              text not null check (length(trim(unit)) between 1 and 20),
  -- Base units (g/ml/pcs) per one `unit`: 1000 for kg and L, else 1. Stock lines only.
  base_factor       integer check (base_factor in (1, 1000)),
  unit_price        bigint not null check (unit_price >= 0),           -- rupiah per `unit`
  subtotal          bigint not null check (subtotal >= 0),             -- round(quantity x unit_price)
  received_quantity numeric(14,3) not null default 0,
  unique (purchase_order_id, line_no),
  unique (id, outlet_id),
  foreign key (purchase_order_id, outlet_id) references app.purchase_orders (id, outlet_id),
  foreign key (stock_item_id, tenant_id)     references app.stock_items (id, tenant_id),
  constraint stock_line_unit check (
    (stock_item_id is null and base_factor is null) or
    (stock_item_id is not null and base_factor is not null and unit in ('g', 'kg', 'ml', 'L', 'pcs'))),
  -- Over-receipt is refused (US-060).
  constraint received_range check (received_quantity between 0 and quantity)
);
create index on app.purchase_order_lines (purchase_order_id);

-- Only the received quantity changes after the PO is opened, and it only goes up.
create function app.purchase_order_line_guard() returns trigger
language plpgsql as $$
begin
  if (new.tenant_id, new.outlet_id, new.purchase_order_id, new.line_no, new.stock_item_id,
      new.item_name, new.quantity, new.unit, new.base_factor, new.unit_price, new.subtotal)
     is distinct from
     (old.tenant_id, old.outlet_id, old.purchase_order_id, old.line_no, old.stock_item_id,
      old.item_name, old.quantity, old.unit, old.base_factor, old.unit_price, old.subtotal)
     or new.received_quantity < old.received_quantity then
    raise exception 'purchase order lines are fixed; only received quantity can grow'
      using errcode = 'check_violation';
  end if;
  return new;
end $$;
create trigger guard before update on app.purchase_order_lines
  for each row execute function app.purchase_order_line_guard();
create trigger no_delete before delete on app.purchase_order_lines
  for each row execute function app.reject_update_delete();

-- Goods receipts (S11 "Simpan penerimaan"), append-only ------------------------------------------
create table app.purchase_order_receipts (
  id                uuid primary key default gen_random_uuid(),
  tenant_id         uuid not null,
  outlet_id         uuid not null,
  purchase_order_id uuid not null,
  received_on       date not null,                       -- outlet-local delivery date
  note              text check (note is null or length(note) <= 300),
  actor_type        app.actor_type not null,
  actor_id          uuid,
  created_at        timestamptz not null default now(),
  unique (id, outlet_id),
  foreign key (purchase_order_id, outlet_id) references app.purchase_orders (id, outlet_id),
  constraint receipt_actor check (actor_type in ('system', 'agent') or actor_id is not null)
);
create index on app.purchase_order_receipts (purchase_order_id, created_at);

alter table app.stock_movements add column purchase_order_id uuid;
alter table app.stock_movements
  add foreign key (purchase_order_id, outlet_id) references app.purchase_orders (id, outlet_id);
alter table app.stock_movements
  add constraint po_restock check (purchase_order_id is null or type = 'restock');

create table app.purchase_order_receipt_lines (
  id                bigint generated always as identity primary key,
  tenant_id         uuid not null,
  outlet_id         uuid not null,
  receipt_id        uuid not null,
  line_id           uuid not null,
  quantity          numeric(14,3) not null check (quantity > 0),   -- in the line's unit
  stock_movement_id bigint references app.stock_movements (id),    -- stock lines only
  unique (receipt_id, line_id),
  foreign key (receipt_id, outlet_id) references app.purchase_order_receipts (id, outlet_id),
  foreign key (line_id, outlet_id)    references app.purchase_order_lines (id, outlet_id)
);

-- Supplier payments (owner only), append-only -----------------------------------------------------
alter table app.ledger_entries add column purchase_order_id uuid;
alter table app.ledger_entries
  add foreign key (purchase_order_id, outlet_id) references app.purchase_orders (id, outlet_id);
alter table app.ledger_entries
  add constraint po_expense check (purchase_order_id is null or type = 'expense');
alter table app.ledger_entries
  add constraint transfer_only_expense check (payment_method is distinct from 'transfer' or type = 'expense');

create table app.purchase_order_payments (
  id                uuid primary key default gen_random_uuid(),
  tenant_id         uuid not null,
  outlet_id         uuid not null,
  purchase_order_id uuid not null,
  paid_on           date not null,                       -- outlet-local; the ledger business date
  amount            bigint not null check (amount > 0),
  method            app.payment_method not null check (method in ('cash', 'transfer')),
  shift_id          uuid,                                -- cash taken from an open drawer
  ledger_entry_id   bigint not null unique references app.ledger_entries (id),
  recorded_by       uuid not null references app.users (id),
  created_at        timestamptz not null default now(),
  foreign key (purchase_order_id, outlet_id) references app.purchase_orders (id, outlet_id),
  foreign key (shift_id, outlet_id)          references app.cashier_shifts (id, outlet_id),
  constraint shift_only_cash check (shift_id is null or method = 'cash')
);
create index on app.purchase_order_payments (purchase_order_id, created_at);

-- A PO payment entry is never reversed from O9: payments cannot be edited or deleted (US-058).
create function app.reject_po_payment_reversal() returns trigger
language plpgsql as $$
begin
  if new.reverses_entry_id is not null and exists (
       select 1 from app.ledger_entries e
       where e.id = new.reverses_entry_id and e.purchase_order_id is not null) then
    raise exception 'supplier payments cannot be reversed' using errcode = 'check_violation';
  end if;
  return new;
end $$;
alter function app.reject_po_payment_reversal() security definer;
alter function app.reject_po_payment_reversal() set search_path = '';
create trigger no_po_payment_reversal before insert on app.ledger_entries
  for each row execute function app.reject_po_payment_reversal();

create trigger append_only before update or delete on app.purchase_order_receipts
  for each row execute function app.reject_update_delete();
create trigger append_only before update or delete on app.purchase_order_receipt_lines
  for each row execute function app.reject_update_delete();
create trigger append_only before update or delete on app.purchase_order_payments
  for each row execute function app.reject_update_delete();

-- PO numbers per outlet from 1 (PO-A-0001), serialized per outlet like order numbers.
create function app.next_po_no(p_outlet_id uuid) returns integer
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_next integer;
begin
  if not app.can_access_outlet(p_outlet_id) then
    raise exception 'no access to outlet' using errcode = '42501';
  end if;
  perform pg_advisory_xact_lock(hashtextextended('po_no:' || p_outlet_id::text, 0));
  select coalesce(max(po_no), 0) + 1 into v_next from app.purchase_orders where outlet_id = p_outlet_id;
  return v_next;
end $$;
revoke execute on function app.next_po_no(uuid) from public;
grant execute on function app.next_po_no(uuid) to app_backend;

-- RLS ---------------------------------------------------------------------------------------------
alter table app.suppliers enable row level security;
create policy tenant_scope on app.suppliers to app_backend
  using      (tenant_id = app.current_tenant())
  with check (tenant_id = app.current_tenant());
-- Staff read suppliers (S12 dropdown); only the owner adds or edits them.
create policy owner_writes on app.suppliers as restrictive for insert to app_backend
  with check (app.is_owner() or app.current_actor() = 'system');
create policy owner_updates on app.suppliers as restrictive for update to app_backend
  using (app.is_owner() or app.current_actor() = 'system');

do $$
declare
  t text;
begin
  foreach t in array array[
    'purchase_orders', 'purchase_order_lines', 'purchase_order_receipts',
    'purchase_order_receipt_lines', 'purchase_order_payments'
  ] loop
    execute format('alter table app.%I enable row level security', t);
    execute format($p$
      create policy outlet_scope on app.%I to app_backend
        using      (tenant_id = app.current_tenant() and app.can_access_outlet(outlet_id))
        with check (tenant_id = app.current_tenant() and app.can_access_outlet(outlet_id))
    $p$, t);
  end loop;
end $$;

-- Payments and debt are owner-only, reading included (staff see only payment_status on the PO).
create policy owner_only on app.purchase_order_payments as restrictive to app_backend
  using      (app.is_owner() or app.current_actor() = 'system')
  with check (app.is_owner() or app.current_actor() = 'system');

grant select, insert, update on app.suppliers, app.purchase_orders, app.purchase_order_lines to app_backend;
grant select, insert on app.purchase_order_receipts, app.purchase_order_receipt_lines,
  app.purchase_order_payments to app_backend;
