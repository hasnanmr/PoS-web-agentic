-- T-004: defaults for every new outlet.
-- FR11.7 / AC11.10: a new outlet has one cash drawer, so a single-counter outlet needs no setup.
-- Reservation settings row exists from the start (reservations disabled by default).

create function app.outlet_defaults() returns trigger
language plpgsql as $$
begin
  insert into app.cash_drawers (tenant_id, outlet_id, name) values (new.tenant_id, new.id, 'Kasir 1');
  insert into app.reservation_settings (outlet_id, tenant_id) values (new.id, new.tenant_id);
  return new;
end $$;

create trigger outlet_defaults after insert on app.outlets
  for each row execute function app.outlet_defaults();
