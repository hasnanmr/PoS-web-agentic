-- Table QR takeaway (C8 "🛍 Bawa pulang").
--
-- A web chat order from a table QR may now be takeaway. It keeps its table (so staff know who
-- ordered) and stays pay-first with no bill. Occupancy is unchanged: it counts dine-in only, so
-- a takeaway does not occupy the table.

alter table app.orders drop constraint channel_type;
alter table app.orders add constraint channel_type check (
  (channel = 'whatsapp_online' and type in ('delivery', 'pickup') and payment_mode = 'pay_first') or
  (channel = 'whatsapp_table'  and type = 'dine_in' and table_id is not null) or
  (channel = 'web_table'       and type in ('dine_in', 'takeaway') and table_id is not null
                               and payment_mode = 'pay_first' and bill_id is null) or
  (channel = 'web_online'      and type in ('delivery', 'pickup') and table_id is null
                               and payment_mode = 'pay_first' and bill_id is null) or
  (channel = 'counter'         and type in ('dine_in', 'takeaway')));
