-- T-133 (#44): customer table web page (wireframe Q0–Q5, O8; PRD FR2.13–FR2.16).
--
-- * Web orders (`web_table`) are always paid first with the outlet's static QRIS and never join
--   the table's open bill.
-- * Each web order carries a per-order access key (stored as a SHA-256 hash): a phone reads only
--   the orders it placed (FR2.15).
-- * "Saya sudah bayar" is a payment proof without a screenshot (`kind = customer_claim`), so the
--   existing S4 review (accept / reject) confirms it and `proof_submitted` stops the unpaid timer.
-- * The owner picks where the QR leads per outlet (O8 "Tujuan QR meja").

-- Orders --------------------------------------------------------------------------------------
alter table app.orders drop constraint channel_type;
alter table app.orders add constraint channel_type check (
  (channel = 'whatsapp_online' and type in ('delivery', 'pickup') and payment_mode = 'pay_first') or
  (channel = 'whatsapp_table'  and type = 'dine_in' and table_id is not null) or
  (channel = 'web_table'       and type = 'dine_in' and table_id is not null
                               and payment_mode = 'pay_first' and bill_id is null) or
  (channel = 'counter'         and type in ('dine_in', 'takeaway')));

-- Q3 "Nama pemesan (opsional)": free text, no phone number, so no membership consent (§5.12).
alter table app.orders add column customer_name text
  check (customer_name is null or length(trim(customer_name)) between 1 and 40);
-- Q3 "Catatan untuk dapur (opsional)", shown on the S2 card.
alter table app.orders add column note text
  check (note is null or length(trim(note)) between 1 and 200);
-- SHA-256 (hex) of the access key returned once to the phone that placed a web order.
alter table app.orders add column access_key_hash text
  check (access_key_hash is null or access_key_hash ~ '^[0-9a-f]{64}$');
alter table app.orders add constraint web_access_key check (
  (channel = 'web_table') = (access_key_hash is not null));

-- Payment proofs: "Saya sudah bayar" without a screenshot -------------------------------------
alter table app.payment_proofs add column kind text not null default 'screenshot'
  check (kind in ('screenshot', 'customer_claim'));
alter table app.payment_proofs alter column storage_path drop not null;
alter table app.payment_proofs add constraint proof_kind_fields check (
  (kind = 'screenshot' and storage_path is not null) or
  (kind = 'customer_claim' and storage_path is null));

-- Outlets: where the table QR leads (O8) -------------------------------------------------------
alter table app.outlets add column table_qr_target text not null default 'web_whatsapp'
  check (table_qr_target in ('web_whatsapp', 'web', 'whatsapp'));

-- Cross-tenant lookup for the public table page -------------------------------------------------
-- The page has no sign-in: resolve the table token to its tenant, outlet, and table before any
-- tenant context exists (like the WhatsApp webhook resolver). Active tables of active outlets
-- only; returns no row for an unknown or replaced token (Q0).
create function app.resolve_table_qr(p_token text)
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
  where t.qr_token = p_token and t.is_active and o.is_active
    and length(p_token) between 16 and 64
$$;

revoke execute on function app.resolve_table_qr(text) from public;
grant execute on function app.resolve_table_qr(text) to app_backend;
