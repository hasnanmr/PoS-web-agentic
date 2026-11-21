-- Automatic table occupancy (FR9.11, PRD v0.22, T-149).
--
-- A table is occupied while it has an open dine-in order (table QR or counter) or an open bill.
-- That state is derived from orders and bills, not stored; only the staff override
-- "Kosongkan meja" is stored here: orders and bills whose latest activity is not after
-- `occupancy_released_at` no longer occupy the table.

alter table app.tables
  add column occupancy_released_at timestamptz,
  add column occupancy_released_by uuid references app.users (id);

-- The occupancy check reads the open dine-in orders of a table.
create index orders_open_dine_in_by_table on app.orders (table_id, created_at)
  where type = 'dine_in' and status not in ('completed', 'cancelled');
