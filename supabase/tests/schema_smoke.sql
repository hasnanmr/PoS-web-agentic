-- Schema smoke tests for T-004. Runs inside one transaction and rolls back.
-- Usage: psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/tests/schema_smoke.sql
-- Any failed assertion raises an exception and stops the script.

\o /dev/null
begin;

create function pg_temp.expect_error(stmt text, label text) returns void
language plpgsql as $$
begin
  begin
    execute stmt;
  exception when others then
    raise notice 'ok   - % (rejected: %)', label, sqlerrm;
    return;
  end;
  raise exception 'FAIL - % was accepted', label;
end $$;

create function pg_temp.check(cond boolean, label text) returns void
language plpgsql as $$
begin
  if not cond then raise exception 'FAIL - %', label; end if;
  raise notice 'ok   - %', label;
end $$;

-- Fixtures ---------------------------------------------------------------
insert into app.tenants (id, name, type) values
  ('00000000-0000-0000-0000-00000000000a', 'Kopi Senja', 'cafe'),
  ('00000000-0000-0000-0000-00000000000b', 'Warung Lain', 'restaurant');
insert into app.outlets (id, tenant_id, name) values
  ('00000000-0000-0000-0000-0000000000a1', '00000000-0000-0000-0000-00000000000a', 'Bandung - Dago'),
  ('00000000-0000-0000-0000-0000000000b1', '00000000-0000-0000-0000-00000000000b', 'Jakarta');
insert into app.users (id, tenant_id, email, display_name, role) values
  ('00000000-0000-0000-0000-0000000000f1', '00000000-0000-0000-0000-00000000000a', 'rina@kopisenja.id', 'Rina', 'staff');
insert into app.tables (id, tenant_id, outlet_id, name, capacity) values
  ('00000000-0000-0000-0000-0000000000c1', '00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-0000000000a1', 'M02', 4);
insert into app.stock_items (id, tenant_id, name, unit) values
  ('00000000-0000-0000-0000-0000000000d1', '00000000-0000-0000-0000-00000000000a', 'Susu UHT', 'ml');

-- Outlet defaults ---------------------------------------------------------
select pg_temp.check(
  (select timezone = 'Asia/Jakarta' and not pb1_enabled and payment_mode = 'pay_first'
     from app.outlets where id = '00000000-0000-0000-0000-0000000000a1'),
  'new outlet defaults to WIB, PB1 off, pay first');
select pg_temp.check(
  (select count(*) = 1 and min(name) = 'Kasir depan' from app.cash_drawers where outlet_id = '00000000-0000-0000-0000-0000000000a1'),
  'new outlet gets one cash drawer "Kasir depan" (AC11.10, wireframe O3/S8)');
select pg_temp.expect_error(
  $$insert into app.outlets (tenant_id, name) values ('00000000-0000-0000-0000-00000000000a', 'Outlet kedua')$$,
  'second outlet reusing order prefix A in the same tenant');
select pg_temp.expect_error(
  $$update app.outlets set pb1_enabled = true where id = '00000000-0000-0000-0000-0000000000a1'$$,
  'PB1 enabled without a rate');
select pg_temp.expect_error(
  $$update app.outlets set timezone = 'Asia/Singapore' where id = '00000000-0000-0000-0000-0000000000a1'$$,
  'non-Indonesian outlet time zone');

-- Stock -------------------------------------------------------------------
insert into app.stock_movements (tenant_id, outlet_id, stock_item_id, type, quantity, actor_type, actor_id)
values ('00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-0000000000a1',
        '00000000-0000-0000-0000-0000000000d1', 'restock', 1000, 'user', '00000000-0000-0000-0000-0000000000f1');
select pg_temp.check(
  (select on_hand = 1000 from app.outlet_stock where stock_item_id = '00000000-0000-0000-0000-0000000000d1'),
  'restock movement updates on_hand');
select pg_temp.expect_error(
  $$insert into app.stock_movements (tenant_id, outlet_id, stock_item_id, type, quantity, actor_type)
    values ('00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-0000000000a1',
            '00000000-0000-0000-0000-0000000000d1', 'sale', -1001, 'system')$$,
  'sale that would make stock negative');
select pg_temp.expect_error(
  $$update app.stock_movements set quantity = 5$$, 'editing a stock movement (AC4.2)');
select pg_temp.expect_error(
  $$delete from app.stock_movements$$, 'deleting a stock movement (AC4.2)');

-- Add-on limit ------------------------------------------------------------
insert into app.products (id, tenant_id, name) values
  ('00000000-0000-0000-0000-0000000000e1', '00000000-0000-0000-0000-00000000000a', 'Es Kopi Susu Senja');
insert into app.addon_groups (id, tenant_id, product_id, name, selection) values
  ('00000000-0000-0000-0000-0000000000e2', '00000000-0000-0000-0000-00000000000a',
   '00000000-0000-0000-0000-0000000000e1', 'Topping', 'multiple');
insert into app.addon_options (tenant_id, group_id, name)
select '00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-0000000000e2', 'Opsi ' || g
from generate_series(1, 10) g;
select pg_temp.expect_error(
  $$insert into app.addon_options (tenant_id, group_id, name)
    values ('00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-0000000000e2', 'Opsi 11')$$,
  '11th add-on option (AC4.6)');

-- Orders ------------------------------------------------------------------
insert into app.orders (id, tenant_id, outlet_id, order_no, channel, type, payment_mode, status,
                        subtotal, pb1_rate_bps, pb1_amount, total, created_by_actor, created_by_id)
values ('00000000-0000-0000-0000-000000000101', '00000000-0000-0000-0000-00000000000a',
        '00000000-0000-0000-0000-0000000000a1', 1036, 'counter', 'takeaway', 'pay_first', 'confirmed',
        84000, 1000, 8400, 92400, 'user', '00000000-0000-0000-0000-0000000000f1');
select pg_temp.expect_error(
  $$update app.orders set total = 92000 where order_no = 1036$$, 'total not equal to subtotal + PB1 + delivery');
select pg_temp.expect_error(
  $$update app.orders set status = 'completed' where order_no = 1036$$, 'completed while unpaid (AC10.2)');
select pg_temp.expect_error(
  $$insert into app.orders (tenant_id, outlet_id, order_no, channel, type, payment_mode, status,
                            subtotal, total, created_by_actor)
    values ('00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-0000000000a1', 2,
            'whatsapp_online', 'dine_in', 'pay_first', 'pending_payment', 1000, 1000, 'system')$$,
  'online order with dine-in type');
select pg_temp.expect_error(
  $$insert into app.orders (tenant_id, outlet_id, order_no, channel, type, payment_mode, status,
                            subtotal, total, created_by_actor)
    values ('00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-0000000000b1', 3,
            'counter', 'takeaway', 'pay_first', 'confirmed', 1000, 1000, 'system')$$,
  'order linking tenant A to an outlet of tenant B');
select pg_temp.expect_error(
  $$insert into app.order_events (tenant_id, outlet_id, order_id, event, actor_type, actor_id)
    values ('00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-0000000000a1',
            '00000000-0000-0000-0000-000000000101', 'reversed', 'user', '00000000-0000-0000-0000-0000000000f1')$$,
  'reversal without a reason (AC1.7)');

-- Shifts and payments -----------------------------------------------------
insert into app.cashier_shifts (tenant_id, outlet_id, drawer_id, opened_by, starting_cash)
select tenant_id, outlet_id, id, '00000000-0000-0000-0000-0000000000f1', 500000
from app.cash_drawers where outlet_id = '00000000-0000-0000-0000-0000000000a1';
select pg_temp.expect_error(
  $$insert into app.cashier_shifts (tenant_id, outlet_id, drawer_id, opened_by, starting_cash)
    select tenant_id, outlet_id, id, '00000000-0000-0000-0000-0000000000f1', 0
    from app.cash_drawers where outlet_id = '00000000-0000-0000-0000-0000000000a1'$$,
  'second open shift on one drawer (AC11.7)');
insert into app.payments (tenant_id, outlet_id, order_id, method, amount, cash_received, change_due, shift_id, confirmed_by)
select '00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-0000000000a1',
       '00000000-0000-0000-0000-000000000101', 'cash', 92400, 100000, 7600, s.id,
       '00000000-0000-0000-0000-0000000000f1'
from app.cashier_shifts s where s.status = 'open';
select pg_temp.check(true, 'cash payment with exact change, no rounding (Rp100.000 - Rp92.400 = Rp7.600)');

-- Ledger ------------------------------------------------------------------
insert into app.ledger_entries (tenant_id, outlet_id, type, amount, payment_method, order_id, business_date, actor_type, actor_id)
values ('00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-0000000000a1', 'revenue', 84000, 'cash',
        '00000000-0000-0000-0000-000000000101', '2026-11-17', 'user', '00000000-0000-0000-0000-0000000000f1');
select pg_temp.expect_error($$update app.ledger_entries set amount = 1$$, 'editing a ledger entry (AC3.1)');
select pg_temp.expect_error($$delete from app.ledger_entries$$, 'deleting a ledger entry (AC3.1)');

-- Bills -------------------------------------------------------------------
insert into app.bills (tenant_id, outlet_id, table_id, opened_by_actor)
values ('00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-0000000000a1',
        '00000000-0000-0000-0000-0000000000c1', 'system');
select pg_temp.expect_error(
  $$insert into app.bills (tenant_id, outlet_id, table_id, opened_by_actor)
    values ('00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-0000000000a1',
            '00000000-0000-0000-0000-0000000000c1', 'system')$$,
  'second open bill on one table (AC10.7)');

-- Reservations ------------------------------------------------------------
insert into app.reservations (tenant_id, outlet_id, table_id, guest_name, party_size, starts_at, ends_at, source, created_by_actor)
values ('00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-0000000000a1',
        '00000000-0000-0000-0000-0000000000c1', 'Dewi', 2,
        '2026-11-17 19:00+07', '2026-11-17 20:30+07', 'whatsapp', 'system');
select pg_temp.expect_error(
  $$insert into app.reservations (tenant_id, outlet_id, table_id, guest_name, party_size, starts_at, ends_at, source, created_by_actor)
    values ('00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-0000000000a1',
            '00000000-0000-0000-0000-0000000000c1', 'Rudi', 4,
            '2026-11-17 20:00+07', '2026-11-17 21:30+07', 'phone', 'system')$$,
  'overlapping booking on one table (AC9.4)');
insert into app.reservations (tenant_id, outlet_id, table_id, guest_name, party_size, starts_at, ends_at, source, created_by_actor)
values ('00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-0000000000a1',
        '00000000-0000-0000-0000-0000000000c1', 'Tono', 2,
        '2026-11-17 20:30+07', '2026-11-17 22:00+07', 'phone', 'system');
select pg_temp.check(true, 'back-to-back booking (20:30 after a booking ending 20:30) allowed');

-- Attendance ---------------------------------------------------------------
insert into app.attendance_devices (id, tenant_id, outlet_id, name, paired_by)
values ('00000000-0000-0000-0000-000000000201', '00000000-0000-0000-0000-00000000000a',
        '00000000-0000-0000-0000-0000000000a1', 'Tablet Kasir Dago', '00000000-0000-0000-0000-0000000000f1');
insert into app.attendance_records (tenant_id, outlet_id, user_id, clock_in_at, clock_in_device_id, clock_in_photo_path)
values ('00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-0000000000a1',
        '00000000-0000-0000-0000-0000000000f1', now(), '00000000-0000-0000-0000-000000000201', 'selfies/x.jpg');
select pg_temp.expect_error(
  $$insert into app.attendance_records (tenant_id, outlet_id, user_id, clock_in_at, clock_in_device_id)
    values ('00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-0000000000a1',
            '00000000-0000-0000-0000-0000000000f1', now(), '00000000-0000-0000-0000-000000000201')$$,
  'second open attendance record (AC5.1)');

-- Customers -----------------------------------------------------------------
select pg_temp.expect_error(
  $$insert into app.whatsapp_contacts (tenant_id, phone, is_anonymized)
    values ('00000000-0000-0000-0000-00000000000a', '+6281200000000', true)$$,
  'anonymized contact that still has a phone number');

select pg_temp.check(true, 'all schema smoke tests passed');
rollback;
