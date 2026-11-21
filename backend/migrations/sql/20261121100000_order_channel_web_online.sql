-- T-140 (PRD v0.20): the web chat channel for orders from the outlet link (`/o/<slug>`), and the
-- web chat as a booking source. Their own revision, because a new enum value cannot be used in
-- the transaction that adds it; the web chat schema follows in the next one.
alter type app.order_channel add value if not exists 'web_online';
alter type app.reservation_source add value if not exists 'web_chat';
