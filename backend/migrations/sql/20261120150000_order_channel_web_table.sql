-- T-133 (#44): channel `web_table` for orders placed on the customer table web page (Q3).
-- Its own revision, because a new enum value cannot be used in the transaction that adds it;
-- the table QR schema follows in the next one.
alter type app.order_channel add value if not exists 'web_table';
