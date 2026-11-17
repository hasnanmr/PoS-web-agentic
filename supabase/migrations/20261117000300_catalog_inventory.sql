-- T-004: menu, add-ons, per-outlet prices, tags, ingredients, recipes, stock movements.
-- Menu items, add-ons, and recipes are tenant-level (shared by outlets, FR1.2).
-- Prices, stock levels, and thresholds are per outlet.

create table app.products (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       uuid not null references app.tenants (id),
  name            text not null check (length(trim(name)) between 1 and 120),
  category        text,
  description     text,
  photo_path      text,                -- required before catalog sync (FR2.11), enforced by the app
  is_owner_pick   boolean not null default false,
  owner_pick_rank integer,
  is_active       boolean not null default true,
  is_sample       boolean not null default false,   -- sample menu for new tenants (FR2.12)
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  unique (id, tenant_id)
);
create index on app.products (tenant_id);

create table app.product_tags (
  product_id uuid not null,
  tenant_id  uuid not null,
  tag        text not null check (tag = lower(tag) and length(tag) between 1 and 40),
  primary key (product_id, tag),
  foreign key (product_id, tenant_id) references app.products (id, tenant_id) on delete cascade
);

create table app.addon_groups (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null,
  product_id    uuid not null,
  name          text not null,
  selection     app.addon_selection not null,
  is_required   boolean not null default false,
  sort_order    integer not null default 0,
  created_at    timestamptz not null default now(),
  unique (id, tenant_id),
  foreign key (product_id, tenant_id) references app.products (id, tenant_id) on delete cascade
);

create table app.addon_options (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null,
  group_id    uuid not null,
  name        text not null,
  sort_order  integer not null default 0,
  is_active   boolean not null default true,
  created_at  timestamptz not null default now(),
  unique (id, tenant_id),
  foreign key (group_id, tenant_id) references app.addon_groups (id, tenant_id) on delete cascade
);

-- Max 10 options per add-on group (FR4.9, AC4.6).
create function app.enforce_addon_option_limit() returns trigger
language plpgsql as $$
begin
  perform 1 from app.addon_groups where id = new.group_id for update;
  if (select count(*) from app.addon_options where group_id = new.group_id) >= 10 then
    raise exception 'an add-on group can have at most 10 options' using errcode = 'check_violation';
  end if;
  return new;
end $$;
create trigger addon_option_limit before insert on app.addon_options
  for each row execute function app.enforce_addon_option_limit();

-- Per-outlet prices for products and add-on options (FR4.8). Exactly one target.
create table app.outlet_prices (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null,
  outlet_id        uuid not null,
  product_id       uuid,
  addon_option_id  uuid,
  price            bigint not null check (price >= 0),
  is_available     boolean not null default true,   -- owner can hide an item at one outlet
  updated_at       timestamptz not null default now(),
  constraint one_target check ((product_id is null) <> (addon_option_id is null)),
  foreign key (outlet_id, tenant_id)       references app.outlets (id, tenant_id),
  foreign key (product_id, tenant_id)      references app.products (id, tenant_id) on delete cascade,
  foreign key (addon_option_id, tenant_id) references app.addon_options (id, tenant_id) on delete cascade
);
create unique index outlet_prices_product_key on app.outlet_prices (outlet_id, product_id) where product_id is not null;
create unique index outlet_prices_option_key  on app.outlet_prices (outlet_id, addon_option_id) where addon_option_id is not null;

create table app.stock_items (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references app.tenants (id),
  name        text not null check (length(trim(name)) between 1 and 120),
  unit        app.stock_unit not null,
  is_active   boolean not null default true,
  created_at  timestamptz not null default now(),
  unique (tenant_id, name),
  unique (id, tenant_id)
);

-- Per-outlet stock level and low-stock threshold. on_hand is a cached sum of
-- stock_movements, maintained only by the movement trigger below, and is the row
-- locked during order creation (FR4.6).
create table app.outlet_stock (
  outlet_id      uuid not null,
  stock_item_id  uuid not null,
  tenant_id      uuid not null,
  on_hand        numeric(14,3) not null default 0 check (on_hand >= 0),
  low_threshold  numeric(14,3) not null default 0 check (low_threshold >= 0),
  updated_at     timestamptz not null default now(),
  primary key (outlet_id, stock_item_id),
  foreign key (outlet_id, tenant_id)     references app.outlets (id, tenant_id),
  foreign key (stock_item_id, tenant_id) references app.stock_items (id, tenant_id)
);

-- Recipe lines: per product portion, or the delta an add-on option adds.
create table app.recipe_items (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       uuid not null,
  product_id      uuid,
  addon_option_id uuid,
  stock_item_id   uuid not null,
  quantity        numeric(14,3) not null,   -- add-on deltas may be negative (e.g. less milk)
  constraint one_owner check ((product_id is null) <> (addon_option_id is null)),
  constraint product_qty_positive check (product_id is null or quantity > 0),
  foreign key (product_id, tenant_id)      references app.products (id, tenant_id) on delete cascade,
  foreign key (addon_option_id, tenant_id) references app.addon_options (id, tenant_id) on delete cascade,
  foreign key (stock_item_id, tenant_id)   references app.stock_items (id, tenant_id)
);
create unique index recipe_items_product_key on app.recipe_items (product_id, stock_item_id) where product_id is not null;
create unique index recipe_items_option_key  on app.recipe_items (addon_option_id, stock_item_id) where addon_option_id is not null;

-- Append-only stock movements (FR4.2). order_id is a plain uuid here; its FK is
-- added in the orders migration.
create table app.stock_movements (
  id             bigint generated always as identity primary key,
  tenant_id      uuid not null,
  outlet_id      uuid not null,
  stock_item_id  uuid not null,
  type           app.stock_movement_type not null,
  quantity       numeric(14,3) not null check (quantity <> 0),  -- signed: + in, - out
  order_id       uuid,
  note           text,
  actor_type     app.actor_type not null,
  actor_id       uuid,
  created_at     timestamptz not null default now(),
  constraint movement_sign check (
    (type in ('sale', 'waste') and quantity < 0) or
    (type in ('sale_reversal', 'restock') and quantity > 0) or
    type = 'adjustment'),
  constraint movement_actor check (actor_type in ('system', 'agent') or actor_id is not null),
  foreign key (outlet_id, tenant_id)     references app.outlets (id, tenant_id),
  foreign key (stock_item_id, tenant_id) references app.stock_items (id, tenant_id)
);
create index on app.stock_movements (outlet_id, stock_item_id, created_at desc);
create index on app.stock_movements (order_id) where order_id is not null;

create function app.apply_stock_movement() returns trigger
language plpgsql as $$
begin
  insert into app.outlet_stock (outlet_id, stock_item_id, tenant_id, on_hand)
  values (new.outlet_id, new.stock_item_id, new.tenant_id, new.quantity)
  on conflict (outlet_id, stock_item_id)
  do update set on_hand = app.outlet_stock.on_hand + excluded.on_hand, updated_at = now();
  return new;   -- the on_hand >= 0 check rejects movements that would go negative
end $$;
create trigger apply_movement after insert on app.stock_movements
  for each row execute function app.apply_stock_movement();
create trigger append_only before update or delete on app.stock_movements
  for each row execute function app.reject_update_delete();

create trigger touch before update on app.products     for each row execute function app.touch_updated_at();
create trigger touch before update on app.outlet_prices for each row execute function app.touch_updated_at();
