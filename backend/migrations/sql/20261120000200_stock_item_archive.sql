-- Owner can archive (delete) an ingredient that was mistyped or is no longer used. The row stays
-- (stock movements, PO lines and audit refer to it), so the name must only be unique among
-- active ingredients; otherwise a wrongly typed name could never be re-entered correctly.
alter table app.stock_items drop constraint stock_items_tenant_id_name_key;
create unique index stock_items_active_name on app.stock_items (tenant_id, name) where is_active;
