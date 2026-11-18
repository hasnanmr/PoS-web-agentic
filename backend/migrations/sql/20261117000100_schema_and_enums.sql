-- T-004: schema, extensions, and enums.
-- Enum values follow docs/domain/domain-glossary-and-rules.md (T-001).
-- All operational tables live in schema `app`, which is not exposed to the
-- Supabase Data API (Appendix B.4). Grants and RLS are added in T-005/T-113.

create schema if not exists extensions;
create extension if not exists btree_gist with schema extensions;

create schema if not exists app;
comment on schema app is 'Deterministic core. Not exposed to the Supabase Data API.';

create type app.tenant_type            as enum ('restaurant', 'cafe');
create type app.user_role              as enum ('owner', 'staff');
create type app.payment_mode           as enum ('pay_first', 'open_bill');
create type app.order_channel          as enum ('whatsapp_online', 'whatsapp_table', 'counter');
create type app.order_type             as enum ('delivery', 'pickup', 'dine_in', 'takeaway');
create type app.order_status           as enum ('pending_payment', 'confirmed', 'preparing', 'ready',
                                                'out_for_delivery', 'served', 'completed', 'cancelled');
create type app.payment_status         as enum ('unpaid', 'proof_submitted', 'paid', 'refunded');
create type app.payment_method         as enum ('cash', 'qris');
create type app.payment_proof_status   as enum ('pending', 'accepted', 'rejected');
create type app.bill_status            as enum ('open', 'closed', 'voided');
create type app.cashier_shift_status   as enum ('open', 'closed');
create type app.stock_unit             as enum ('g', 'ml', 'pcs');
create type app.stock_movement_type    as enum ('sale', 'sale_reversal', 'restock', 'waste', 'adjustment');
create type app.ledger_entry_type      as enum ('revenue', 'pb1', 'delivery_fee', 'refund', 'expense',
                                                'cash_shortage', 'cash_surplus', 'reversal');
create type app.addon_selection        as enum ('single', 'multiple');
create type app.reservation_status     as enum ('booked', 'seated', 'completed', 'cancelled', 'no_show');
create type app.reservation_source     as enum ('whatsapp', 'phone', 'in_person', 'walk_in');
create type app.consent_status         as enum ('granted', 'declined', 'withdrawn');
create type app.message_direction      as enum ('inbound', 'outbound');
create type app.scheduled_job_type     as enum ('unpaid_timeout', 'reservation_reminder', 'no_show_release',
                                                'anonymize_declined', 'attendance_flag', 'attendance_photo_purge');
create type app.scheduled_job_status   as enum ('pending', 'enqueued', 'done', 'cancelled', 'failed');
create type app.actor_type             as enum ('user', 'system', 'agent', 'device');
create type app.attendance_record_status as enum ('open', 'closed', 'needs_correction', 'corrected');
create type app.attendance_event_type  as enum ('clock_in', 'clock_out', 'flag', 'correction');

-- Shared trigger to maintain updated_at on mutable tables.
create function app.touch_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end $$;

-- Shared trigger that makes a table append-only (FR3.1, FR4.2, NFR3).
create function app.reject_update_delete() returns trigger
language plpgsql as $$
begin
  raise exception 'table %.% is append-only; add a new entry instead', tg_table_schema, tg_table_name
    using errcode = 'restrict_violation';
end $$;
