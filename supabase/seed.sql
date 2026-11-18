-- Dummy seed data for local development and the demo (NFR1: no real merchant data).
-- Mirrors the wireframe content (design/previews): Kopi Senja with outlets Dago, Riau,
-- Kemang, and Canggu; the menu, add-ons, recipes, stock, drawers, and tables shown on
-- O3, O5, O6, O8, S1, S7. Idempotent: safe to run more than once.
--
-- Users are not seeded: app.users.id must match a Supabase Auth user. Invite the
-- owner with `uv run python -m app.cli invite-owner ...` (T-006) or, for plain
-- PostgreSQL tests, insert into auth.users first (see supabase/tests/rls.sql).

begin;

-- Tenant and outlets (O3) ---------------------------------------------------------
insert into app.tenants (id, name, type) values
  ('11111111-1111-1111-1111-111111111111', 'Kopi Senja', 'cafe')
on conflict (id) do nothing;

insert into app.outlets (id, tenant_id, name, address, timezone, payment_mode, delivery_fee,
                         pb1_enabled, pb1_rate_bps, unpaid_timeout_minutes, order_prefix,
                         whatsapp_phone, whatsapp_status) values
  ('22222222-2222-2222-2222-222222222201', '11111111-1111-1111-1111-111111111111',
   'Bandung – Dago', 'Jl. Ir. H. Juanda No. 12, Bandung', 'Asia/Jakarta', 'open_bill', 10000,
   true, 1000, 15, 'A', '+628110000001', 'connected'),
  ('22222222-2222-2222-2222-222222222202', '11111111-1111-1111-1111-111111111111',
   'Bandung – Riau', 'Jl. L. L. R. E. Martadinata, Bandung', 'Asia/Jakarta', 'pay_first', 10000,
   true, 1000, 15, 'R', '+628110000002', 'connected'),
  ('22222222-2222-2222-2222-222222222203', '11111111-1111-1111-1111-111111111111',
   'Jakarta – Kemang', 'Jl. Kemang Raya, Jakarta', 'Asia/Jakarta', 'pay_first', 15000,
   true, 1000, 15, 'K', '+628110000003', 'pending_verification'),
  ('22222222-2222-2222-2222-222222222204', '11111111-1111-1111-1111-111111111111',
   'Bali – Canggu', 'Jl. Batu Mejan, Canggu', 'Asia/Makassar', 'pay_first', 15000,
   false, null, 15, 'C', null, 'not_started')
on conflict (id) do nothing;
-- PB1 10% here is dummy data for the demo only; the real rate per outlet is still TBD.

insert into app.outlet_opening_hours (outlet_id, tenant_id, weekday, opens_at, closes_at)
select o.id, o.tenant_id, d, '08:00', '22:00'
from app.outlets o cross join generate_series(1, 7) d
where o.tenant_id = '11111111-1111-1111-1111-111111111111'
on conflict do nothing;

-- Second drawer at Dago (O3: "Drawer 2 · Bar"); "Kasir depan" is created by the trigger.
insert into app.cash_drawers (tenant_id, outlet_id, name) values
  ('11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222201', 'Bar')
on conflict do nothing;

update app.reservation_settings set is_enabled = true, cancellation_cutoff_minutes = 180
where outlet_id = '22222222-2222-2222-2222-222222222201';

-- Tables at Dago (O8) ------------------------------------------------------------------
insert into app.tables (tenant_id, outlet_id, name, capacity, area, is_bookable)
select '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222201', t.name, t.cap, t.area, t.bookable
from (values ('M01', 2, 'Indoor', true), ('M02', 2, 'Indoor', true), ('M05', 4, 'Indoor', true),
             ('M07', 4, 'Indoor', true), ('M09', 6, 'Indoor', true), ('M12', 4, 'Outdoor', false),
             ('VIP', 10, 'Lantai 2', true)) as t(name, cap, area, bookable)
on conflict do nothing;

-- Stock items (S7, O6) -------------------------------------------------------------------
insert into app.stock_items (id, tenant_id, name, unit, display_unit) values
  ('33333333-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'Biji kopi house blend', 'g', 'kg'),
  ('33333333-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'Susu UHT', 'ml', 'L'),
  ('33333333-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'Susu oat', 'ml', 'L'),
  ('33333333-0000-0000-0000-000000000004', '11111111-1111-1111-1111-111111111111', 'Gula aren cair', 'ml', 'L'),
  ('33333333-0000-0000-0000-000000000005', '11111111-1111-1111-1111-111111111111', 'Bubuk matcha', 'g', 'g'),
  ('33333333-0000-0000-0000-000000000006', '11111111-1111-1111-1111-111111111111', 'Croissant (frozen)', 'pcs', 'pcs'),
  ('33333333-0000-0000-0000-000000000007', '11111111-1111-1111-1111-111111111111', 'Roti tawar', 'pcs', 'pcs'),
  ('33333333-0000-0000-0000-000000000008', '11111111-1111-1111-1111-111111111111', 'Kentang beku', 'g', 'kg'),
  ('33333333-0000-0000-0000-000000000009', '11111111-1111-1111-1111-111111111111', 'Cup 16oz', 'pcs', 'pcs'),
  ('33333333-0000-0000-0000-000000000010', '11111111-1111-1111-1111-111111111111', 'Susu almond', 'ml', 'L')
on conflict (id) do nothing;

-- Products (O5) ------------------------------------------------------------------------------
insert into app.products (id, tenant_id, name, category, description, is_owner_pick, owner_pick_rank, is_active, is_sample) values
  ('44444444-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'Es Kopi Susu Senja', 'Kopi', 'Espresso, susu segar & gula aren', true, 1, true, false),
  ('44444444-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'Americano', 'Kopi', null, false, null, true, false),
  ('44444444-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'Matcha Latte', 'Non-kopi', null, true, 2, true, false),
  ('44444444-0000-0000-0000-000000000004', '11111111-1111-1111-1111-111111111111', 'Croissant Butter', 'Makanan', null, false, null, true, false),
  ('44444444-0000-0000-0000-000000000005', '11111111-1111-1111-1111-111111111111', 'Roti Bakar Cokelat', 'Makanan', null, true, 4, true, true),
  ('44444444-0000-0000-0000-000000000006', '11111111-1111-1111-1111-111111111111', 'Kentang Goreng', 'Makanan', null, true, 3, false, true)
on conflict (id) do nothing;

insert into app.product_tags (product_id, tenant_id, tag) values
  ('44444444-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'coffee'),
  ('44444444-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'sweet'),
  ('44444444-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', 'sweet'),
  ('44444444-0000-0000-0000-000000000006', '11111111-1111-1111-1111-111111111111', 'sharing'),
  ('44444444-0000-0000-0000-000000000005', '11111111-1111-1111-1111-111111111111', 'sweet'),
  ('44444444-0000-0000-0000-000000000005', '11111111-1111-1111-1111-111111111111', 'sharing')
on conflict do nothing;

-- Prices per outlet (O5 "Harga per outlet"): Dago/Riau base, Kemang +3.000, Canggu +5.000.
insert into app.outlet_prices (tenant_id, outlet_id, product_id, price)
select p.tenant_id, o.id, p.id,
       base.price + case o.order_prefix when 'K' then 3000 when 'C' then 5000 else 0 end
from (values ('44444444-0000-0000-0000-000000000001'::uuid, 25000), ('44444444-0000-0000-0000-000000000002'::uuid, 22000),
             ('44444444-0000-0000-0000-000000000003'::uuid, 28000), ('44444444-0000-0000-0000-000000000004'::uuid, 24000),
             ('44444444-0000-0000-0000-000000000005'::uuid, 20000), ('44444444-0000-0000-0000-000000000006'::uuid, 18000))
     as base(product_id, price)
join app.products p on p.id = base.product_id
join app.outlets o on o.tenant_id = p.tenant_id
on conflict do nothing;

-- Add-ons for Es Kopi Susu Senja (O5): Ukuran (required), Pilihan susu, Gula.
insert into app.addon_groups (id, tenant_id, product_id, name, selection, is_required, sort_order) values
  ('55555555-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', '44444444-0000-0000-0000-000000000001', 'Ukuran', 'single', true, 1),
  ('55555555-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', '44444444-0000-0000-0000-000000000001', 'Pilihan susu', 'single', false, 2),
  ('55555555-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', '44444444-0000-0000-0000-000000000001', 'Gula', 'single', false, 3)
on conflict (id) do nothing;

insert into app.addon_options (id, tenant_id, group_id, name, sort_order) values
  ('66666666-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', '55555555-0000-0000-0000-000000000001', 'Regular', 1),
  ('66666666-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', '55555555-0000-0000-0000-000000000001', 'Large', 2),
  ('66666666-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111', '55555555-0000-0000-0000-000000000002', 'Oat milk', 1),
  ('66666666-0000-0000-0000-000000000004', '11111111-1111-1111-1111-111111111111', '55555555-0000-0000-0000-000000000002', 'Almond milk', 2),
  ('66666666-0000-0000-0000-000000000005', '11111111-1111-1111-1111-111111111111', '55555555-0000-0000-0000-000000000003', 'Normal', 1),
  ('66666666-0000-0000-0000-000000000006', '11111111-1111-1111-1111-111111111111', '55555555-0000-0000-0000-000000000003', 'Less sugar', 2),
  ('66666666-0000-0000-0000-000000000007', '11111111-1111-1111-1111-111111111111', '55555555-0000-0000-0000-000000000003', 'No sugar', 3)
on conflict (id) do nothing;

insert into app.outlet_prices (tenant_id, outlet_id, addon_option_id, price)
select '11111111-1111-1111-1111-111111111111', o.id, x.option_id, x.price
from (values ('66666666-0000-0000-0000-000000000001'::uuid, 0), ('66666666-0000-0000-0000-000000000002'::uuid, 5000),
             ('66666666-0000-0000-0000-000000000003'::uuid, 5000), ('66666666-0000-0000-0000-000000000004'::uuid, 6000),
             ('66666666-0000-0000-0000-000000000005'::uuid, 0), ('66666666-0000-0000-0000-000000000006'::uuid, 0),
             ('66666666-0000-0000-0000-000000000007'::uuid, 0)) as x(option_id, price)
cross join app.outlets o
where o.tenant_id = '11111111-1111-1111-1111-111111111111'
on conflict do nothing;

-- Recipes (O6) -------------------------------------------------------------------------------
insert into app.recipe_items (tenant_id, product_id, stock_item_id, quantity) values
  ('11111111-1111-1111-1111-111111111111', '44444444-0000-0000-0000-000000000001', '33333333-0000-0000-0000-000000000001', 18),
  ('11111111-1111-1111-1111-111111111111', '44444444-0000-0000-0000-000000000001', '33333333-0000-0000-0000-000000000002', 150),
  ('11111111-1111-1111-1111-111111111111', '44444444-0000-0000-0000-000000000001', '33333333-0000-0000-0000-000000000004', 20),
  ('11111111-1111-1111-1111-111111111111', '44444444-0000-0000-0000-000000000001', '33333333-0000-0000-0000-000000000009', 1),
  ('11111111-1111-1111-1111-111111111111', '44444444-0000-0000-0000-000000000002', '33333333-0000-0000-0000-000000000001', 18),
  ('11111111-1111-1111-1111-111111111111', '44444444-0000-0000-0000-000000000002', '33333333-0000-0000-0000-000000000009', 1),
  ('11111111-1111-1111-1111-111111111111', '44444444-0000-0000-0000-000000000003', '33333333-0000-0000-0000-000000000005', 5),
  ('11111111-1111-1111-1111-111111111111', '44444444-0000-0000-0000-000000000003', '33333333-0000-0000-0000-000000000002', 200),
  ('11111111-1111-1111-1111-111111111111', '44444444-0000-0000-0000-000000000003', '33333333-0000-0000-0000-000000000009', 1),
  ('11111111-1111-1111-1111-111111111111', '44444444-0000-0000-0000-000000000004', '33333333-0000-0000-0000-000000000006', 1),
  ('11111111-1111-1111-1111-111111111111', '44444444-0000-0000-0000-000000000005', '33333333-0000-0000-0000-000000000007', 2),
  ('11111111-1111-1111-1111-111111111111', '44444444-0000-0000-0000-000000000006', '33333333-0000-0000-0000-000000000008', 150)
on conflict do nothing;

-- Add-on recipe deltas (O6 "Delta resep dari add-on").
insert into app.recipe_items (tenant_id, addon_option_id, stock_item_id, quantity) values
  ('11111111-1111-1111-1111-111111111111', '66666666-0000-0000-0000-000000000002', '33333333-0000-0000-0000-000000000001', 6),
  ('11111111-1111-1111-1111-111111111111', '66666666-0000-0000-0000-000000000002', '33333333-0000-0000-0000-000000000002', 50),
  ('11111111-1111-1111-1111-111111111111', '66666666-0000-0000-0000-000000000003', '33333333-0000-0000-0000-000000000002', -150),
  ('11111111-1111-1111-1111-111111111111', '66666666-0000-0000-0000-000000000003', '33333333-0000-0000-0000-000000000003', 150),
  ('11111111-1111-1111-1111-111111111111', '66666666-0000-0000-0000-000000000004', '33333333-0000-0000-0000-000000000002', -150),
  ('11111111-1111-1111-1111-111111111111', '66666666-0000-0000-0000-000000000004', '33333333-0000-0000-0000-000000000010', 150),
  ('11111111-1111-1111-1111-111111111111', '66666666-0000-0000-0000-000000000007', '33333333-0000-0000-0000-000000000004', -20)
on conflict do nothing;

-- Opening stock at Dago (S7), only on a fresh database, and thresholds ("MIN").
insert into app.stock_movements (tenant_id, outlet_id, stock_item_id, type, quantity, note, actor_type)
select '11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222201', s.id, 'restock', s.qty, 'seed: stok awal', 'system'
from (values ('33333333-0000-0000-0000-000000000001'::uuid, 2400), ('33333333-0000-0000-0000-000000000002'::uuid, 12000),
             ('33333333-0000-0000-0000-000000000003'::uuid, 800), ('33333333-0000-0000-0000-000000000004'::uuid, 1500),
             ('33333333-0000-0000-0000-000000000005'::uuid, 180), ('33333333-0000-0000-0000-000000000007'::uuid, 24),
             ('33333333-0000-0000-0000-000000000008'::uuid, 3000), ('33333333-0000-0000-0000-000000000009'::uuid, 140))
     as s(id, qty)
where not exists (select 1 from app.stock_movements
                  where outlet_id = '22222222-2222-2222-2222-222222222201' and note = 'seed: stok awal');

insert into app.outlet_stock (outlet_id, stock_item_id, tenant_id, low_threshold)
select '22222222-2222-2222-2222-222222222201', t.id, '11111111-1111-1111-1111-111111111111', t.min
from (values ('33333333-0000-0000-0000-000000000001'::uuid, 1000), ('33333333-0000-0000-0000-000000000002'::uuid, 4000),
             ('33333333-0000-0000-0000-000000000003'::uuid, 2000), ('33333333-0000-0000-0000-000000000004'::uuid, 1000),
             ('33333333-0000-0000-0000-000000000005'::uuid, 200), ('33333333-0000-0000-0000-000000000006'::uuid, 10),
             ('33333333-0000-0000-0000-000000000007'::uuid, 10), ('33333333-0000-0000-0000-000000000008'::uuid, 2000),
             ('33333333-0000-0000-0000-000000000009'::uuid, 50)) as t(id, min)
on conflict (outlet_id, stock_item_id) do update set low_threshold = excluded.low_threshold;

commit;
