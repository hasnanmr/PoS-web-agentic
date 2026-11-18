-- T-019, T-022, T-024: stock thresholds through a definer function, and the editable
-- sample menu every new business gets at onboarding (FR2.12, wireframe O1 note).

-- Thresholds ("MIN" on S7, O6 "Threshold per outlet") ------------------------------
-- outlet_stock is read-only for app_backend (levels change only through movements),
-- so the owner sets thresholds here. Same checks as the RLS policies, plus owner only.
create function app.set_stock_threshold(p_outlet_id uuid, p_stock_item_id uuid, p_threshold numeric)
returns void
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_tenant uuid := app.current_tenant();
begin
  if not app.is_owner() or not app.can_access_outlet(p_outlet_id) then
    raise exception 'owner only' using errcode = '42501';
  end if;
  if not exists (select 1 from app.stock_items where id = p_stock_item_id and tenant_id = v_tenant) then
    raise exception 'stock item not found' using errcode = 'P0002';
  end if;
  insert into app.outlet_stock (outlet_id, stock_item_id, tenant_id, low_threshold)
  values (p_outlet_id, p_stock_item_id, v_tenant, p_threshold)
  on conflict (outlet_id, stock_item_id)
  do update set low_threshold = excluded.low_threshold, updated_at = now();
end $$;

revoke execute on function app.set_stock_threshold(uuid, uuid, numeric) from public;
grant execute on function app.set_stock_threshold(uuid, uuid, numeric) to app_backend;

-- Sample menu ------------------------------------------------------------------------
-- Same content as the wireframes (O5, O6, S7), marked is_sample so the owner can see
-- what to edit. Opening stock lets the counter sell right away; the owner adjusts it
-- in S7. Photos are added later (T-107 sample photos).
create function app.seed_sample_menu(p_tenant_id uuid, p_outlet_id uuid) returns void
language plpgsql volatile set search_path = '' as $$
begin
  create temp table sample_items (key text primary key, id uuid) on commit drop;

  with ins as (
    insert into app.stock_items (tenant_id, name, unit, display_unit)
    select p_tenant_id, s.name, s.unit::app.stock_unit, s.display
    from (values ('Biji kopi house blend', 'g', 'kg'), ('Susu UHT', 'ml', 'L'), ('Susu oat', 'ml', 'L'),
                 ('Susu almond', 'ml', 'L'), ('Gula aren cair', 'ml', 'L'), ('Bubuk matcha', 'g', 'g'),
                 ('Croissant (frozen)', 'pcs', 'pcs'), ('Roti tawar', 'pcs', 'pcs'),
                 ('Kentang beku', 'g', 'kg'), ('Cup 16oz', 'pcs', 'pcs')) as s(name, unit, display)
    returning name, id)
  insert into sample_items select 'stock:' || name, id from ins;

  with ins as (
    insert into app.products (tenant_id, name, category, description, is_owner_pick, owner_pick_rank, is_sample)
    select p_tenant_id, p.name, p.category, p.description, p.pick, p.rank, true
    from (values ('Es Kopi Susu Senja', 'Kopi', 'Espresso, susu segar & gula aren', true, 1),
                 ('Americano', 'Kopi', 'Espresso dan air panas', false, null),
                 ('Matcha Latte', 'Non-kopi', 'Matcha dan susu segar', true, 2),
                 ('Croissant Butter', 'Makanan', 'Croissant mentega, dipanaskan', false, null),
                 ('Roti Bakar Cokelat', 'Makanan', 'Roti bakar isi cokelat', true, 3),
                 ('Kentang Goreng', 'Makanan', 'Kentang goreng renyah', false, null))
         as p(name, category, description, pick, rank)
    returning name, id)
  insert into sample_items select 'product:' || name, id from ins;

  insert into app.product_tags (product_id, tenant_id, tag)
  select i.id, p_tenant_id, t.tag
  from (values ('Es Kopi Susu Senja', 'coffee'), ('Es Kopi Susu Senja', 'sweet'), ('Matcha Latte', 'sweet'),
               ('Roti Bakar Cokelat', 'sweet'), ('Kentang Goreng', 'sharing')) as t(product, tag)
  join sample_items i on i.key = 'product:' || t.product;

  insert into app.outlet_prices (tenant_id, outlet_id, product_id, price)
  select p_tenant_id, p_outlet_id, i.id, x.price
  from (values ('Es Kopi Susu Senja', 25000), ('Americano', 22000), ('Matcha Latte', 28000),
               ('Croissant Butter', 24000), ('Roti Bakar Cokelat', 20000), ('Kentang Goreng', 18000))
       as x(product, price)
  join sample_items i on i.key = 'product:' || x.product;

  with ins as (
    insert into app.addon_groups (tenant_id, product_id, name, selection, is_required, sort_order)
    select p_tenant_id, i.id, g.name, g.selection::app.addon_selection, g.required, g.sort
    from (values ('Ukuran', 'single', true, 1), ('Pilihan susu', 'single', false, 2), ('Gula', 'single', false, 3))
         as g(name, selection, required, sort)
    join sample_items i on i.key = 'product:Es Kopi Susu Senja'
    returning name, id)
  insert into sample_items select 'group:' || name, id from ins;

  with ins as (
    insert into app.addon_options (tenant_id, group_id, name, sort_order)
    select p_tenant_id, g.id, o.name, o.sort
    from (values ('Ukuran', 'Regular', 1), ('Ukuran', 'Large', 2), ('Pilihan susu', 'Oat milk', 1),
                 ('Pilihan susu', 'Almond milk', 2), ('Gula', 'Normal', 1), ('Gula', 'Less sugar', 2),
                 ('Gula', 'No sugar', 3)) as o(grp, name, sort)
    join sample_items g on g.key = 'group:' || o.grp
    returning name, id)
  insert into sample_items select 'option:' || name, id from ins;

  insert into app.outlet_prices (tenant_id, outlet_id, addon_option_id, price)
  select p_tenant_id, p_outlet_id, i.id, x.price
  from (values ('Regular', 0), ('Large', 5000), ('Oat milk', 5000), ('Almond milk', 6000),
               ('Normal', 0), ('Less sugar', 0), ('No sugar', 0)) as x(option, price)
  join sample_items i on i.key = 'option:' || x.option;

  insert into app.recipe_items (tenant_id, product_id, stock_item_id, quantity)
  select p_tenant_id, p.id, s.id, r.qty
  from (values ('Es Kopi Susu Senja', 'Biji kopi house blend', 18), ('Es Kopi Susu Senja', 'Susu UHT', 150),
               ('Es Kopi Susu Senja', 'Gula aren cair', 20), ('Es Kopi Susu Senja', 'Cup 16oz', 1),
               ('Americano', 'Biji kopi house blend', 18), ('Americano', 'Cup 16oz', 1),
               ('Matcha Latte', 'Bubuk matcha', 5), ('Matcha Latte', 'Susu UHT', 200), ('Matcha Latte', 'Cup 16oz', 1),
               ('Croissant Butter', 'Croissant (frozen)', 1), ('Roti Bakar Cokelat', 'Roti tawar', 2),
               ('Kentang Goreng', 'Kentang beku', 150)) as r(product, stock, qty)
  join sample_items p on p.key = 'product:' || r.product
  join sample_items s on s.key = 'stock:' || r.stock;

  insert into app.recipe_items (tenant_id, addon_option_id, stock_item_id, quantity)
  select p_tenant_id, o.id, s.id, r.qty
  from (values ('Large', 'Biji kopi house blend', 6), ('Large', 'Susu UHT', 50),
               ('Oat milk', 'Susu UHT', -150), ('Oat milk', 'Susu oat', 150),
               ('Almond milk', 'Susu UHT', -150), ('Almond milk', 'Susu almond', 150),
               ('No sugar', 'Gula aren cair', -20)) as r(option, stock, qty)
  join sample_items o on o.key = 'option:' || r.option
  join sample_items s on s.key = 'stock:' || r.stock;

  insert into app.outlet_stock (outlet_id, stock_item_id, tenant_id, low_threshold)
  select p_outlet_id, s.id, p_tenant_id, t.min
  from (values ('Biji kopi house blend', 1000), ('Susu UHT', 4000), ('Susu oat', 1000), ('Susu almond', 1000),
               ('Gula aren cair', 1000), ('Bubuk matcha', 200), ('Croissant (frozen)', 10), ('Roti tawar', 10),
               ('Kentang beku', 2000), ('Cup 16oz', 50)) as t(stock, min)
  join sample_items s on s.key = 'stock:' || t.stock;

  insert into app.stock_movements (tenant_id, outlet_id, stock_item_id, type, quantity, note, actor_type)
  select p_tenant_id, p_outlet_id, s.id, 'restock', t.qty, 'Stok awal sample menu', 'system'
  from (values ('Biji kopi house blend', 2400), ('Susu UHT', 12000), ('Susu oat', 2000), ('Susu almond', 2000),
               ('Gula aren cair', 1500), ('Bubuk matcha', 500), ('Croissant (frozen)', 20), ('Roti tawar', 24),
               ('Kentang beku', 3000), ('Cup 16oz', 140)) as t(stock, qty)
  join sample_items s on s.key = 'stock:' || t.stock;

  drop table sample_items;
end $$;

revoke execute on function app.seed_sample_menu(uuid, uuid) from public;

-- Onboarding now also seeds the sample menu (same signature as 20261118000100).
create or replace function app.complete_owner_onboarding(
  p_auth_user_id   uuid,
  p_business_name  text,
  p_business_type  app.tenant_type,
  p_outlet_name    text,
  p_timezone       text,
  p_address        text,
  p_whatsapp_phone text
) returns table (tenant_id uuid, outlet_id uuid)
language plpgsql volatile security definer set search_path = '' as $$
declare
  inv      record;
  v_tenant uuid;
  v_outlet uuid;
begin
  select id, email into inv from app.owner_invitations
  where auth_user_id = p_auth_user_id and accepted_at is null and revoked_at is null
  for update;
  if not found then
    raise exception 'no open owner invitation' using errcode = 'P0002';
  end if;

  insert into app.tenants (name, type) values (trim(p_business_name), p_business_type)
  returning id into v_tenant;

  insert into app.users (id, tenant_id, email, display_name, role, invited_at, invitation_accepted_at)
  values (p_auth_user_id, v_tenant, inv.email, split_part(inv.email, '@', 1), 'owner', now(), now());

  insert into app.outlets (tenant_id, name, timezone, address, whatsapp_phone, order_prefix)
  values (v_tenant, trim(p_outlet_name), coalesce(p_timezone, 'Asia/Jakarta'),
          nullif(trim(p_address), ''), nullif(trim(p_whatsapp_phone), ''), 'A')
  returning id into v_outlet;

  insert into app.outlet_opening_hours (outlet_id, tenant_id, weekday, opens_at, closes_at)
  select v_outlet, v_tenant, d, '08:00', '22:00' from generate_series(1, 7) d;

  perform app.seed_sample_menu(v_tenant, v_outlet);

  update app.owner_invitations set accepted_at = now(), tenant_id = v_tenant where id = inv.id;

  insert into app.audit_events (tenant_id, actor_type, actor_id, action, entity_type, entity_id, data)
  values (v_tenant, 'user', p_auth_user_id, 'tenant.created', 'tenant', v_tenant::text,
          jsonb_build_object('outlet_id', v_outlet, 'invitation_id', inv.id, 'sample_menu', true));

  return query select v_tenant, v_outlet;
end $$;

-- Fix (T-020): the Wave 0 trigger inserted the raw movement quantity with ON CONFLICT
-- DO UPDATE. CHECK constraints are evaluated on the proposed insert row first, so any
-- outgoing movement (waste, sale) failed on_hand >= 0 even with enough stock. Update
-- the existing row first; insert only when the item has no row at this outlet yet.
-- The row lock taken by the UPDATE serializes concurrent movements on one item.
create or replace function app.apply_stock_movement() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  update app.outlet_stock set on_hand = on_hand + new.quantity, updated_at = now()
  where outlet_id = new.outlet_id and stock_item_id = new.stock_item_id;
  if not found then
    insert into app.outlet_stock (outlet_id, stock_item_id, tenant_id, on_hand)
    values (new.outlet_id, new.stock_item_id, new.tenant_id, new.quantity);
  end if;
  return new;   -- the on_hand >= 0 check rejects movements that would go negative
end $$;
