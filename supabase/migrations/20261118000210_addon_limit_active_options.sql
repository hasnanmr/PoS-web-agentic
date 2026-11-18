-- PR #7 review fixes.
--
-- 1) The 10-option limit counted every option row, including deactivated ones. Removed
--    options are only deactivated (orders may reference them), so a group that once had
--    10 options could never take another. Count active options, and enforce the limit
--    when an option is reactivated too.
create or replace function app.enforce_addon_option_limit() returns trigger
language plpgsql as $$
begin
  if not new.is_active then
    return new;
  end if;
  perform 1 from app.addon_groups where id = new.group_id for update;
  if (select count(*) from app.addon_options
      where group_id = new.group_id and is_active and id <> new.id) >= 10 then
    raise exception 'an add-on group can have at most 10 options' using errcode = 'check_violation';
  end if;
  return new;
end $$;

drop trigger addon_option_limit on app.addon_options;
create trigger addon_option_limit before insert or update of is_active on app.addon_options
  for each row execute function app.enforce_addon_option_limit();

-- 2) Two concurrent first movements for the same item and outlet both saw "no row" and
--    one failed with a unique violation. Fall back to an upsert that adds to the row.
create or replace function app.apply_stock_movement() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  update app.outlet_stock set on_hand = on_hand + new.quantity, updated_at = now()
  where outlet_id = new.outlet_id and stock_item_id = new.stock_item_id;
  if not found then
    insert into app.outlet_stock (outlet_id, stock_item_id, tenant_id, on_hand)
    values (new.outlet_id, new.stock_item_id, new.tenant_id, new.quantity)
    on conflict (outlet_id, stock_item_id)
    do update set on_hand = app.outlet_stock.on_hand + excluded.on_hand, updated_at = now();
  end if;
  return new;   -- the on_hand >= 0 check rejects movements that would go negative
end $$;
