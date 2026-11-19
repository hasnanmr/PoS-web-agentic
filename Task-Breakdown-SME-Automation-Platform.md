# Task Breakdown — SME Business Automation Platform

This backlog breaks down the 61 user stories in [User-Stories-SME-Automation-Platform.md](User-Stories-SME-Automation-Platform.md) into implementation tasks. Each task is intended to become an issue in Jira, Linear, or a similar tracker.

## Delivery assumptions

- MVP consists of Phase 0–1. The only AI feature in the MVP is AI-assisted recommendations (T-115), which fall back to rule-based recommendations, so every MVP flow still works with the agent switched off.
- The deterministic core owns orders, payments, stock, ledger, bills, and reservations.
- Phase 2 agent features can only call validated application tools; they cannot write directly to stock or ledger tables.
- Tasks in the same wave can run in parallel after their dependencies are complete.
- `P0` is required for the relevant release; `P1` is important follow-up work; `P2` is expansion.
- Task IDs are stable. Tasks added after the first version use T-100 and up, and some tasks moved to a different wave; IDs were not renumbered so existing tracker issues keep their keys.
- Hosting: Supabase provides Auth, PostgreSQL, and Storage; Railway runs the FastAPI app, the WhatsApp worker, and RabbitMQ. The demo runs on Supabase Free and Railway Hobby with dummy data only. A pilot with real merchants needs Supabase Pro, a RabbitMQ volume, and the region decision from T-108.
- Scope decision (2026-11-18): the WhatsApp infrastructure tasks (T-045–T-049, T-100) and the recommendation tasks (T-073–T-074, T-115) are scheduled for the **Pilot** stage, not the MVP. They stay in their waves and keep their IDs and priorities; they are delivered after the POS-core demo, because they depend on the Meta account, business verification, and per-outlet WhatsApp numbers. The MVP release gates below still describe the full scope and need a decision before they are changed.
- RabbitMQ is used in every environment, including the demo. Fixed-delay retries use TTL + dead-letter queues; business timers (unpaid timeout, reminders, no-show, anonymization) use the database-backed `scheduled_jobs` table. The full topology is in Appendix A.

## Wave 0 — Product and technical foundation

| ID | Task | User stories | Depends on | Priority |
|---|---|---|---|---|
| T-001 | Confirm domain glossary, business rules, status enums, payment modes, channel enums, and timezone behavior. | US-001–US-048 | — | P0 |
| T-002 | Define API boundaries between the deterministic core, WhatsApp workers, admin app, and future agent layer. | US-014, US-036, US-042 | T-001 | P0 |
| T-003 | Bootstrap FastAPI service, React + TypeScript admin app, shared configuration, environment validation, and local development setup. | US-033–US-035 | — | P0 |
| T-004 | Create PostgreSQL migrations for tenants, outlets, users, outlet assignments, products, add-ons, prices, ingredients, recipes, orders, bills, payments, shifts, ledger, tables, reservations, customers, messages, and audit events. | US-001–US-041 | T-001 | P0 |
| T-005 | Add `tenant_id` and `outlet_id` to all operational records and create PostgreSQL row-level security policies that read the tenant and user from per-request session settings set after token verification (T-113) and check outlet access against `staff_outlets` live (Appendix B). | US-002, US-003, US-038 | T-004, T-113 | P0 |
| T-006 | Integrate Supabase Auth: JWT verification in FastAPI using Supabase asymmetric signing keys (public keys from JWKS and cached, short access-token expiry, shared-secret HS256 tokens rejected), owner/staff roles from the claim contract in T-113, invite-only account creation (public sign-up disabled in Supabase Auth; the owner invites staff by email), session invalidation on deactivation (ban + sign-out through the Supabase admin API), and outlet-scope authorization. No custom password storage. | US-003, US-033, US-038 | T-004, T-079, T-113 | P0 |
| T-007 | Build shared money, tax, rounding, inventory-unit, and local-timezone utilities. | US-011, US-012, US-019, US-022 | T-001, T-004 | P0 |
| T-008 | Create a standard actor/audit context for named users, system jobs, and `agent`, including timestamp and reason fields. | US-004, US-006, US-016, US-030 | T-004, T-006 | P0 |
| T-009 | Add CI checks, migration checks, unit-test framework, API contract checks, and seed data for local development. | All | T-003, T-004 | P0 |
| T-079 | Provision a Supabase project per environment (PostgreSQL, Auth, private Storage buckets for menu photos, QRIS images, and payment screenshots), backups, and access policies. Region follows the T-108 decision. | US-039, US-049 | T-003, T-108 | P0 |
| T-104 | Build scheduled job infrastructure: a `scheduled_jobs` table (source of truth with `run_at`, status, idempotency key, cancellation) and a poller that publishes due jobs to RabbitMQ `jobs.due.q`, with at-least-once delivery, idempotent handlers that re-check current state, and late-job handling. Used for unpaid-order timeout, reservation reminders, no-show release, and anonymization. Fixed-delay retries use the TTL queues from T-110, not this table. | US-021, US-025, US-027, US-041, US-051 | T-003, T-004, T-110, T-111 | P0 |
| T-105 | Set up Railway environments (demo, staging, production), container builds, GitHub-triggered deploys with a pre-deploy migration step and rollback, and secret management. Staging region follows the T-108 decision. | US-038, US-039, US-049 | T-003, T-009, T-079, T-109 | P0 |
| T-106 | Draft the customer privacy notice (PDP Law) with legal review and publish it at a stable URL per tenant. | US-040 | T-001 | P0 |
| T-108 | Decide how to meet the Indonesia data-residency requirement (US-039, NFR1). Checked on 2026-11-18 against the providers' region pages: neither Supabase nor Railway lists an Indonesia region; the nearest for both is Singapore (`ap-southeast-1` on Supabase, `asia-southeast1` on Railway). Demo: use Singapore with dummy data only. Pilot with real data: auth and the database stay on Supabase (Singapore), so obtain a legally reviewed cross-border transfer basis under the PDP Law, record the decision, and reflect it in the privacy notice (T-106) and consent text (T-076). | US-039, US-049 | T-001 | P0 |
| T-109 | Create the Railway project and service topology: `app` (FastAPI API and WhatsApp worker as separate processes; split into two services for the pilot) and `rabbitmq` (single node, memory watermark set, volume optional in the demo and required in the pilot), private networking, health checks, and environment variables. Host the admin app on Cloudflare Pages or Vercel. | US-049 | T-003, T-108 | P0 |
| T-110 | Declare the RabbitMQ topology as code (exchanges, queues, bindings, TTL and dead-letter arguments, policies) per Appendix A, with idempotent declaration at startup and a topology test. | US-050, US-036 | T-003, T-109 | P0 |
| T-111 | Build the shared consumer framework: manual ack after DB commit, publisher confirms, prefetch, attempt counter, retryable/permanent error classification, tiered retry routing, dead-letter routing with failure reason, and correlation ID propagation. | US-050, US-037 | T-110 | P0 |
| T-112 | Build dead-letter visibility and replay: list, inspect, and requeue or discard dead-lettered messages (CLI or protected admin endpoint), with an audit record for each action. | US-050 | T-006, T-008, T-111 | P0 |
| T-113 | Define the JWT claim contract (`tenant_id` and `app_role`; outlet access and active status are checked live in the database), enable Supabase asymmetric JWT signing keys, implement the custom access token hook, and define the backend DB session pattern: transaction pooler connection, per-request session settings (`set_config(..., true)`) filled from the verified token, a system context for workers, and a non-bypass database role in a schema hidden from the Data API (details in Appendix B). The service role is never used for tenant data. | US-003, US-038 | T-004, T-079 | P0 |
| T-114 | Demo operations: keep-alive to prevent Supabase Free auto-pause, Railway usage alerts and spend limit, demo-data seed and reset, and a promotion checklist from demo to pilot (Supabase Pro and backups, RabbitMQ volume, split API and worker, region decision). | US-049 | T-105, T-109 | P1 |

## Wave 1 — Tenant, outlet, staff, and configuration

| ID | Task | User stories | Depends on | Priority |
|---|---|---|---|---|
| T-010 | Implement tenant creation with restaurant/cafe validation and owner assignment. | US-001 | T-004, T-006 | P0 |
| T-011 | Implement outlet CRUD and configuration for address, hours, timezone, WhatsApp number, delivery fee, PB1, payment mode, reservation settings, and QRIS. | US-002, US-019, US-022 | T-005, T-007 | P0 |
| T-012 | Implement owner-created staff accounts (Supabase Auth email invitation), outlet assignments, deactivation, and login/session rejection after deactivation. | US-003 | T-006, T-011 | P0 |
| T-013 | Implement permission matrix for owner and staff actions at both API and UI route levels. | US-003, US-033 | T-006, T-012 | P0 |
| T-014 | Implement secure QRIS image upload to a private Supabase Storage bucket (signed URLs), storage metadata, replacement, and outlet-level access. | US-017 | T-011, T-079 | P0 |
| T-015 | Add API and integration tests for cross-tenant and cross-outlet access attempts, including direct API requests, tokens signed with a wrong key or algorithm, and sign-up attempts without an invitation. | US-002, US-003, US-038 | T-005, T-006, T-013 | P0 |
| T-084 | Create the Meta template library and submit order-update, auto-cancellation, payment-rejected, payment-request, reservation-confirmation, and reservation-reminder templates as early as possible, since Meta's review is outside our control. Keep template names and parameters in a shared registry used by T-055. | US-015, US-021, US-025 | T-001 | P0 |

## Wave 2 — Menu, add-ons, recipes, and inventory

| ID | Task | User stories | Depends on | Priority |
|---|---|---|---|---|
| T-016 | Implement menu item CRUD with required photo, description, active/inactive state, and shared tenant-level data. | US-005 | T-004, T-006, T-079 | P0 |
| T-017 | Implement add-on groups and options with required/optional selection rules, price delta, recipe delta, and a maximum of 10 options. | US-005, US-011 | T-016, T-007 | P0 |
| T-018 | Implement outlet-specific prices for menu items and add-on options. | US-002, US-005 | T-011, T-016, T-017 | P0 |
| T-019 | Implement ingredients, units, low-stock thresholds, and menu/add-on recipes. | US-006, US-007 | T-016, T-017 | P0 |
| T-020 | Implement append-only stock movements for restock, waste, adjustment, sale, and cancellation/reversal. | US-006, US-021, US-030 | T-008, T-019 | P0 |
| T-021 | Implement transactional recipe expansion and stock deduction/return, including add-ons and row-level/concurrency protection. | US-006, US-014, US-021 | T-019, T-020 | P0 |
| T-022 | Implement stock projection, low-stock warnings, sold-out calculation, and outlet-specific availability. | US-007, US-010, US-028 | T-020, T-021 | P0 |
| T-023 | Add tests for exact recipe quantities, add-on ingredient changes, no negative stock, immutable movements, and sold-out recovery after restock. | US-005–US-007, US-014 | T-020–T-022 | P0 |
| T-024 | Seed editable sample menu, sample photos, prices, and add-ons for every new tenant/outlet. | US-008 | T-016–T-018, T-107 | P0 |
| T-107 | Prepare sample menu content: items, descriptions, recipes, add-ons, and photos with usage rights that meet Meta catalog image rules. | US-008 | T-001 | P1 |

## Wave 3 — Order and bill domain

| ID | Task | User stories | Depends on | Priority |
|---|---|---|---|---|
| T-025 | Define order, order-item, add-on, payment, bill, order-event, and status-transition models. | US-014, US-016, US-020 | T-004, T-007, T-008 | P0 |
| T-026 | Implement a single order-creation service used by WhatsApp, table QR, counter, and future agent tools. | US-014, US-034, US-042 | T-021, T-025 | P0 |
| T-027 | Implement quote calculation for subtotal, add-ons, PB1, delivery fee, pickup, and total using outlet settings. | US-011, US-012, US-019 | T-007, T-018, T-025 | P0 |
| T-028 | Implement confirmation-time stock recheck and atomic order creation; return item-level sold-out errors with replacement/remove options. | US-011, US-014 | T-021, T-026, T-027 | P0 |
| T-029 | Implement duplicate-safe order creation using message/request idempotency keys. | US-014, US-037 | T-026, T-028 | P0 |
| T-030 | Implement order and payment status machines for online, pay-first dine-in, open-bill dine-in, and takeaway orders. | US-016, US-020 | T-025, T-027 | P0 |
| T-031 | Implement status transition validation and immutable order event history with actor, timestamp, and reason where required. | US-004, US-016 | T-008, T-030 | P0 |
| T-032 | Implement cancellation and paid-order reversal workflows, including stock return versus waste behavior and refund ledger hooks. | US-004, US-021 | T-020, T-030, T-031 | P0 |
| T-033 | Implement open bills per table or guest name, one open bill per table, order attachment, running total, duration, and full-bill close. | US-020 | T-025, T-027, T-030 | P0 |
| T-035 | Add concurrency and transition tests for last-stock orders, invalid status changes, open-bill uniqueness, and mode changes preserving existing order flow. | US-014, US-016, US-020 | T-028–T-033 | P0 |

## Wave 4 — Payments, cashier shifts, ledger, and reports

| ID | Task | User stories | Depends on | Priority |
|---|---|---|---|---|
| T-037 | Implement the payment-proof model, `proof_submitted` payment status, staff payment-review queue, merchant-account confirmation step, mark-paid action, and reject-proof action (required reason, immediate cancellation with stock reversal, no ledger entry, customer notification hook); actor and time recorded on both. Customer screenshot intake from WhatsApp is in T-036. | US-017 | T-014, T-030, T-032 | P0 |
| T-038 | Implement cash payment capture, payment-method validation, amount received, change due, and online cash restriction. | US-018 | T-025, T-027 | P0 |
| T-039 | Implement owner-configured cash drawers per outlet (one created by default with each outlet), cashier shift open/close per drawer, starting cash, one active shift per drawer, and payment/refund linkage. | US-018 | T-038 | P0 |
| T-040 | Implement blind end-of-shift cash count, expected-cash calculation, difference, actor tracking, and shortage/surplus ledger entries. | US-018, US-030 | T-039 | P0 |
| T-041 | Implement append-only ledger posting for revenue, PB1, delivery fee, cash/QRIS payment, refund, expense, cash difference, and reversal. | US-019, US-030 | T-008, T-027, T-032, T-037–T-040 | P0 |
| T-042 | Implement owner-only manual expense entry with outlet, amount, description, date, and actor. | US-031 | T-006, T-041 | P0 |
| T-043 | Implement daily, weekly, monthly cashflow summaries and trends per outlet and across outlets, using outlet-local day boundaries, with cash in, cash out, and net cash compared against the previous period of the same length, expenses per outlet, and a recent-expenses list. | US-032 | T-041, T-042, T-007 | P0 |
| T-044 | Add financial integrity tests ensuring ledger values are created only at confirmed payment and cannot be edited/deleted. | US-018–US-032 | T-040–T-043 | P0 |
| T-125 | Create the purchase-order schema: `suppliers` (tenant-level), `purchase_orders` (outlet, supplier, number per outlet such as `PO-A-0012`, payment term `pay_later`/`pay_in_advance`, due date or expected delivery date, total, goods status, payment status, cancellation with reason), `purchase_order_lines` (stock item or free-text item, quantity in the item's unit, unit price), `purchase_order_receipts` and receipt lines, and `purchase_order_payments` (date, amount, method, linked ledger entry, optional cashier shift); add `transfer` to the payment method enum and a PO reference on ledger entries and stock movements; RLS (assigned staff may open and read POs and record receipts for their outlets; suppliers, payments, cancellation, and debt are owner-only), append-only receipts and payments. | US-057–US-061 | T-004, T-005, T-041 | P0 |
| T-126 | Implement the PO service and API: supplier CRUD (owner), open PO with lines (owner, or staff for an assigned outlet, no approval, creator recorded), cancel (owner; reason required; refused once paid or received), record payments for pay-later POs (instalments, never above the amount owed) and the full payment for pay-in-advance POs, each posting one `expense` ledger entry on the payment date with method, PO number, and supplier; cash payments optionally linked to an open shift so the blind count's expected cash includes them; `Idempotency-Key` on create and payment; audit events. | US-057, US-058, US-059 | T-041, T-042, T-125 | P0 |
| T-127 | Implement goods check and PO close: owner or assigned staff enter the received quantity next to each PO line (delivery date, note), lines show match or shortfall, ingredient lines create restock movements referencing the PO (base units), free-text lines add no stock; partial deliveries allowed, over-receipt refused; status `difference_found` while short; close by staff when every line matches; a short PO can't be closed by staff and only the owner can close it with a required note (pay-later amount owed becomes received × unit price); pay-in-advance POs can't close unpaid; closed POs can't reopen; staff may close only when every line matches. | US-060 | T-020, T-125 | P0 |
| T-128 | Add supplier payment reminders and PO figures: the owner dashboard **PO ada selisih** list (open POs with a shortfall, close-with-note shortcut) and **Pembayaran supplier** card (closed pay-later POs not fully paid, overdue first then by due date in the outlet time zone; open unpaid pay-in-advance POs; record-payment shortcut), supplier debt (total, overdue, due in 7 days) and goods paid for but not yet received on the dashboard and cashflow report, separate from cash out; PO payments in expenses per outlet and recent expenses with their PO number; the **Ringkasan PO** report (count and value by open/closed, goods not arrived/partly/fully arrived, payment unpaid/partly/paid, split by payment term, for outlet(s) and month by PO open date, each figure linking to the filtered PO list); all in the Dashboard tab **PO & Supplier** (PRD v0.15), where the month filter applies to Ringkasan PO only; owner-only at the API. | US-058, US-059, US-061 | T-043, T-071, T-126, T-127 | P0 |
| T-129 | Design the Pengeluaran wireframes in figcraft: tabs **Pengeluaran** and **Purchase Order** (list with filters and status badges, PO detail with lines, checks, and payments), open-PO form with payment term, the staff Purchase Order screen (list for their outlets, open PO) and the goods cross-check screen (ordered vs received per line, match/shortfall, Tutup PO), the record-payment dialog, the owner dashboard **Pembayaran supplier** card and **Ringkasan PO** report, mobile 360 px; update `design/WIREFRAME-TRACEABILITY.md` and `docs/architecture/screen-endpoint-map.md`. | US-031, US-057–US-061 | — | P0 |
| T-130 | Build the owner Dashboard tab **PO & Supplier** (O15–O17; PRD v0.15, Pengeluaran stays for direct expenses), the PO create/detail/payment/cancel flows, supplier management, the staff goods-receipt view, and the supplier debt cards, following the T-129 wireframes. | US-031, US-057–US-061 | T-072, T-126, T-127, T-128, T-129 | P0 |
| T-131 | Add PO tests: scheme 1 (open → check → close → dashboard reminder → instalments, overpayment refused, overdue by outlet time zone), scheme 2 (open → dashboard payment request → pay → check → close; close refused while unpaid), partial delivery and difference found (staff close refused, PO listed on the owner dashboard), owner close with a required note adjusting the amount owed, over-receipt refused, restock movements in base units, cash payment lowering a shift's expected cash, cancellation rules, ledger cash-basis (no entry at open, check, or close), staff opening a PO for an assigned outlet (and refused for others), and staff refused from payments, cancellation, suppliers, reminders, and debt through the API. | US-057–US-061 | T-126–T-128 | P0 |

## Wave 5 — WhatsApp integration and deterministic flows

| ID | Task | User stories | Depends on | Priority |
|---|---|---|---|---|
| T-045 | Configure Meta WhatsApp Cloud API/BSP credentials, webhook verification, signature validation, and outlet-number mapping. | US-002, US-036 | T-011 | P0 |
| T-100 | Build per-outlet WhatsApp onboarding: Meta Embedded Signup or BSP flow, business verification status, phone number registration, catalog creation and linking, and setup status shown to the owner. | US-002, US-036 | T-011, T-045 | P0 |
| T-046 | Implement inbound webhook persistence and publishing to `wa.inbound` with immediate acknowledgement; process one conversation at a time (Postgres advisory lock on conversation id). | US-036 | T-045, T-008, T-110, T-111 | P0 |
| T-047 | Implement outbound WhatsApp worker on `wa.outbound.q` and catalog sync worker on `catalog.sync.q`, using the retry tiers and error classification from T-111 (429 and 5xx retry; 4xx dead-letter; outside-24-hour-window error falls back to a template once). | US-015, US-036, US-050 | T-046, T-111 | P0 |
| T-048 | Implement processed-message store and idempotent worker behavior for webhook retries and RabbitMQ redelivery. | US-037 | T-046 | P0 |
| T-049 | Implement conversation state for main menu, active order, active reservation, and safe restart/recovery behavior. | US-009–US-011, US-023 | T-046, T-048 | P0 |
| T-050 | Implement the main menu list message (Pesan, Rekomendasi, Data Saya, plus Reservasi and Reservasi Saya when reservations are enabled) and the "menu" keyword that returns to it from any flow without creating anything. | US-009 | T-049 | P0 |
| T-051 | Implement catalog sync for item metadata, photos, outlet prices, active state, and unavailable/sold-out state. | US-008, US-010 | T-016–T-018, T-022, T-047, T-100 | P0 |
| T-052 | Implement catalog cart intake and post-cart add-on collection through reply buttons/list messages. | US-010, US-011 | T-017, T-049, T-051 | P0 |
| T-053 | Implement WhatsApp order summary, pickup/delivery selection, address capture, explicit confirmation, and order creation call. | US-011, US-012, US-014 | T-026–T-029, T-049, T-052 | P0 |
| T-054 | Implement table QR generation with outlet number, table identifier, and optional rotating token validation. | US-013 | T-011, T-045 | P0 |
| T-036 | Implement the QRIS payment request (outlet QRIS image, exact total, screenshot request) and inbound screenshot intake: download Meta media to storage, attach it to the order via T-037, and stop the unpaid timer. | US-017 | T-014, T-027, T-037, T-047, T-049 | P0 |
| T-034 | Implement configurable unpaid-order timeout, screenshot timer pause, automatic cancellation, stock reversal, and customer notification. | US-015, US-021 | T-030, T-032, T-036, T-047, T-104 | P0 |
| T-055 | Implement order confirmation, status notifications, shared notification templates, and approved-template selection outside the 24-hour window. | US-015, US-025 | T-047, T-053, T-084 | P0 |
| T-056 | Add end-to-end WhatsApp tests for online, table QR, pickup, delivery, add-ons, sold-out confirmation, duplicate messages, unpaid timeout, and template fallback. | US-009–US-015, US-037 | T-034, T-036, T-048–T-055 | P0 |

## Wave 6 — Reservations and tables

| ID | Task | User stories | Depends on | Priority |
|---|---|---|---|---|
| T-057 | Implement table CRUD, capacity, area, bookable hours, duration, booking window, party limit, reminder time, and cancellation cutoff. | US-022 | T-011, T-025 | P0 |
| T-058 | Implement timezone-aware availability calculation and smallest-fitting-table assignment. | US-022, US-023 | T-007, T-057 | P0 |
| T-059 | Add database-level exclusion/locking rule preventing overlapping reservations, including concurrent requests. | US-024 | T-057, T-058 | P0 |
| T-060 | Implement structured WhatsApp reservation flow: party size, date, available time, review, and confirmation. | US-023 | T-049, T-058, T-059 | P0 |
| T-061 | Implement reservation confirmation, reminder scheduling, and the Reservasi Saya flow (list upcoming bookings, cancel, reschedule) with cutoff enforcement. | US-025 | T-055, T-060, T-104 | P0 |
| T-062 | Implement staff reservation board with phone/in-person booking, table reassignment, seated/completed/cancelled/no-show states, and event audit. | US-026 | T-006, T-057, T-060 | P0 |
| T-063 | Implement table occupancy for walk-in guests (no reservation) and availability blocking. | US-027 | T-057, T-058, T-062 | P0 |
| T-064 | Implement 15-minute post-booking hold, automatic no-show, table release, and seated-before-deadline behavior. | US-027 | T-061, T-062, T-104 | P0 |
| T-065 | Add reservation tests for capacity limits, timezone display, double-booking, reminders, cutoff, walk-ins, reassignment, and no-show release. | US-022–US-027 | T-057–T-064 | P0 |

## Wave 7 — Admin application and recommendations

| ID | Task | User stories | Depends on | Priority |
|---|---|---|---|---|
| T-066 | Build owner onboarding, outlet settings (including cash drawers), staff management, QRIS upload, menu, add-on, recipe, and price screens. | US-001–US-006, US-017, US-019 | T-010–T-019 | P0 |
| T-067 | Build staff counter order screen with dine-in and takeaway order types, add-ons, table selection, payment, and order submission. | US-034 | T-026–T-030, T-033, T-038, T-039, T-057 | P0 |
| T-068 | Build order board with payment review, lifecycle actions, cancellation/reversal, and open-bills view. | US-016–US-021 | T-030–T-033, T-037–T-039 | P0 |
| T-069 | Build stock, stock movement, low-stock, and sold-out screens. | US-006, US-007 | T-020–T-023 | P0 |
| T-070 | Build reservation/table view and cashier shift screens. | US-018, US-026, US-027 | T-039, T-062–T-064 | P0 |
| T-071 | Build owner dashboard for outlet-level and combined sales, cashflow, PB1, payment method, and stock summaries. | US-032, US-033 | T-041–T-043 | P0 |
| T-072 | Build role-aware navigation and responsive layouts for 360 px mobile width through desktop. | US-003, US-033, US-035 | T-006, T-066–T-071 | P0 |
| T-073 | Implement owner picks and tags, outlet best-seller query for the last 30 days, sold-out filtering, de-duplication, and 30-item limit. | US-028 | T-016, T-022, T-026 | P0 |
| T-074 | Implement WhatsApp recommendation product messages and add-to-cart handoff. | US-029 | T-051, T-073, T-052 | P0 |
| T-115 | Implement AI-assisted recommendations in the Rekomendasi flow: a minimal LangChain gateway with prompt versioning; read-only tools for menu, tags, outlet availability, and 30-day sales; suggestions limited to active, available items at outlet prices with owner's picks first; selected items handed to the T-074 add-to-cart flow; an immediate acknowledgement message ("Sebentar ya, lagi cariin rekomendasi…") is sent before the AI call starts, because a reply can take up to 30 seconds; errors or a 30-second timeout fall back to the T-073 rule-based message; tool calls logged with actor `agent`; a small evaluation set covering sold-out items, price accuracy, and prompt injection. | US-052 | T-008, T-049, T-073, T-074 | P0 |
| T-101 | Build the owner audit log screen for order reversals and status changes, filterable by outlet, staff member, and date, showing order, actor, time, and reason. | US-004 | T-031, T-032, T-066 | P0 |
| T-102 | Build the owner cash count report: every shift's starting cash, expected cash, counted cash, difference, and who counted, per outlet. | US-018 | T-040, T-071 | P0 |
| T-116 | Build the attendance domain: `attendance_records` and append-only `attendance_events` (clock in, clock out, flag, correction) with outlet-local times, one open record per staff member, the tablet and the selfie stored with each clock-in and clock-out (a photo is required), RLS, and API endpoints for clock in and clock out (attendance tablet session only) and own history (staff session). | US-053 | T-005, T-006, T-007, T-008, T-011, T-012, T-121 | P0 |
| T-117 | Build the attendance tablet screens: staff list for the outlet, selfie capture with the front camera (retake, camera-denied state), clock in or out confirmation with time and duration, first-use privacy notice, and an offline message without queueing submissions (NFR7). Also build the staff's own attendance history in the admin app (read-only, with their selfies) at 360 px. | US-053 | T-072, T-116, T-121, T-122 | P0 |
| T-118 | Add the missing-clock-out check on the `scheduled_jobs` scheduler (job type `attendance_flag`, run at outlet closing time plus the owner-set grace period): flag the record "needs correction" without inventing a clock-out time, and re-check that the record is still open before acting. Add the grace-period setting to outlet settings. | US-053 | T-011, T-104, T-116 | P0 |
| T-119 | Build the owner attendance report and correction screens: filter by outlet, staff member, and date range; hours per day and in total; flagged records; clock-in and clock-out selfies for each record; correction with a required reason that keeps the original values; outlet-local day boundaries. | US-054 | T-072, T-116, T-118, T-122 | P0 |
| T-120 | Add attendance tests: one open record per staff member, clock in without a selfie, clock in for an unassigned outlet and from a staff token by direct API call, a tablet session opening other admin data, a revoked tablet, staff seeing only their own records and selfies, selfie deletion after 30 days, WIB/WITA/WIT day boundaries, flagging after worker downtime, and the correction audit trail. | US-053, US-054, US-055 | T-116–T-119, T-121, T-122 | P0 |
| T-121 | Build outlet attendance tablets: owner-generated one-time pairing code per outlet, a device account and session scoped to one outlet that can only list that outlet's staff and record attendance (enforced in the API and RLS), a device list with last activity, and revocation that rejects the tablet on its next request. Add the pairing and device list to outlet settings. | US-055 | T-006, T-011, T-113 | P0 |
| T-122 | Store attendance selfies in a private Supabase Storage bucket: upload from the tablet with size and type checks, short-lived signed URLs for the owner and the staff member only, and a scheduled `attendance_photo_purge` job that deletes photos after 30 days while keeping the records. | US-053, US-054 | T-079, T-104, T-116 | P0 |
| T-123 | Implement busyness queries for the owner: orders per hour per outlet and period (outlet-local time, opening hours only) with busy (≥ 130% of the hourly average) and quiet (≤ 60%) marking, the day-by-hour average over the last 4 weeks, current crowd per outlet (occupied tables, active orders, Ramai/Normal/Sepi status), and the hour-group filter for dashboard figures. Owner-only at the API. Include tests for time zones, thresholds, and totals. | US-056 | T-007, T-013, T-026, T-030, T-057, T-063 | P1 |
| T-124 | Build the owner dashboard busyness views (wireframe O2): hour-group filter in the header, day-by-hour busyness map, current crowd per outlet, and orders-per-hour chart with busy and quiet hours marked. | US-056 | T-071, T-123 | P1 |
| T-075 | Add frontend accessibility, responsive, permission, and critical-flow tests. | US-033–US-035 | T-066–T-074, T-101, T-102, T-117, T-119, T-124, T-130 | P0 |

## Wave 8 — Membership, compliance, and MVP hardening

| ID | Task | User stories | Depends on | Priority |
|---|---|---|---|---|
| T-076 | Implement customer/contact, consent, privacy-notice link, and business-wide membership state across outlets. | US-040 | T-004, T-045, T-049, T-106 | P0 |
| T-077 | Implement the Data Saya flow (membership status, end membership) and delete/anonymize personal data without changing orders, ledger, or stock history. | US-041 | T-076, T-041 | P0 |
| T-103 | Implement the scheduled anonymization job for customers who declined membership, run once their order is completed/cancelled or their booking is finished. | US-040, US-041 | T-076, T-077, T-104 | P0 |
| T-078 | Ensure personal data is absent from append-only ledger and stock tables; add automated privacy regression tests. | US-040, US-041 | T-077, T-103 | P0 |
| T-080 | Add security hardening: secret management, token expiry, webhook verification, upload validation, rate limiting, and audit-log protection. | US-003, US-036, US-038, US-039 | T-006, T-008, T-014, T-045 | P0 |
| T-081 | Add queue metrics (RabbitMQ management API), structured logs, correlation IDs, retry/DLQ dashboards, and alerts for dead-lettered messages, queue backlog, and failed catalog updates. | US-008, US-036, US-037, US-050 | T-047, T-048, T-112 | P0 |
| T-082 | Run performance, concurrency, tenant-isolation, backup-restore, and failure-recovery tests against MVP acceptance criteria. | US-014, US-024, US-030, US-037–US-039 | T-015, T-035, T-044, T-056, T-065, T-075, T-078, T-080, T-081, T-103, T-105, T-120, T-131 | P0 |
| T-083 | Execute full UAT with owner, cashier/waiter, and customer scenarios; triage defects and produce release checklist. | All MVP stories | T-082 | P0 |

## MVP release gates

The MVP is ready for release only when:

1. T-083 is complete and all MVP acceptance criteria pass.
2. An online WhatsApp order, table-QR order, and counter order use the same order service and produce correct stock, payment, and ledger outcomes.
3. Pay-first and open-bill outlets both work, including payment restrictions and existing-order behavior after a mode change.
4. Reservation concurrency, 15-minute no-show release, and timezone behavior pass.
5. Duplicate webhook delivery cannot create duplicate orders, stock movements, or ledger entries.
6. Cross-tenant access tests and append-only audit checks pass, and the data-residency decision from T-108 is met (Indonesia region, or a documented and approved exception) before real merchant data is stored.
7. Approved WhatsApp templates are available for every required outside-window notification, or the release is explicitly blocked with a documented Meta dependency.
8. Dead-letter queues are empty or triaged, a replay has been rehearsed (T-112), and the demo-to-pilot promotion checklist (T-114) is complete.

## Phase 2 — Agent layer

| ID | Task | User stories | Depends on | Priority |
|---|---|---|---|---|
| T-085 | Define versioned deterministic tool contracts for quote, order creation, reservation creation, menu lookup, stock lookup, sales lookup, and FAQ data. | US-042–US-045 | T-026, T-058, T-082 | P0 |
| T-086 | Extend the MVP agent gateway from T-115 with conversation memory boundaries, prompt/version management, timeout, fallback, and error handling for Phase 2 features. | US-042–US-045 | T-085, T-115 | P0 |
| T-087 | Implement free-text order parsing, structured summary, clarification questions, explicit confirmation gate, and handoff to T-026. | US-042 | T-085, T-086 | P0 |
| T-088 | Implement free-text reservation parsing, detail confirmation, availability lookup, and handoff to T-060. | US-043 | T-058–T-060, T-085, T-086 | P0 |
| T-089 | Implement FAQ handling and advisory upsell without direct cart/order mutation (conversational recommendations ship in the MVP as T-115). | US-044 | T-085, T-086 | P1 |
| T-090 | Implement demand forecast, restock suggestion, and unusual-cashflow detection views for owners. | US-045 | T-043, T-085, T-086 | P1 |
| T-091 | Enforce agent guardrails: no direct database writes, no stock-change tool, explicit customer confirmation, actor=`agent`, and tool-call audit trail. | US-042–US-045 | T-085–T-090 | P0 |
| T-092 | Build agent evaluation set for ambiguous orders, unavailable items, incorrect quantities, timezone reservations, prompt injection, and duplicate confirmations. | US-042–US-045 | T-087–T-091 | P0 |
| T-093 | Run shadow/canary rollout with deterministic fallback and monitor tool errors, confirmation rate, and unsafe-action attempts. | US-042–US-045 | T-092 | P1 |

## Phase 3 — Scale and expansion

| ID | Task | User stories | Depends on | Priority |
|---|---|---|---|---|
| T-094 | Add scheduled staff shifts and planned-versus-actual reporting against the MVP attendance records. | US-046 | T-116, T-119 | P1 |
| T-095 | Add demand-based schedule suggestions with owner approval workflow. | US-046 | T-094, T-090 | P1 |
| T-096 | Integrate dynamic QRIS/payment gateway, webhook validation, reconciliation, and idempotent payment confirmation. | US-047 | MVP payment domain, T-081 | P1 |
| T-097 | Add dropshipper tenant type, non-physical outlet behavior, and dropshipper-specific onboarding. | US-048 | T-010–T-013 | P2 |
| T-098 | Implement marketplace connector framework and Shopee integration. | US-048 | T-097 | P2 |
| T-099 | Implement Tokopedia and TikTok Shop integrations, sync monitoring, and conflict resolution. | US-048 | T-098 | P2 |

## Critical path

The shortest dependency path to a usable MVP is:

`T-001 → T-004 + T-108 → T-079 → T-113 → T-005/T-006 → T-016–T-022 → T-025–T-033 → T-037–T-041 → T-045–T-053 → T-036/T-034 → T-055 → T-066–T-072 → T-076–T-078/T-103 → T-082 → T-083`

Two external dependencies run alongside it and can block release regardless of engineering progress, so start them early:

- Meta template approval (T-084), started in Wave 1.
- Per-outlet WhatsApp number and catalog onboarding (T-100), including Meta business verification.
- The Supabase and Railway region decision (T-108), which gates any real merchant data.

The following work can proceed in parallel once the foundation is ready:

- Platform and infrastructure: T-079, T-104, T-105, T-108–T-114
- Tenant/staff administration: T-010–T-015
- Menu and inventory: T-016–T-024
- Purchase orders and supplier debt: T-125–T-131 (after the ledger, T-041; not on the order critical path)
- Admin shell and screens: T-066–T-072
- WhatsApp infrastructure: T-045–T-049, T-100 (**Pilot**, not MVP)
- Reservations: T-057–T-065 (not on the order critical path; needs T-055 and T-104 only for reminders and no-show release)
- Recommendations: T-073–T-074, T-115 (**Pilot**, not MVP)
- Legal and content: T-106, T-107

## Suggested issue labels

Use these labels when importing the backlog:

- `phase:mvp`, `phase:p2`, `phase:p3`
- `domain:platform`, `domain:auth`, `domain:menu`, `domain:inventory`, `domain:orders`, `domain:payments`, `domain:whatsapp`, `domain:reservations`, `domain:admin`, `domain:agent`
- `type:backend`, `type:frontend`, `type:worker`, `type:database`, `type:qa`, `type:devops`
- `risk:financial`, `risk:privacy`, `risk:concurrency`, `risk:external-api`

## Appendix A — Demo hosting and RabbitMQ topology

### A.1 Hosting map

| Component | Runs on | Demo | Pilot |
|---|---|---|---|
| PostgreSQL, Auth, Storage | Supabase | Free plan, dummy data | Pro plan, backups, region per T-108 |
| FastAPI API + WhatsApp worker | Railway service `app` | One service, two processes | Two services (`api`, `worker`) |
| RabbitMQ | Railway service `rabbitmq` | Single node, no volume, memory watermark ~256 MiB | Single node with volume |
| Admin app (React) | Cloudflare Pages or Vercel | Free tier | Same |
| DB connections | Supabase transaction pooler (port 6543) | Small pool per process | Same |

### A.2 Exchanges and queues

All queues are durable, messages are persistent, and everything lives in one vhost (`sme`). The delayed-message plugin is not used.

| Exchange | Queue | Producer | Consumer | Notes |
|---|---|---|---|---|
| `wa.inbound` (direct) | `wa.inbound.q` | Webhook handler (T-046) | Inbound worker | Prefetch 10. Per-conversation ordering through a Postgres advisory lock on conversation id. Max 4 attempts. |
| `wa.outbound` (direct) | `wa.outbound.q` | Order, reservation, and notification services | Outbound worker (T-047) | Prefetch 5, paced to Meta rate limits. Max 6 attempts. |
| `catalog.sync` (direct) | `catalog.sync.q` | Menu, price, and stock changes | Catalog worker (T-047) | Coalesce by outlet + item key (latest wins). Max 8 attempts. |
| `jobs` (direct) | `jobs.due.q` | Scheduler poller (T-104) | Job handlers | Handlers are idempotent and re-check current state. |
| `wa.dlx` (direct) | `wa.dead.q`, `catalog.dead.q`, `jobs.dead.q` | Consumer framework (T-111) | Replay tool (T-112) | No TTL. Kept until an admin replays or discards. |

That is 4 working queues, 3 dead-letter queues, and 3 retry queues (A.3), 10 in total.

### A.3 Retry tiers (TTL + dead-letter)

Retry delays are fixed, so queue-level TTL is safe here (no head-of-line blocking).

| Retry exchange (topic) | Queue | Queue TTL | Dead-letters to |
|---|---|---|---|
| `retry.5s` | `retry.5s.q` | 5 s | `retry.return` |
| `retry.30s` | `retry.30s.q` | 30 s | `retry.return` |
| `retry.2m` | `retry.2m.q` | 2 min | `retry.return` |

- The consumer republishes a failed message to a retry exchange using the original routing key (for example `wa.outbound`). After the TTL, RabbitMQ dead-letters it to `retry.return` (topic) with the same routing key, and `retry.return` is bound to the matching working queue.
- The app increments an `x-attempt` header on each republish. Attempt 1 uses 5 s, attempt 2 uses 30 s, attempt 3 and later use 2 min, until the queue's maximum is reached. Then the message goes to the matching dead-letter queue with `x-failure-reason`.
- **Retryable:** network timeout, HTTP 429, HTTP 5xx, DB deadlock or serialization failure, lock timeout.
- **Permanent (dead-letter immediately):** HTTP 4xx other than 429, invalid payload, unknown message type, template rejected.
- **Special case:** a Meta "outside 24-hour window" error switches to an approved template and resends once. It does not count as a plain retry.

### A.4 Scheduled jobs (not TTL)

Business timers have variable delays (the unpaid timeout is configured per outlet, and reminders and no-show depend on booking time). Per-message TTL in one queue blocks behind the oldest message, and delayed messages are lost if the broker restarts without a volume. So the source of truth is the database:

1. A job is inserted into `scheduled_jobs` (`job_key`, `type`, `run_at`, `status`, `payload`) in the same transaction as the business change, for example order creation.
2. A poller (every 15 s) selects due jobs with `FOR UPDATE SKIP LOCKED`, publishes to `jobs` with publisher confirms, and marks them `enqueued`.
3. The handler checks the current state before acting (for example the order is still unpaid and has no screenshot), then marks the job `done`. A job cancelled earlier (screenshot received, booking seated) is skipped.
4. Jobs that are overdue after downtime run immediately on the next poll.

| Job type | Created when | Runs at | Spec |
|---|---|---|---|
| `unpaid_timeout` | Pay-first order created (T-034) | Order time + outlet timeout | US-021 |
| `reservation_reminder` | Reservation confirmed (T-061) | Booking time − reminder offset | US-025 |
| `no_show_release` | Reservation confirmed (T-064) | Booking time + 15 min | US-027 |
| `anonymize_declined` | Order completed or cancelled, or booking finished (T-103) | Immediately after the end event | US-040, US-041 |
| `attendance_flag` | Staff member clocks in (T-118) | Outlet closing time + grace period | US-053 |
| `attendance_photo_purge` | Selfie stored (T-122) | Photo time + 30 days | US-053 |

### A.5 Consumer rules

- Manual ack, sent only after the DB transaction commits. Publisher confirms on every publish.
- Idempotency keys: Meta message id for inbound (T-048), `order_id:event` for outbound, `job_key` for jobs.
- Heartbeat 30 s, automatic reconnect with backoff, correlation id carried in message headers.
- RabbitMQ memory bound set with an absolute `vm_memory_high_watermark` so Railway usage stays predictable.
- Alert when any dead-letter queue is non-empty or `wa.inbound.q` backlog stays above a threshold (T-081).

### A.6 Demo readiness checklist

- [ ] Supabase project created, Auth hook adds `tenant_id` and `app_role` to the JWT (T-113)
- [ ] RLS verified through the backend with a non-bypass role (T-005, T-015)
- [ ] Railway `app` and `rabbitmq` deployed, topology declared by code (T-109, T-110)
- [ ] Duplicate webhook, retry, and dead-letter replay rehearsed (T-111, T-112)
- [ ] Keep-alive and usage alerts active (T-114)
- [ ] Only dummy data loaded; region decision recorded (T-108)

## Appendix B — Auth and database access design (T-113)

The SQL below is a sketch to settle the design. Check function signatures and hook behavior against the current Supabase documentation before implementing.

### B.1 Claim contract

| Claim | Set by | Used for |
|---|---|---|
| `sub` | Supabase Auth | User id, matches `app.users.id` |
| `tenant_id` | Access token hook | Tenant scope for the request |
| `app_role` | Access token hook | `owner` or `staff`, used for routing and as a sanity check |

- `role` is deliberately not used: Supabase reserves it for the Postgres role (`authenticated`).
- `outlet_ids` is deliberately not in the token: a token keeps its claims until it expires, so a removed assignment or a deactivated account would still look valid. Outlet access and active status are checked live in the database on every request (US-003: a deactivated staff member is rejected immediately).
- The token only identifies the caller. It never grants outlet access by itself.

### B.2 Token issuance (custom access token hook)

```sql
create function app.custom_access_token_hook(event jsonb) returns jsonb
language plpgsql stable as $$
declare
  claims jsonb := event->'claims';
  u record;
begin
  select tenant_id, role, is_active into u
  from app.users where id = (event->>'user_id')::uuid;

  if u is null or not u.is_active then
    return jsonb_build_object('error',
      jsonb_build_object('http_code', 403, 'message', 'account inactive'));
  end if;

  claims := jsonb_set(claims, '{tenant_id}', to_jsonb(u.tenant_id));
  claims := jsonb_set(claims, '{app_role}',  to_jsonb(u.role));
  return jsonb_set(event, '{claims}', claims);
end $$;

grant usage on schema app to supabase_auth_admin;
grant execute on function app.custom_access_token_hook to supabase_auth_admin;
revoke execute on function app.custom_access_token_hook from public, anon, authenticated;
grant select on app.users to supabase_auth_admin;  -- plus a policy for this role if RLS is on
```

### B.3 Token verification in FastAPI

- Fetch public keys from the project's JWKS endpoint and cache them. Refresh on an unknown `kid`, rate limited.
- Accept only the configured asymmetric algorithm (for example ES256 or RS256). Reject `none` and HS256.
- Check `iss`, `aud` (`authenticated`), `exp`, and that `tenant_id` and `app_role` are present.
- Load the `app.users` row and confirm it is active and that its `tenant_id` matches the token. Authorization uses this live row, not the claim alone.

### B.4 Database session

- All operational tables live in schema `app`, which is not exposed to the Supabase Data API. `anon` and `authenticated` have no grants on it.
- FastAPI and workers connect as a dedicated role `app_backend` (login, not `BYPASSRLS`, not superuser) through the transaction pooler (port 6543). Migrations use a direct or session-mode connection.
- Transaction mode does not support prepared statements: disable the statement cache in the driver (for example asyncpg `statement_cache_size=0`).
- Every request runs in one transaction that first sets local settings from the verified token:

```python
async with pool.acquire() as conn, conn.transaction():
    await conn.execute(
        "select set_config('app.tenant_id', $1, true),"
        "       set_config('app.user_id',   $2, true),"
        "       set_config('app.actor',     'user', true)",
        tenant_id, user_id)
    ...  # handler queries run here
```

- The third argument `true` makes the setting transaction-local, so it cannot leak to the next request on a pooled connection.
- The service role key is never used for tenant data.

### B.5 RLS policy sketch

```sql
create function app.current_tenant() returns uuid language sql stable as
$$ select nullif(current_setting('app.tenant_id', true), '')::uuid $$;

create function app.can_access_outlet(o uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from app.outlets ou
    where ou.id = o and ou.tenant_id = app.current_tenant()
      and (
        current_setting('app.actor', true) in ('system', 'agent')
        or exists (select 1 from app.users u
                   where u.id = nullif(current_setting('app.user_id', true), '')::uuid
                     and u.tenant_id = ou.tenant_id and u.is_active and u.role = 'owner')
        or exists (select 1 from app.staff_outlets so
                   join app.users u on u.id = so.user_id and u.is_active
                   where so.outlet_id = o
                     and so.user_id = nullif(current_setting('app.user_id', true), '')::uuid)
      )
  )
$$;

alter table app.orders enable row level security;
alter table app.orders force row level security;
create policy orders_scope on app.orders to app_backend
  using      (tenant_id = app.current_tenant() and app.can_access_outlet(outlet_id))
  with check (tenant_id = app.current_tenant() and app.can_access_outlet(outlet_id));
```

The same pattern repeats for every table that carries `tenant_id` and `outlet_id` (T-005). A missing tenant setting makes `current_tenant()` null, so queries return nothing instead of everything.

### B.6 Workers and system actions

- Workers and the scheduler have no user token. They set `app.actor` to `system` (or `agent` in Phase 2) and `app.tenant_id` from the message or job.
- The webhook needs to find the tenant from the receiving WhatsApp number before any tenant is known. A narrow `security definer` function `app.resolve_outlet_by_phone(phone)` returns only `tenant_id` and `outlet_id`. It is the only lookup that crosses tenants.
- Every ledger and stock write still records the actor (NFR3), whether `user`, `system`, or `agent`.

### B.7 What happens when access changes

| Event | Effect |
|---|---|
| Staff deactivated | Refresh tokens revoked (ban and sign-out) and the next request is rejected by the live `is_active` check, even while the old access token is still valid |
| Outlet assignment removed | The next request loses access (live `staff_outlets` check) |
| Role changed | Applies at once, because authorization reads `app.users.role` live. The `app_role` claim catches up at the next token refresh. |
| Token expires | Short expiry bounds the window for anything not checked live |

### B.8 What RLS protects and what it does not

RLS here protects against application bugs such as a forgotten `WHERE tenant_id`, because the backend sets the session context itself. It does not protect against a stolen backend database credential, since the holder could set any tenant. Keep the `app_backend` password in Railway secrets only, rotate it, and never log it.

### B.9 Acceptance tests (T-015, T-113)

- A tenant A request with no tenant filter returns no tenant B rows.
- A request with no `app.tenant_id` set returns no rows.
- Staff cannot read or write an outlet they are not assigned to, including by direct API call.
- A deactivated staff member is rejected on the next request, before the access token expires.
- Pooled connections do not leak one request's tenant into the next (run two tenants alternately through a pool of one connection).
- Tokens with HS256, `none`, a wrong `kid`, a wrong issuer or audience, or an expired `exp` are rejected.
- A sign-up attempt for an email that was not invited fails.
- `anon` and `authenticated` roles get nothing from `app` tables through the Data API.
