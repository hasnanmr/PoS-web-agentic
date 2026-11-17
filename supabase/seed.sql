-- Dummy seed data for local development only (NFR1: no real merchant data).
-- Users are not seeded here because app.users.id must match a Supabase Auth user;
-- create them through the invite flow (T-012). Full seed set comes with T-009.

insert into app.tenants (id, name, type) values
  ('11111111-1111-1111-1111-111111111111', 'Kopi Senja (dummy)', 'cafe')
on conflict do nothing;

insert into app.outlets (id, tenant_id, name, address, timezone, payment_mode, delivery_fee) values
  ('22222222-2222-2222-2222-222222222201', '11111111-1111-1111-1111-111111111111',
   'Bandung - Dago', 'Jl. Ir. H. Juanda No. 12, Bandung', 'Asia/Jakarta', 'open_bill', 10000),
  ('22222222-2222-2222-2222-222222222202', '11111111-1111-1111-1111-111111111111',
   'Bali - Canggu', 'Jl. Batu Mejan, Canggu', 'Asia/Makassar', 'pay_first', 15000)
on conflict do nothing;
