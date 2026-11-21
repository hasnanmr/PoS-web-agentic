-- Field encryption (app.core.crypto; glossary §10). The API encrypts with AES-256-GCM before
-- writing and decrypts after reading; the database never sees the key. Values are text
-- `enc:v1:<base64>`. Equality lookups use keyed HMAC-SHA256 blind indexes (`*_index`), and
-- random tokens are looked up by their SHA-256 (`*_hash`).
--
-- * `customers` (web chat, not in production before this change): name and phone must be
--   ciphertext; `phone_index` finds a number without decrypting.
-- * `orders.customer_name`, `orders.delivery_address`, `reservations.guest_name`,
--   `reservations.guest_phone`: written encrypted from now on; rows written before stay
--   readable until `app.cli encrypt-existing` re-writes them.
-- * `reservations.booking_code`: ciphertext for display (C11/C12) + `booking_code_index`
--   for "Cari dengan kode + HP" and uniqueness per outlet.
-- * `tables.qr_token`: ciphertext for the O8 re-download + `qr_token_hash` (SHA-256 of the
--   random token) for the public lookup.

-- Customers ---------------------------------------------------------------------------------------
alter table app.customers drop constraint customers_name_check;
alter table app.customers drop constraint customers_phone_check;
alter table app.customers add constraint customers_name_encrypted
  check (name is null or name like 'enc:v1:%');
alter table app.customers add constraint customers_phone_encrypted
  check (phone is null or phone like 'enc:v1:%');
alter table app.customers add column phone_index text
  check (phone_index is null or phone_index ~ '^[0-9a-f]{64}$');
alter table app.customers add constraint phone_index_with_phone
  check ((phone is null) = (phone_index is null));
drop index if exists app.customers_outlet_id_phone_idx;
create index on app.customers (outlet_id, phone_index) where phone_index is not null;

create or replace function app.anonymize_customer(p_customer_id uuid) returns void
language sql set search_path = '' as $$
  update app.customers
     set name = null, phone = null, phone_index = null, is_anonymized = true,
         anonymized_at = now()
   where id = p_customer_id and not is_anonymized
$$;

-- Orders: ciphertext is longer than the plaintext limits ----------------------------------------
alter table app.orders drop constraint orders_customer_name_check;

-- Reservations --------------------------------------------------------------------------------------
alter table app.reservations drop constraint reservations_booking_code_check;
drop index app.reservations_booking_code_key;
alter table app.reservations add column booking_code_index text
  check (booking_code_index is null or booking_code_index ~ '^[0-9a-f]{64}$');
alter table app.reservations add column guest_phone_index text
  check (guest_phone_index is null or guest_phone_index ~ '^[0-9a-f]{64}$');
create unique index reservations_booking_code_key on app.reservations (outlet_id, booking_code_index)
  where booking_code_index is not null;
create index on app.reservations (outlet_id, guest_phone_index) where guest_phone_index is not null;
alter table app.reservations drop constraint web_chat_booking;
alter table app.reservations add constraint web_chat_booking check (
  source <> 'web_chat' or (booking_code like 'enc:v1:%' and booking_code_index is not null
                           and access_key_hash is not null and customer_id is not null));

create or replace function app.reservations_anonymize_when_finished() returns trigger
language plpgsql set search_path = '' as $$
begin
  if new.source = 'web_chat'
     and new.status in ('completed', 'cancelled', 'no_show') and old.status is distinct from new.status then
    new.guest_name := null;
    new.guest_phone := null;
    new.guest_phone_index := null;
    if new.customer_id is not null then
      perform app.anonymize_customer(new.customer_id);
    end if;
  end if;
  return new;
end $$;

-- Tables: QR token --------------------------------------------------------------------------------
alter table app.tables add column qr_token_hash text
  check (qr_token_hash is null or qr_token_hash ~ '^[0-9a-f]{64}$');
update app.tables set qr_token_hash = encode(sha256(convert_to(qr_token, 'UTF8')), 'hex');
alter table app.tables alter column qr_token_hash set not null;
create unique index tables_qr_token_hash_key on app.tables (qr_token_hash);

-- A token still written in plaintext (the column default, SQL fixtures) gets its hash here; the
-- API writes ciphertext together with the hash of the plaintext token.
create function app.tables_qr_token_hash() returns trigger
language plpgsql set search_path = '' as $$
begin
  if new.qr_token not like 'enc:v1:%' then
    new.qr_token_hash := encode(sha256(convert_to(new.qr_token, 'UTF8')), 'hex');
  elsif new.qr_token_hash is null then
    raise exception 'an encrypted qr_token needs qr_token_hash' using errcode = '23502';
  end if;
  return new;
end $$;
create trigger qr_token_hash before insert or update of qr_token on app.tables
  for each row execute function app.tables_qr_token_hash();

-- The public lookup now takes the SHA-256 of the token from the URL.
drop function app.resolve_table_qr(text);
create function app.resolve_table_qr(p_token_hash text)
returns table (
  tenant_id uuid, outlet_id uuid, table_id uuid, table_name text, area text,
  outlet_name text, timezone text, table_qr_target text, whatsapp_status text,
  whatsapp_phone text, unpaid_timeout_minutes integer, has_qris boolean
)
language sql stable security definer set search_path = '' as $$
  select o.tenant_id, o.id, t.id, t.name, t.area, o.name, o.timezone, o.table_qr_target,
         o.whatsapp_status, o.whatsapp_phone, o.unpaid_timeout_minutes,
         exists (select 1 from app.outlet_qris q where q.outlet_id = o.id)
  from app.tables t
  join app.outlets o on o.id = t.outlet_id
  where t.qr_token_hash = p_token_hash and t.is_active and o.is_active
$$;
revoke execute on function app.resolve_table_qr(text) from public;
grant execute on function app.resolve_table_qr(text) to app_backend;
