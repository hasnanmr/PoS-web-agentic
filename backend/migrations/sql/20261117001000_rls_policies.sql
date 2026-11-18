-- T-005: row-level security and table privileges for app_backend.
--
-- RLS is ENABLED (not FORCED) on every table. app_backend is never a table owner,
-- so RLS always applies to it; the migration role owns the tables and stays exempt,
-- which lets the few SECURITY DEFINER functions (token hook, outlet resolver,
-- job claim, access helpers) read across tenants without policy recursion.
-- This deviates from the FORCE in the Appendix B.5 sketch on purpose; the smoke
-- tests assert app_backend owns nothing and has no BYPASSRLS.

-- Outlet-scoped tables: tenant match + live outlet access check.
do $$
declare
  t text;
begin
  foreach t in array array[
    'outlet_opening_hours', 'reservation_settings', 'cash_drawers', 'tables',
    'attendance_devices', 'attendance_pairing_codes', 'outlet_prices', 'outlet_stock',
    'stock_movements', 'conversations', 'messages', 'processed_messages',
    'cashier_shifts', 'bills', 'orders', 'order_items', 'order_events', 'payments',
    'payment_proofs', 'ledger_entries', 'reservations', 'reservation_events',
    'attendance_records', 'attendance_events'
  ] loop
    execute format('alter table app.%I enable row level security', t);
    execute format($p$
      create policy outlet_scope on app.%I to app_backend
        using      (tenant_id = app.current_tenant() and app.can_access_outlet(outlet_id))
        with check (tenant_id = app.current_tenant() and app.can_access_outlet(outlet_id))
    $p$, t);
  end loop;
end $$;

-- Tenant-scoped tables (shared by the tenant's outlets).
do $$
declare
  t text;
begin
  foreach t in array array[
    'users', 'products', 'product_tags', 'addon_groups', 'addon_options', 'stock_items',
    'recipe_items', 'whatsapp_contacts', 'customer_addresses', 'customer_consents',
    'scheduled_jobs'
  ] loop
    execute format('alter table app.%I enable row level security', t);
    execute format($p$
      create policy tenant_scope on app.%I to app_backend
        using      (tenant_id = app.current_tenant())
        with check (tenant_id = app.current_tenant())
    $p$, t);
  end loop;
end $$;

alter table app.tenants enable row level security;
create policy tenant_self on app.tenants to app_backend
  using (id = app.current_tenant()) with check (id = app.current_tenant());

alter table app.outlets enable row level security;
create policy outlet_self on app.outlets to app_backend
  using      (tenant_id = app.current_tenant() and app.can_access_outlet(id))
  with check (tenant_id = app.current_tenant() and (app.is_owner() or app.current_actor() = 'system'));

-- Staff see only their own assignments; owners and workers see all in the tenant.
alter table app.staff_outlets enable row level security;
create policy staff_outlets_scope on app.staff_outlets to app_backend
  using (tenant_id = app.current_tenant()
         and (app.is_owner() or app.current_actor() in ('system', 'agent') or user_id = app.current_user_id()))
  with check (tenant_id = app.current_tenant() and (app.is_owner() or app.current_actor() = 'system'));

-- Add-on selections inherit access from their order item.
alter table app.order_item_addons enable row level security;
create policy via_order_item on app.order_item_addons to app_backend
  using      (tenant_id = app.current_tenant()
              and exists (select 1 from app.order_items oi where oi.id = order_item_id))
  with check (tenant_id = app.current_tenant()
              and exists (select 1 from app.order_items oi where oi.id = order_item_id));

-- Audit: anyone in the tenant can append; only the owner (O11, O13) and workers read.
alter table app.audit_events enable row level security;
create policy audit_insert on app.audit_events for insert to app_backend
  with check (tenant_id = app.current_tenant()
              and (outlet_id is null or app.can_access_outlet(outlet_id)));
create policy audit_read on app.audit_events for select to app_backend
  using (tenant_id = app.current_tenant() and (app.is_owner() or app.current_actor() = 'system'));

-- Owner invitations: no direct access; only the SECURITY DEFINER functions.
alter table app.owner_invitations enable row level security;

-- Privileges ---------------------------------------------------------------------
-- Mutable tables.
grant select, insert, update, delete on
  app.outlet_opening_hours, app.cash_drawers, app.tables, app.attendance_devices,
  app.attendance_pairing_codes, app.outlet_prices, app.conversations, app.messages,
  app.processed_messages, app.bills, app.orders, app.order_items, app.order_item_addons,
  app.payment_proofs, app.reservations, app.attendance_records, app.products,
  app.product_tags, app.addon_groups, app.addon_options, app.stock_items, app.recipe_items,
  app.whatsapp_contacts, app.customer_addresses, app.scheduled_jobs, app.staff_outlets
  to app_backend;
grant select, insert, update on app.outlets, app.users, app.cashier_shifts to app_backend;
grant select, update on app.tenants, app.reservation_settings to app_backend;
grant select, insert on app.payments to app_backend;

-- Append-only tables: no UPDATE/DELETE privilege at all (the triggers are a second line).
grant select, insert on
  app.ledger_entries, app.stock_movements, app.order_events, app.reservation_events,
  app.attendance_events, app.audit_events, app.customer_consents
  to app_backend;

-- Stock levels are read-only: they change only through stock_movements (FR4.1).
grant select on app.outlet_stock to app_backend;
alter function app.apply_stock_movement() security definer;
alter function app.apply_stock_movement() set search_path = '';

-- Defaults for a new outlet are written by the trigger with definer rights too.
alter function app.outlet_defaults() security definer;
alter function app.outlet_defaults() set search_path = '';
