-- RLS, privilege, and token-hook tests (T-005, T-113, Appendix B.9).
-- Run as a superuser/owner on a migrated test database:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/tests/rls.sql
-- Fixtures are inserted as the owner (exempt from RLS); checks run as app_backend.

\o /dev/null

-- Pooled connections must not leak one request's tenant into the next (B.9).
begin;
select set_config('app.tenant_id', '00000000-0000-0000-0000-00000000000a', true);
commit;
do $$ begin
  if current_setting('app.tenant_id', true) <> '' then
    raise exception 'FAIL - transaction-local tenant setting leaked after commit';
  end if;
  raise notice 'ok   - tenant setting does not survive the transaction';
end $$;

begin;

create function pg_temp.check(cond boolean, label text) returns void
language plpgsql as $$
begin
  if not coalesce(cond, false) then raise exception 'FAIL - %', label; end if;
  raise notice 'ok   - %', label;
end $$;

create function pg_temp.expect_error(stmt text, label text) returns void
language plpgsql as $$
begin
  begin
    execute stmt;
  exception when others then
    raise notice 'ok   - % (rejected: %)', label, sqlerrm;
    return;
  end;
  raise exception 'FAIL - % was accepted', label;
end $$;

-- Switch request context the way the backend does (B.4).
create function pg_temp.as_user(p_tenant uuid, p_user uuid) returns void
language sql as $$
  select set_config('app.tenant_id', coalesce(p_tenant::text, ''), true),
         set_config('app.user_id', coalesce(p_user::text, ''), true),
         set_config('app.actor', 'user', true),
         set_config('app.device_outlet_id', '', true),
         set_config('app.device_id', '', true);
$$;
create function pg_temp.as_device(p_tenant uuid, p_outlet uuid) returns void
language sql as $$
  select set_config('app.tenant_id', p_tenant::text, true),
         set_config('app.user_id', '', true),
         set_config('app.actor', 'device', true),
         set_config('app.device_outlet_id', p_outlet::text, true),
         set_config('app.device_id', '', true);
$$;
grant execute on all functions in schema pg_temp to app_backend;

-- Fixtures (owner) ---------------------------------------------------------------
-- Tenant A: outlets A1, A2; owner Olga; staff Rina (A1 only); staff Dodi (inactive, A1).
-- Tenant B: outlet B1; owner Budi.
insert into auth.users (id, email) values
  ('00000000-0000-0000-0000-0000000000f0', 'olga@a.test'),
  ('00000000-0000-0000-0000-0000000000f1', 'rina@a.test'),
  ('00000000-0000-0000-0000-0000000000f2', 'dodi@a.test'),
  ('00000000-0000-0000-0000-0000000000f9', 'budi@b.test'),
  ('00000000-0000-0000-0000-0000000000e0', 'newowner@c.test'),
  ('00000000-0000-0000-0000-0000000000e1', 'stranger@x.test');
insert into app.tenants (id, name, type) values
  ('00000000-0000-0000-0000-00000000000a', 'Tenant A', 'cafe'),
  ('00000000-0000-0000-0000-00000000000b', 'Tenant B', 'restaurant');
insert into app.outlets (id, tenant_id, name, order_prefix, whatsapp_phone_number_id) values
  ('00000000-0000-0000-0000-0000000000a1', '00000000-0000-0000-0000-00000000000a', 'A1', 'A', 'pnid-a1'),
  ('00000000-0000-0000-0000-0000000000a2', '00000000-0000-0000-0000-00000000000a', 'A2', 'K', 'pnid-a2'),
  ('00000000-0000-0000-0000-0000000000b1', '00000000-0000-0000-0000-00000000000b', 'B1', 'A', 'pnid-b1');
insert into app.users (id, tenant_id, email, display_name, role, is_active) values
  ('00000000-0000-0000-0000-0000000000f0', '00000000-0000-0000-0000-00000000000a', 'olga@a.test', 'Olga', 'owner', true),
  ('00000000-0000-0000-0000-0000000000f1', '00000000-0000-0000-0000-00000000000a', 'rina@a.test', 'Rina', 'staff', true),
  ('00000000-0000-0000-0000-0000000000f2', '00000000-0000-0000-0000-00000000000a', 'dodi@a.test', 'Dodi', 'staff', false),
  ('00000000-0000-0000-0000-0000000000f9', '00000000-0000-0000-0000-00000000000b', 'budi@b.test', 'Budi', 'owner', true);
insert into app.staff_outlets (user_id, outlet_id, tenant_id) values
  ('00000000-0000-0000-0000-0000000000f1', '00000000-0000-0000-0000-0000000000a1', '00000000-0000-0000-0000-00000000000a'),
  ('00000000-0000-0000-0000-0000000000f2', '00000000-0000-0000-0000-0000000000a1', '00000000-0000-0000-0000-00000000000a');
insert into app.orders (id, tenant_id, outlet_id, order_no, channel, type, payment_mode, status, subtotal, total, created_by_actor) values
  ('00000000-0000-0000-0000-000000000101', '00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-0000000000a1', 1, 'counter', 'takeaway', 'pay_first', 'confirmed', 1000, 1000, 'system'),
  ('00000000-0000-0000-0000-000000000102', '00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-0000000000a2', 1, 'counter', 'takeaway', 'pay_first', 'confirmed', 1000, 1000, 'system'),
  ('00000000-0000-0000-0000-000000000103', '00000000-0000-0000-0000-00000000000b', '00000000-0000-0000-0000-0000000000b1', 1, 'counter', 'takeaway', 'pay_first', 'confirmed', 1000, 1000, 'system');
insert into app.stock_items (id, tenant_id, name, unit) values
  ('00000000-0000-0000-0000-0000000000d1', '00000000-0000-0000-0000-00000000000a', 'Susu UHT', 'ml');
insert into app.ledger_entries (tenant_id, outlet_id, type, amount, payment_method, business_date, actor_type) values
  ('00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-0000000000a1', 'revenue', 1000, 'cash', '2026-11-17', 'system');
insert into app.attendance_devices (id, tenant_id, outlet_id, name, paired_by) values
  ('00000000-0000-0000-0000-000000000201', '00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-0000000000a1', 'Tablet A1', '00000000-0000-0000-0000-0000000000f0');
insert into app.audit_events (tenant_id, actor_type, actor_id, action, entity_type) values
  ('00000000-0000-0000-0000-00000000000a', 'user', '00000000-0000-0000-0000-0000000000f0', 'outlet.updated', 'outlet');
select app.record_owner_invitation('NewOwner@c.test', '00000000-0000-0000-0000-0000000000e0', 'platform-admin@sme-pos', 'pilot cafe');

-- Role hardening --------------------------------------------------------------------
select pg_temp.check(
  (select not rolsuper and not rolbypassrls from pg_roles where rolname = 'app_backend'),
  'app_backend is not superuser and has no BYPASSRLS');
select pg_temp.check(
  not exists (select 1 from pg_tables where schemaname = 'app' and tableowner = 'app_backend'),
  'app_backend owns no table in schema app');
select pg_temp.check(
  not exists (select 1 from pg_tables t join pg_class c on c.relname = t.tablename
              join pg_namespace n on n.oid = c.relnamespace and n.nspname = 'app'
              where t.schemaname = 'app' and not c.relrowsecurity),
  'every table in schema app has RLS enabled');
select pg_temp.check(
  not has_schema_privilege('anon', 'app', 'usage') and not has_schema_privilege('authenticated', 'app', 'usage'),
  'Data API roles (anon, authenticated) have no access to schema app');

-- Token hook (B.2) --------------------------------------------------------------------
select pg_temp.check(
  (select r->'claims'->>'tenant_id' = '00000000-0000-0000-0000-00000000000a' and r->'claims'->>'app_role' = 'staff'
     from app.custom_access_token_hook('{"user_id":"00000000-0000-0000-0000-0000000000f1","claims":{"sub":"x","role":"authenticated"}}') r),
  'hook adds tenant_id and app_role for an active user');
select pg_temp.check(
  (select r->'claims'->>'role' = 'authenticated'
     from app.custom_access_token_hook('{"user_id":"00000000-0000-0000-0000-0000000000f1","claims":{"sub":"x","role":"authenticated"}}') r),
  'hook keeps the reserved role claim untouched');
select pg_temp.check(
  (select r->'error'->>'message' = 'account_inactive'
     from app.custom_access_token_hook('{"user_id":"00000000-0000-0000-0000-0000000000f2","claims":{}}') r),
  'hook refuses a deactivated user (US-003)');
select pg_temp.check(
  (select r->'claims'->>'app_role' = 'owner_pending' and not (r->'claims' ? 'tenant_id')
     from app.custom_access_token_hook('{"user_id":"00000000-0000-0000-0000-0000000000e0","claims":{}}') r),
  'hook gives an invited owner app_role owner_pending without tenant');
select pg_temp.check(
  (select r->'error'->>'message' = 'account_not_invited'
     from app.custom_access_token_hook('{"user_id":"00000000-0000-0000-0000-0000000000e1","claims":{}}') r),
  'hook refuses a user who was never invited (no public sign-up)');

-- RLS as app_backend --------------------------------------------------------------------
set local role app_backend;

select pg_temp.as_user(null, null);
select pg_temp.check((select count(*) = 0 from app.orders), 'no tenant set: orders return no rows');
select pg_temp.check((select count(*) = 0 from app.outlets), 'no tenant set: outlets return no rows');

select pg_temp.as_user('00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-0000000000f0');
select pg_temp.check((select count(*) = 2 from app.outlets), 'owner A sees both A outlets');
select pg_temp.check((select count(*) = 2 from app.orders), 'owner A sees orders of A1 and A2, query without tenant filter');
select pg_temp.check((select count(*) = 0 from app.orders where tenant_id = '00000000-0000-0000-0000-00000000000b'),
  'owner A gets no tenant B orders even when asking for them (ACN2)');
select pg_temp.check((select count(*) = 1 from app.audit_events), 'owner reads own tenant audit log, not platform events');

select pg_temp.as_user('00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-0000000000f1');
select pg_temp.check((select count(*) = 1 from app.outlets), 'staff Rina sees only her assigned outlet');
select pg_temp.check((select array_agg(outlet_id)::text = '{00000000-0000-0000-0000-0000000000a1}' from app.orders),
  'staff Rina sees only A1 orders (AC1.5)');
select pg_temp.check((select count(*) = 1 from app.staff_outlets), 'staff sees only their own outlet assignments');
select pg_temp.check((select count(*) = 0 from app.audit_events), 'staff cannot read the audit log');
select pg_temp.expect_error(
  $$insert into app.orders (tenant_id, outlet_id, order_no, channel, type, payment_mode, status, subtotal, total, created_by_actor, created_by_id)
    values ('00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-0000000000a2', 9, 'counter', 'takeaway',
            'pay_first', 'confirmed', 1000, 1000, 'user', '00000000-0000-0000-0000-0000000000f1')$$,
  'staff creating an order at an unassigned outlet');
update app.orders set status = 'preparing' where id = '00000000-0000-0000-0000-000000000102';
reset role;
select pg_temp.check((select status = 'confirmed' from app.orders where id = '00000000-0000-0000-0000-000000000102'),
  'staff update of an unassigned outlet''s order changes nothing');
set local role app_backend;
select pg_temp.expect_error($$update app.outlets set pb1_enabled = false$$, 'staff editing outlet settings');

insert into app.stock_movements (tenant_id, outlet_id, stock_item_id, type, quantity, actor_type, actor_id)
values ('00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-0000000000a1',
        '00000000-0000-0000-0000-0000000000d1', 'restock', 500, 'user', '00000000-0000-0000-0000-0000000000f1');
select pg_temp.check((select on_hand = 500 from app.outlet_stock), 'restock by staff updates stock through the trigger');
select pg_temp.expect_error($$update app.outlet_stock set on_hand = 9999$$, 'editing the stock level directly (AC4.1)');
-- Waste (outgoing) movement succeeds with enough stock and is rejected below zero.
insert into app.stock_movements (tenant_id, outlet_id, stock_item_id, type, quantity, actor_type, actor_id)
values ('00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-0000000000a1',
        '00000000-0000-0000-0000-0000000000d1', 'waste', -100, 'user', '00000000-0000-0000-0000-0000000000f1');
select pg_temp.check((select on_hand = 400 from app.outlet_stock), 'waste by staff reduces stock through the trigger');
select pg_temp.expect_error(
  $$insert into app.stock_movements (tenant_id, outlet_id, stock_item_id, type, quantity, actor_type, actor_id)
    values ('00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-0000000000a1',
            '00000000-0000-0000-0000-0000000000d1', 'waste', -9999, 'user', '00000000-0000-0000-0000-0000000000f1')$$,
  'a movement that would take stock below zero');
-- Thresholds go through a definer function: owner of the outlet's tenant only.
select pg_temp.expect_error(
  $$select app.set_stock_threshold('00000000-0000-0000-0000-0000000000a1', '00000000-0000-0000-0000-0000000000d1', 50)$$,
  'staff setting a stock threshold');
select pg_temp.expect_error($$update app.ledger_entries set amount = 1$$, 'updating a ledger entry as app_backend (AC3.1)');
select pg_temp.expect_error($$delete from app.stock_movements$$, 'deleting stock movements as app_backend');

select pg_temp.as_user('00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-0000000000f0');
select app.set_stock_threshold('00000000-0000-0000-0000-0000000000a1', '00000000-0000-0000-0000-0000000000d1', 50);
select pg_temp.check((select low_threshold = 50 from app.outlet_stock), 'owner sets a stock threshold');
select pg_temp.expect_error(
  $$select app.set_stock_threshold('00000000-0000-0000-0000-0000000000a1', '00000000-0000-0000-0000-0000000000ff', 50)$$,
  'threshold for an unknown stock item');

select pg_temp.as_user('00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-0000000000f2');
select pg_temp.check((select count(*) = 0 from app.orders), 'deactivated staff sees nothing, even with a valid tenant');

select pg_temp.as_device('00000000-0000-0000-0000-00000000000a', '00000000-0000-0000-0000-0000000000a1');
select pg_temp.check((select count(*) = 1 from app.outlets), 'attendance tablet sees only its outlet');
select pg_temp.check((select count(*) = 0 from app.orders), 'attendance tablet cannot read its outlet''s orders (T-121)');
select pg_temp.check((select count(*) = 0 from app.users), 'attendance tablet cannot read users');
select pg_temp.check((select count(*) = 0 from app.attendance_devices), 'attendance tablet cannot read the device list');
select pg_temp.check(
  (select count(*) = 0 from pg_class c join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'app' and c.relkind = 'r' and c.relrowsecurity
      and c.relname not in ('outlets', 'attendance_records', 'attendance_events', 'attendance_selfies')
      and not exists (select 1 from pg_policy p where p.polrelid = c.oid and p.polname = 'no_device')),
  'every other RLS table refuses the device actor (add policy no_device to new tables)');

select pg_temp.as_user('00000000-0000-0000-0000-00000000000b', '00000000-0000-0000-0000-0000000000f9');
select pg_temp.check((select count(*) = 1 from app.orders), 'owner B sees only tenant B');
select pg_temp.expect_error(
  $$select app.set_stock_threshold('00000000-0000-0000-0000-0000000000a1', '00000000-0000-0000-0000-0000000000d1', 50)$$,
  'owner B setting a threshold for tenant A''s outlet');
select pg_temp.expect_error($$select * from app.owner_invitations$$, 'reading owner invitations directly (definer functions only)');

select pg_temp.as_user(null, null);
select pg_temp.check(
  (select outlet_id = '00000000-0000-0000-0000-0000000000a2' from app.resolve_outlet_by_phone_number_id('pnid-a2')),
  'webhook resolver finds the outlet by phone number id without a tenant');

reset role;
select pg_temp.check(true, 'all RLS tests passed');
rollback;
