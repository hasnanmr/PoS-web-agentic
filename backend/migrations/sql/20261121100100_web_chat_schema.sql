-- T-140 (PRD v0.20 §5.2, §5.6, §5.12): schema for the customer web chat.
--
-- * Outlet link `/o/<slug>`: `outlets.public_slug`, unique across the platform and changeable;
--   the old link stops working at once (FR2.10). Existing and new outlets get a default slug.
-- * Channel `web_online`: online pickup/delivery orders from the outlet link, always paid first,
--   never on a bill, with a per-order access key like `web_table` (FR2.3, FR2.6, FR2.15).
-- * `customers`: name and phone per order or booking (no accounts, no profile across visits,
--   FR12.3). The delivery address stays on `orders.delivery_address`. Personal data is
--   anonymized as soon as the order or booking is finished (FR12.2), by the triggers below;
--   ledger and stock rows never hold any of it (FR12.4).
-- * `privacy_notice_acknowledgements`: which notice version was shown, and when (FR12.1).
-- * `chat_sessions`: the conversation state per phone (step + cart), so a refresh resumes the
--   chat; no personal data is stored here (FR6.2).
-- * Web chat bookings: `reservations.booking_code` + access key (FR9.4, FR9.5).
--
-- Decision (T-140): the WhatsApp tables (`whatsapp_contacts`, `conversations`, `messages`,
-- `processed_messages`, the outlet WhatsApp and catalog columns) are KEPT for the optional
-- Phase 3 channel (T-148); no MVP flow writes them. The table QR target column
-- (`outlets.table_qr_target`) is dropped together with its O8 setting (T-147), so the admin app
-- keeps working until that change ships.

-- Outlet link -----------------------------------------------------------------------------------
create function app.slugify(p_text text) returns text
language sql immutable set search_path = '' as $$
  select coalesce(nullif(left(trim(both '-' from regexp_replace(
           lower(coalesce(p_text, '')), '[^a-z0-9]+', '-', 'g')), 30), ''), 'outlet')
$$;

-- `kopi-senja-dago-3f9a`: readable, and the id suffix makes it unique; the owner can change it.
-- When that slug is already taken (same name and id prefix, or an owner-chosen slug), the suffix
-- grows (8, 12, then all 32 hex characters of the id, which is unique).
create function app.default_outlet_slug(p_name text, p_id uuid, p_suffix integer default 4)
returns text language sql immutable set search_path = '' as $$
  -- The name part is shortened so the whole slug stays within 40 characters.
  select coalesce(nullif(trim(both '-' from left(app.slugify(p_name), 39 - p_suffix)), ''), 'o')
         || '-' || left(replace(p_id::text, '-', ''), p_suffix)
$$;

-- Definer: the check must see every tenant's slugs (RLS would hide them from app_backend).
create function app.unique_outlet_slug(p_name text, p_id uuid) returns text
language plpgsql stable security definer set search_path = '' as $$
declare
  v_len integer;
  v_slug text;
begin
  foreach v_len in array array[4, 8, 12, 32] loop
    v_slug := app.default_outlet_slug(p_name, p_id, v_len);
    if not exists (select 1 from app.outlets o where o.public_slug = v_slug and o.id <> p_id) then
      return v_slug;
    end if;
  end loop;
  return v_slug;  -- the full id: unique
end $$;

alter table app.outlets add column public_slug text
  check (public_slug ~ '^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$' and public_slug !~ '--');
do $$
declare
  r record;
begin
  for r in select id, name from app.outlets order by created_at, id loop
    update app.outlets set public_slug = app.unique_outlet_slug(r.name, r.id) where id = r.id;
  end loop;
end $$;
alter table app.outlets alter column public_slug set not null;
create unique index outlets_public_slug_key on app.outlets (public_slug);

create function app.outlet_default_slug() returns trigger
language plpgsql set search_path = '' as $$
begin
  if new.public_slug is null then
    new.public_slug := app.unique_outlet_slug(new.name, new.id);
  end if;
  return new;
end $$;
create trigger default_slug before insert on app.outlets
  for each row execute function app.outlet_default_slug();
revoke execute on function app.unique_outlet_slug(text, uuid) from public;
grant execute on function app.unique_outlet_slug(text, uuid) to app_backend;

-- Customers (personal data, FR12) ---------------------------------------------------------------
create table app.customers (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null,
  outlet_id      uuid not null,
  name           text check (name is null or length(trim(name)) between 1 and 60),
  phone          text check (phone is null or phone ~ '^\+?[0-9]{8,15}$'),
  is_anonymized  boolean not null default false,
  anonymized_at  timestamptz,
  created_at     timestamptz not null default now(),
  unique (id, tenant_id),
  unique (id, outlet_id),
  foreign key (outlet_id, tenant_id) references app.outlets (id, tenant_id),
  constraint anonymized_has_no_pii check (
    (not is_anonymized and name is not null) or
    (is_anonymized and name is null and phone is null and anonymized_at is not null))
);
create index on app.customers (outlet_id, phone) where phone is not null;

create table app.privacy_notice_acknowledgements (
  id               bigint generated always as identity primary key,
  tenant_id        uuid not null,
  outlet_id        uuid not null,
  customer_id      uuid not null,
  notice_version   text not null check (length(notice_version) between 1 and 40),
  acknowledged_at  timestamptz not null default now(),
  foreign key (customer_id, outlet_id) references app.customers (id, outlet_id)
);
create index on app.privacy_notice_acknowledgements (customer_id);

-- Orders: channel web_online ------------------------------------------------------------------
alter table app.orders add column customer_id uuid;
alter table app.orders add constraint orders_customer_fk
  foreign key (customer_id, outlet_id) references app.customers (id, outlet_id);
create index on app.orders (customer_id) where customer_id is not null;

alter table app.orders drop constraint channel_type;
alter table app.orders add constraint channel_type check (
  (channel = 'whatsapp_online' and type in ('delivery', 'pickup') and payment_mode = 'pay_first') or
  (channel = 'whatsapp_table'  and type = 'dine_in' and table_id is not null) or
  (channel = 'web_table'       and type = 'dine_in' and table_id is not null
                               and payment_mode = 'pay_first' and bill_id is null) or
  (channel = 'web_online'      and type in ('delivery', 'pickup') and table_id is null
                               and payment_mode = 'pay_first' and bill_id is null) or
  (channel = 'counter'         and type in ('dine_in', 'takeaway')));

alter table app.orders drop constraint web_access_key;
alter table app.orders add constraint web_access_key check (
  (channel in ('web_table', 'web_online')) = (access_key_hash is not null));
-- An online order always names who to call (FR2.6); until it is anonymized.
alter table app.orders add constraint web_online_customer check (
  channel <> 'web_online' or customer_id is not null);

-- Reservations: booking code + access key -------------------------------------------------------
alter table app.reservations add column customer_id uuid;
alter table app.reservations add constraint reservations_customer_fk
  foreign key (customer_id, outlet_id) references app.customers (id, outlet_id);
-- Six characters without look-alikes (no 0/O, 1/I/L), shown in C11 and typed in C12.
alter table app.reservations add column booking_code text
  check (booking_code is null or booking_code ~ '^[A-HJKMNP-Z2-9]{6}$');
alter table app.reservations add column access_key_hash text
  check (access_key_hash is null or access_key_hash ~ '^[0-9a-f]{64}$');
create unique index reservations_booking_code_key on app.reservations (outlet_id, booking_code)
  where booking_code is not null;
create index on app.reservations (customer_id) where customer_id is not null;
alter table app.reservations add constraint web_chat_booking check (
  source <> 'web_chat' or (booking_code is not null and access_key_hash is not null
                           and customer_id is not null));

-- Chat sessions (FR6.2) ---------------------------------------------------------------------------
-- The page creates an opaque session id and keeps it on the phone; only its SHA-256 is stored.
-- One row per phone per entry point (outlet link, or one table's QR). The cart holds product and
-- add-on ids only, never a name, phone, or address (those stay on the phone, FR12.3).
create table app.chat_sessions (
  id                uuid primary key default gen_random_uuid(),
  tenant_id         uuid not null,
  outlet_id         uuid not null,
  table_id          uuid,
  session_key_hash  text not null check (session_key_hash ~ '^[0-9a-f]{64}$'),
  step              text not null default 'main_menu' check (step ~ '^[a-z0-9_.:-]{1,60}$'),
  cart              jsonb not null default '{"lines": []}'::jsonb
                    check (jsonb_typeof(cart) = 'object' and pg_column_size(cart) <= 65536),
  fulfillment       text check (fulfillment in ('pickup', 'delivery')),
  last_activity_at  timestamptz not null default now(),
  created_at        timestamptz not null default now(),
  foreign key (outlet_id, tenant_id) references app.outlets (id, tenant_id),
  foreign key (table_id, outlet_id) references app.tables (id, outlet_id),
  constraint table_has_no_fulfillment check (table_id is null or fulfillment is null)
);
create unique index chat_sessions_key on app.chat_sessions (outlet_id, table_id, session_key_hash)
  nulls not distinct;
create index on app.chat_sessions (last_activity_at);

-- RLS + privileges ------------------------------------------------------------------------------
do $$
declare
  t text;
begin
  foreach t in array array['customers', 'privacy_notice_acknowledgements', 'chat_sessions'] loop
    execute format('alter table app.%I enable row level security', t);
    execute format($p$
      create policy outlet_scope on app.%I to app_backend
        using      (tenant_id = app.current_tenant() and app.can_access_outlet(outlet_id))
        with check (tenant_id = app.current_tenant() and app.can_access_outlet(outlet_id))
    $p$, t);
    execute format($p$
      create policy no_device on app.%I as restrictive to app_backend
        using (app.current_actor() is distinct from 'device')
        with check (app.current_actor() is distinct from 'device')
    $p$, t);
  end loop;
end $$;

grant select, insert, update on app.customers to app_backend;
grant select, insert, update, delete on app.chat_sessions to app_backend;
-- Append-only: what was shown and when must not change afterwards.
grant select, insert on app.privacy_notice_acknowledgements to app_backend;

-- Anonymization when the order or booking is finished (FR12.2, AC12.2) ---------------------------
-- Orders keep their items, totals, and ledger entries; only the personal fields are cleared.
create function app.anonymize_customer(p_customer_id uuid) returns void
language sql set search_path = '' as $$
  update app.customers
     set name = null, phone = null, is_anonymized = true, anonymized_at = now()
   where id = p_customer_id and not is_anonymized
$$;

create function app.orders_anonymize_when_finished() returns trigger
language plpgsql set search_path = '' as $$
begin
  if new.channel in ('web_table', 'web_online')
     and new.status in ('completed', 'cancelled') and old.status is distinct from new.status then
    new.customer_name := null;
    new.delivery_address := null;
    if new.customer_id is not null then
      perform app.anonymize_customer(new.customer_id);
    end if;
  end if;
  return new;
end $$;
create trigger anonymize_when_finished before update of status on app.orders
  for each row execute function app.orders_anonymize_when_finished();

create function app.reservations_anonymize_when_finished() returns trigger
language plpgsql set search_path = '' as $$
begin
  if new.source = 'web_chat'
     and new.status in ('completed', 'cancelled', 'no_show') and old.status is distinct from new.status then
    new.guest_name := null;
    new.guest_phone := null;
    if new.customer_id is not null then
      perform app.anonymize_customer(new.customer_id);
    end if;
  end if;
  return new;
end $$;
create trigger anonymize_when_finished before update of status on app.reservations
  for each row execute function app.reservations_anonymize_when_finished();

-- Cross-tenant lookup for the outlet link ---------------------------------------------------------
-- Like `resolve_table_qr`: the chat has no sign-in, so the slug is resolved to its tenant and
-- outlet before any tenant context exists. Active outlets only; an unknown or old slug returns
-- no row (C13 card 1).
create function app.resolve_outlet_slug(p_slug text)
returns table (
  tenant_id uuid, outlet_id uuid, outlet_name text, timezone text,
  unpaid_timeout_minutes integer, delivery_fee bigint, has_qris boolean,
  reservations_enabled boolean
)
language sql stable security definer set search_path = '' as $$
  select o.tenant_id, o.id, o.name, o.timezone, o.unpaid_timeout_minutes, o.delivery_fee,
         exists (select 1 from app.outlet_qris q where q.outlet_id = o.id),
         coalesce((select rs.is_enabled from app.reservation_settings rs
                   where rs.outlet_id = o.id), false)
  from app.outlets o
  where o.public_slug = lower(p_slug) and o.is_active
    and length(p_slug) between 3 and 40
$$;

revoke execute on function app.resolve_outlet_slug(text) from public;
grant execute on function app.resolve_outlet_slug(text) to app_backend;
revoke execute on function app.anonymize_customer(uuid) from public;
grant execute on function app.anonymize_customer(uuid) to app_backend;
