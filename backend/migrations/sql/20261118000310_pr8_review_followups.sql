-- PR #8 review follow-ups.
--
-- Idempotency keys now bind to the request: a fingerprint of the body and the user who
-- sent it. A key reused with a different body or by another user is rejected instead of
-- silently replaying the first response. Rows from before this migration have no
-- fingerprint and replay as before. app_backend may delete rows (tenant-scoped by the
-- existing policy) so a scheduled job can purge keys older than 24 hours.
alter table app.idempotency_keys add column request_hash text, add column actor_id uuid;
grant delete on app.idempotency_keys to app_backend;
create index idempotency_keys_created_at on app.idempotency_keys (created_at);

-- A refund carries the PB1 it gives back, so "PB1 collected minus refunded PB1" can be
-- reported. The refund row stays one negative amount (revenue + PB1); pb1_portion is the
-- positive PB1 part of it. Zero for every other entry type.
alter table app.ledger_entries
  add column pb1_portion bigint not null default 0 check (pb1_portion >= 0);
