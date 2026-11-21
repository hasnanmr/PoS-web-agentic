-- T-147 (O8 on page 07): the table QR always opens the web chat, so the "Tujuan QR meja" setting
-- (`outlets.table_qr_target`, PR #47) and its WhatsApp fields in the public table lookup go.
-- WhatsApp stays a Phase 3 channel (T-148); its outlet columns are kept.

drop function app.resolve_table_qr(text);
create function app.resolve_table_qr(p_token_hash text)
returns table (
  tenant_id uuid, outlet_id uuid, table_id uuid, table_name text, area text,
  outlet_name text, timezone text, unpaid_timeout_minutes integer, has_qris boolean
)
language sql stable security definer set search_path = '' as $$
  select o.tenant_id, o.id, t.id, t.name, t.area, o.name, o.timezone, o.unpaid_timeout_minutes,
         exists (select 1 from app.outlet_qris q where q.outlet_id = o.id)
  from app.tables t
  join app.outlets o on o.id = t.outlet_id
  where t.qr_token_hash = p_token_hash and t.is_active and o.is_active
$$;
revoke execute on function app.resolve_table_qr(text) from public;
grant execute on function app.resolve_table_qr(text) to app_backend;

alter table app.outlets drop column table_qr_target;
