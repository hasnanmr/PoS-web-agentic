-- T-125: `transfer` for supplier payments (bank transfer). Its own revision, because a new enum
-- value cannot be used in the transaction that adds it; the PO schema follows in the next one.
alter type app.payment_method add value if not exists 'transfer';
