-- Wave 4: QRIS proof review (S4), blind-count shift close (S8), expenses and reports (O9, O10).

-- S4: "Saya sudah menemukan transaksi ini di akun merchant QRIS" is a required step before
-- "Tandai paid". The time it was confirmed is stored with the review (T-037).
alter table app.payment_proofs add column merchant_checked_at timestamptz;
alter table app.payment_proofs add constraint accepted_after_merchant_check
  check (status <> 'accepted' or merchant_checked_at is not null);
-- The S4 queue reads pending proofs per outlet in arrival order.
create index payment_proofs_pending on app.payment_proofs (outlet_id, received_at)
  where status = 'pending';

-- O9: an entry is corrected by at most one reversal entry (append-only, never edited).
create unique index ledger_entries_one_reversal on app.ledger_entries (reverses_entry_id)
  where reverses_entry_id is not null;
-- O9 recent expenses list (newest business date first).
create index ledger_entries_expenses on app.ledger_entries (tenant_id, business_date desc, id desc)
  where type = 'expense';

-- Expenses and their reversals are owner-only (FR1.5). The API checks the role; this
-- restrictive policy makes the database refuse them from a staff session as well.
create policy owner_only_entries on app.ledger_entries as restrictive for insert to app_backend
  with check (type not in ('expense', 'reversal') or app.is_owner() or app.current_actor() = 'system');

-- O10: closed shifts per outlet and date.
create index cashier_shifts_report on app.cashier_shifts (outlet_id, opened_at desc)
  where status = 'closed';
