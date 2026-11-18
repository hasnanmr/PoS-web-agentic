-- T-029: request idempotency for writes that must not run twice (order creation,
-- bill close, stock movements, shift close). The first successful response is stored
-- and returned again for a retry with the same key; a key is scoped per tenant and
-- per operation.

create table app.idempotency_keys (
  tenant_id   uuid not null references app.tenants (id),
  scope       text not null,               -- e.g. 'order.create:<outlet_id>'
  key         text not null check (length(key) between 8 and 200),
  response    jsonb not null,
  created_at  timestamptz not null default now(),
  primary key (tenant_id, scope, key)
);

alter table app.idempotency_keys enable row level security;
create policy tenant_scope on app.idempotency_keys to app_backend
  using (tenant_id = app.current_tenant()) with check (tenant_id = app.current_tenant());
grant select, insert on app.idempotency_keys to app_backend;

-- Order numbers run per outlet from 1001 (#A-1001). Called with a transaction-level
-- advisory lock on the outlet so two counters never get the same number.
create function app.next_order_no(p_outlet_id uuid) returns integer
language plpgsql volatile security definer set search_path = '' as $$
declare
  v_next integer;
begin
  if not app.can_access_outlet(p_outlet_id) then
    raise exception 'no access to outlet' using errcode = '42501';
  end if;
  perform pg_advisory_xact_lock(hashtextextended('order_no:' || p_outlet_id::text, 0));
  select coalesce(max(order_no), 1000) + 1 into v_next from app.orders where outlet_id = p_outlet_id;
  return v_next;
end $$;

revoke execute on function app.next_order_no(uuid) from public;
grant execute on function app.next_order_no(uuid) to app_backend;
