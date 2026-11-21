# Task Breakdown — SME Business Automation Platform

This backlog breaks down the 66 user stories in [User-Stories-SME-Automation-Platform.md](User-Stories-SME-Automation-Platform.md) into implementation tasks. Each task is intended to become an issue in Jira, Linear, or a similar tracker.

## Delivery assumptions

- MVP consists of Phase 0–1. The AI in the MVP is one scoped web chat agent built with LangChain Deep Agents (`deepagents`; PRD v0.21, FR6.6): recommendations (T-115), free-text orders (T-087), and free-text bookings (T-088), with read-only tools for menu, stock, table availability, and the quote (T-085). All fall back to the button flow, so every MVP flow still works with the agent switched off.
- The deterministic core owns orders, payments, stock, ledger, bills, and reservations.
- Phase 2 agent features can only call validated application tools; they cannot write directly to stock or ledger tables.
- Tasks in the same wave can run in parallel after their dependencies are complete.
- `P0` is required for the relevant release; `P1` is important follow-up work; `P2` is expansion.
- Task IDs are stable. Tasks added after the first version use T-100 and up, and some tasks moved to a different wave; IDs were not renumbered so existing tracker issues keep their keys.
- Hosting: Supabase provides Auth, PostgreSQL, and Storage; Railway runs the FastAPI app, the timer worker, and RabbitMQ. The demo runs on Supabase Free and Railway Hobby with dummy data only. A pilot with real merchants needs Supabase Pro, a RabbitMQ volume, and the region decision from T-108.
- Scope decision (2026-11-20, PRD v0.20): the customer channel is a **web chat** in the phone's browser (outlet link `/o/<slug>`, table QR `/t/<token>`), not WhatsApp. The WhatsApp tasks (T-045–T-048, T-051, T-084, T-100) move to **Phase 3** as an optional channel under T-148 and keep their IDs; the WhatsApp parts of T-036 (screenshot intake) and T-055 (templates) are re-planned under T-148, and those two IDs now carry the web chat versions; their first code is on the branch of PR #54 (closed, kept for reference). Wave 5 is now the web chat. The table QR web page built in PR #47–#51 (T-133–T-136) is reworked into the same chat. Web chat screens must be drawn in `design/` (T-139) before any web chat frontend work.
- RabbitMQ is used in every environment, including the demo, for timers only: web chat requests are handled by the API directly. Fixed-delay retries use TTL + dead-letter queues; business timers (unpaid timeout, no-show, anonymization, attendance) use the database-backed `scheduled_jobs` table. The full topology is in Appendix A.

## Wave 0 — Product and technical foundation

| ID | Task | User stories | Depends on | Priority |
|---|---|---|---|---|
| T-001 | Confirm domain glossary, business rules, status enums, payment modes, channel enums, and timezone behavior. | US-001–US-048 | — | P0 |
| T-002 | Define API boundaries between the deterministic core, the public web chat API (`/api/v1/public/*`), timer workers, admin app, and future agent layer. | US-014, US-036, US-042 | T-001 | P0 |
| T-003 | Bootstrap FastAPI service, React + TypeScript admin app, shared configuration, environment validation, and local development setup. | US-033–US-035 | — | P0 |
| T-004 | Create PostgreSQL migrations for tenants, outlets, users, outlet assignments, products, add-ons, prices, ingredients, recipes, orders, bills, payments, shifts, ledger, tables, reservations, customers, chat sessions, and audit events. | US-001–US-041 | T-001 | P0 |
| T-005 | Add `tenant_id` and `outlet_id` to all operational records and create PostgreSQL row-level security policies that read the tenant and user from per-request session settings set after token verification (T-113) and check outlet access against `staff_outlets` live (Appendix B). | US-002, US-003, US-038 | T-004, T-113 | P0 |
| T-006 | Integrate Supabase Auth: JWT verification in FastAPI using Supabase asymmetric signing keys (public keys from JWKS and cached, short access-token expiry, shared-secret HS256 tokens rejected), owner/staff roles from the claim contract in T-113, invite-only account creation (public sign-up disabled in Supabase Auth; the owner invites staff by email), session invalidation on deactivation (ban + sign-out through the Supabase admin API), and outlet-scope authorization. No custom password storage. | US-003, US-033, US-038 | T-004, T-079, T-113 | P0 |
| T-007 | Build shared money, tax, rounding, inventory-unit, and local-timezone utilities. | US-011, US-012, US-019, US-022 | T-001, T-004 | P0 |
| T-008 | Create a standard actor/audit context for named users, system jobs, and `agent`, including timestamp and reason fields. | US-004, US-006, US-016, US-030 | T-004, T-006 | P0 |
| T-009 | Add CI checks, migration checks, unit-test framework, API contract checks, and seed data for local development. | All | T-003, T-004 | P0 |
| T-079 | Provision a Supabase project per environment (PostgreSQL, Auth, private Storage buckets for menu photos, QRIS images, and attendance selfies), backups, and access policies. Region follows the T-108 decision. | US-039, US-049 | T-003, T-108 | P0 |
| T-104 | Build scheduled job infrastructure: a `scheduled_jobs` table (source of truth with `run_at`, status, idempotency key, cancellation) and a poller that publishes due jobs to RabbitMQ `jobs.due.q`, with at-least-once delivery, idempotent handlers that re-check current state, and late-job handling. Used for unpaid-order timeout, no-show release, anonymization, and attendance checks. Fixed-delay retries use the TTL queues from T-110, not this table. | US-021, US-027, US-041, US-051 | T-003, T-004, T-110, T-111 | P0 |
| T-105 | Set up Railway environments (demo, staging, production), container builds, GitHub-triggered deploys with a pre-deploy migration step and rollback, and secret management. Staging region follows the T-108 decision. | US-038, US-039, US-049 | T-003, T-009, T-079, T-109 | P0 |
| T-106 | Draft the customer privacy notice (PDP Law) with legal review and publish it at a stable URL per tenant. | US-040 | T-001 | P0 |
| T-108 | Decide how to meet the Indonesia data-residency requirement (US-039, NFR1). Checked on 2026-11-18 against the providers' region pages: neither Supabase nor Railway lists an Indonesia region; the nearest for both is Singapore (`ap-southeast-1` on Supabase, `asia-southeast1` on Railway). Demo: use Singapore with dummy data only. Pilot with real data: auth and the database stay on Supabase (Singapore), so obtain a legally reviewed cross-border transfer basis under the PDP Law, record the decision, and reflect it in the privacy notice (T-106) and the web chat privacy step (T-076). | US-039, US-049 | T-001 | P0 |
| T-109 | Create the Railway project and service topology: `app` (FastAPI API and timer worker as separate processes; split into two services for the pilot) and `rabbitmq` (single node, memory watermark set, volume optional in the demo and required in the pilot), private networking, health checks, and environment variables. Host the admin app and web chat on Cloudflare Pages or Vercel. | US-049 | T-003, T-108 | P0 |
| T-110 | Declare the RabbitMQ topology as code (exchanges, queues, bindings, TTL and dead-letter arguments, policies) per Appendix A, with idempotent declaration at startup and a topology test. | US-050, US-036 | T-003, T-109 | P0 |
| T-111 | Build the shared consumer framework: manual ack after DB commit, publisher confirms, prefetch, attempt counter, retryable/permanent error classification, tiered retry routing, dead-letter routing with failure reason, and correlation ID propagation. | US-050, US-037 | T-110 | P0 |
| T-112 | Build dead-letter visibility and replay: list, inspect, and requeue or discard dead-lettered messages (CLI or protected admin endpoint), with an audit record for each action. | US-050 | T-006, T-008, T-111 | P0 |
| T-113 | Define the JWT claim contract (`tenant_id` and `app_role`; outlet access and active status are checked live in the database), enable Supabase asymmetric JWT signing keys, implement the custom access token hook, and define the backend DB session pattern: transaction pooler connection, per-request session settings (`set_config(..., true)`) filled from the verified token, a system context for workers, and a non-bypass database role in a schema hidden from the Data API (details in Appendix B). The service role is never used for tenant data. | US-003, US-038 | T-004, T-079 | P0 |
| T-114 | Demo operations: keep-alive to prevent Supabase Free auto-pause, Railway usage alerts and spend limit, demo-data seed and reset, and a promotion checklist from demo to pilot (Supabase Pro and backups, RabbitMQ volume, split API and worker, region decision). | US-049 | T-105, T-109 | P1 |

## Wave 1 — Tenant, outlet, staff, and configuration

| ID | Task | User stories | Depends on | Priority |
|---|---|---|---|---|
| T-010 | Implement tenant creation with restaurant/cafe validation and owner assignment. | US-001 | T-004, T-006 | P0 |
| T-011 | Implement outlet CRUD and configuration for address, hours, timezone, public outlet slug, delivery fee, PB1, payment mode, reservation settings, and QRIS. | US-002, US-019, US-022 | T-005, T-007 | P0 |
| T-012 | Implement owner-created staff accounts (Supabase Auth email invitation), outlet assignments, deactivation, and login/session rejection after deactivation. | US-003 | T-006, T-011 | P0 |
| T-013 | Implement permission matrix for owner and staff actions at both API and UI route levels. | US-003, US-033 | T-006, T-012 | P0 |
| T-014 | Implement secure QRIS image upload to a private Supabase Storage bucket (signed URLs), storage metadata, replacement, and outlet-level access. | US-017 | T-011, T-079 | P0 |
| T-015 | Add API and integration tests for cross-tenant and cross-outlet access attempts, including direct API requests, tokens signed with a wrong key or algorithm, and sign-up attempts without an invitation. | US-002, US-003, US-038 | T-005, T-006, T-013 | P0 |

## Wave 2 — Menu, add-ons, recipes, and inventory

| ID | Task | User stories | Depends on | Priority |
|---|---|---|---|---|
| T-016 | Implement menu item CRUD with optional photo (placeholder when missing), description, active/inactive state, and shared tenant-level data. | US-005 | T-004, T-006, T-079 | P0 |
| T-017 | Implement add-on groups and options with required/optional selection rules, price delta, recipe delta, and a maximum of 10 options. | US-005, US-011 | T-016, T-007 | P0 |
| T-018 | Implement outlet-specific prices for menu items and add-on options. | US-002, US-005 | T-011, T-016, T-017 | P0 |
| T-019 | Implement ingredients, units, low-stock thresholds, and menu/add-on recipes. | US-006, US-007 | T-016, T-017 | P0 |
| T-020 | Implement append-only stock movements for restock, waste, adjustment, sale, and cancellation/reversal. | US-006, US-021, US-030 | T-008, T-019 | P0 |
| T-021 | Implement transactional recipe expansion and stock deduction/return, including add-ons and row-level/concurrency protection. | US-006, US-014, US-021 | T-019, T-020 | P0 |
| T-022 | Implement stock projection, low-stock warnings, sold-out calculation, and outlet-specific availability. | US-007, US-010, US-028 | T-020, T-021 | P0 |
| T-023 | Add tests for exact recipe quantities, add-on ingredient changes, no negative stock, immutable movements, and sold-out recovery after restock. | US-005–US-007, US-014 | T-020–T-022 | P0 |
| T-024 | Seed editable sample menu, sample photos, prices, and add-ons for every new tenant/outlet. | US-008 | T-016–T-018, T-107 | P0 |
| T-107 | Prepare sample menu content: items, descriptions, recipes, add-ons, and photos with usage rights. | US-008 | T-001 | P1 |

## Wave 3 — Order and bill domain

| ID | Task | User stories | Depends on | Priority |
|---|---|---|---|---|
| T-025 | Define order, order-item, add-on, payment, bill, order-event, and status-transition models. | US-014, US-016, US-020 | T-004, T-007, T-008 | P0 |
| T-026 | Implement a single order-creation service used by the web chat (outlet link and table QR), counter, and future agent tools. | US-014, US-034, US-042 | T-021, T-025 | P0 |
| T-027 | Implement quote calculation for subtotal, add-ons, PB1, delivery fee, pickup, and total using outlet settings. | US-011, US-012, US-019 | T-007, T-018, T-025 | P0 |
| T-028 | Implement confirmation-time stock recheck and atomic order creation; return item-level sold-out errors with replacement/remove options. | US-011, US-014 | T-021, T-026, T-027 | P0 |
| T-029 | Implement duplicate-safe customer actions: an `idempotency_keys` store keyed by the key sent from the page, covering place order, Saya sudah bayar, cancel, book, and cancel or reschedule a booking; a processed key returns the earlier result (FR6.4, NFR8). | US-014, US-037 | T-026, T-028 | P0 |
| T-030 | Implement order and payment status machines for web chat orders (always pay first), counter pay-first dine-in, counter open-bill dine-in, and takeaway orders. | US-016, US-020 | T-025, T-027 | P0 |
| T-031 | Implement status transition validation and immutable order event history with actor, timestamp, and reason where required. | US-004, US-016 | T-008, T-030 | P0 |
| T-032 | Implement cancellation and paid-order reversal workflows, including stock return versus waste behavior and refund ledger hooks. | US-004, US-021 | T-020, T-030, T-031 | P0 |
| T-033 | Implement open bills per table or guest name, one open bill per table, order attachment, running total, duration, and full-bill close. | US-020 | T-025, T-027, T-030 | P0 |
| T-035 | Add concurrency and transition tests for last-stock orders, invalid status changes, open-bill uniqueness, and mode changes preserving existing order flow. | US-014, US-016, US-020 | T-028–T-033 | P0 |
| T-137 | Split bill per item (issue #42, PRD v0.19): schema for several payments per bill and the order-item portions each part pays (`payment_items`, with a migration and RLS; a portion can be paid by at most one active part), bill detail with paid/unpaid portions and what is left, a part quote (subtotal, cumulative PB1, total), pay part (cash with amount received and shift, or QRIS; idempotent; ledger entries per part), undo a paid part with a reason (refund entry, audit log), refuse cancelling an order with paid items, close the bill when the last item is paid, and pay-what-is-left for a one-payment close; `allowed_actions` `split` / `pay_part` / `undo_part`. Update `docs/architecture/screen-endpoint-map.md` (S5, S5a) and `docs/domain/domain-glossary-and-rules.md`. Tests: AC10.11–AC10.15 figures (cash and QRIS parts on one bill, QRIS parts not in expected cash), concurrent pay of the same portion, cash count and cashflow still matching after a split (FR10.9). | US-064 | T-033, T-035, T-038, T-039, T-041 | P0 |

## Wave 4 — Payments, cashier shifts, ledger, and reports

| ID | Task | User stories | Depends on | Priority |
|---|---|---|---|---|
| T-037 | Implement the payment-proof model, `proof_submitted` payment status, staff payment-review queue, merchant-account confirmation step, mark-paid action, and reject-proof action (required reason, immediate cancellation with stock reversal, no ledger entry, reason shown in the customer's chat); actor and time recorded on both. The customer claim ("Saya sudah bayar", no screenshot) is in T-036. | US-017 | T-014, T-030, T-032 | P0 |
| T-038 | Implement cash payment capture, payment-method validation, amount received, change due, and no cash for web chat orders. | US-018 | T-025, T-027 | P0 |
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

## Wave 5 — Web chat and deterministic customer flows

The web chat (PRD §5.2, §5.6) serves both entry points from one frontend build: the outlet link `/o/<slug>` (online orders, recommendations, reservations) and the table QR `/t/<token>` (dine-in). Every step is a button or a short text input; free text goes to the AI only in Rekomendasi (T-115).

| ID | Task | User stories | Depends on | Priority |
|---|---|---|---|---|
| T-139 | Draw the web chat wireframes in figcraft before any frontend work (360 px first, Bahasa Indonesia): greeting and main menu from the outlet link and from a table QR, menu cards by category, add-on buttons, kitchen note, cart, summary with Pesan & bayar, name/phone/address step with the privacy notice, pickup/delivery choice, static QRIS payment with deadline and Saya sudah bayar, live order status, Pesanan Saya, Rekomendasi with the AI acknowledgement and fallback cards, the reservation flow, booking confirmation with booking code and Tambah ke kalender, Reservasi Saya with code + phone lookup, "Pesan di kasir" (no QRIS), invalid link/QR, and rate-limit messages. Update O8 (outlet slug and outlet QR, QR target setting removed) and the S2/S4 web-order cards for `web_online` (pickup/delivery, phone). Update `design/WIREFRAME-TRACEABILITY.md` and `docs/architecture/screen-endpoint-map.md`; the Q0–Q5 screens are replaced. | US-009–US-013, US-015, US-023, US-025, US-029, US-040, US-052, US-062, US-063 | — | P0 |
| T-140 | Migration for the web chat (PRD v0.20): add `web_online` to `order_channel`; `outlets.public_slug` (unique across the platform, changeable); `chat_sessions` (outlet, optional table, step, cart, last activity); `idempotency_keys`; `customers` per order or booking (name, phone, address; anonymizable) and `privacy_notice_acknowledgements`; `reservations.booking_code` and access key; drop the table QR target column. Decide whether the WhatsApp tables (`whatsapp_contacts`, `conversations`, `messages`, `processed_messages`, outlet WhatsApp number and catalog) are dropped or kept for Phase 3, and record it. RLS for every new table; update `docs/domain/domain-glossary-and-rules.md` (channels, customer data rules). **Done** (Wave 5a, migrations `20261121100000`/`20261121100100`): WhatsApp tables kept for Phase 3; the address stays on `orders.delivery_address`; dropping the table QR target column moves to T-147. | US-012, US-013, US-036, US-037, US-040, US-041, US-063 | T-004, T-133 | P0 |
| T-049 | Implement the web chat session on the server: a session per phone (cookie or device id) holding the current step, cart, chosen add-ons, and entered details, so a refresh or reopening the link on the same phone resumes where the customer left off; a cart with no activity for 2 hours is emptied (orders and bookings stay); no state in API memory (FR6.2, NFR6). **Done** (Wave 5a): `GET/PUT …/chat-session` with `X-Chat-Session`. | US-036 | T-029, T-140 | P0 |
| T-141 | Public outlet API scoped by the outlet slug (`/api/v1/public/o/<slug>/…`): resolve the outlet (name, hours, reservations enabled, whether ordering is possible), menu with outlet prices, add-ons, and sold-out; quote; place a pay-first `web_online` order (pickup or delivery, name and phone, address and flat fee for delivery) through the shared order-creation function with server-side pricing and an idempotency key, returning a per-order access key. Reuse the T-134 payment, claim, cancel, and status endpoints for both channels. Unknown or changed slugs return no data; rate limit per session and IP (FR2.6, FR2.10, NFR5, ACN5, ACN6). **Done** (Wave 5a). | US-012, US-036, US-063 | T-026–T-030, T-049, T-134, T-140 | P0 |
| T-050 | Implement the main menu: outlet link shows Pesan, Rekomendasi, and (when reservations are enabled) Reservasi and Reservasi Saya; table QR shows outlet, table, Pesan, and Rekomendasi; Pesanan Saya while the phone has an active order; Menu utama button and the "menu" keyword return to it from any flow, keeping the cart and creating nothing (FR2.0). | US-009 | T-049 | P0 |
| T-052 | Implement menu cards by category (photo or placeholder, description, outlet price, sold-out disabled) and add-on collection with buttons (required groups must be answered, optional can be skipped), kitchen note per item, and a cart the customer can open, change, or empty (FR2.1, FR2.2). | US-010, US-011 | T-017, T-022, T-049 | P0 |
| T-053 | Implement the summary (items, add-ons, notes, subtotal, PB1, delivery fee, total from the server quote), pickup/delivery choice, name and phone (outlet link) or name only (table), address for delivery, the privacy step (T-076), and Pesan & bayar calling the order-creation endpoint with an idempotency key; sold-out at confirmation names the item with remove/replace options (FR2.3, FR2.6, FR2.9). | US-011, US-012, US-014 | T-026–T-029, T-052, T-076, T-141 | P0 |
| T-054 | Table QR token generation and replacement (`tables.qr_token`, random per table). Built with T-133. | US-013 | T-011 | P0 |
| T-133 | Schema for the table QR web page (issue #44): order channel `web_table`, `orders.customer_name`, a per-order access key for public orders, and a customer payment claim on `payment_proofs` (no image, `claimed_at`); `tables.qr_token` (replaceable), with migrations and RLS. **Done** (PR #47); the table QR target column is removed by T-140. | US-062, US-063 | T-004, T-054 | P0 |
| T-134 | Public table API scoped by the table token: resolve the table, menu with outlet prices/add-ons/sold-out, place a pay-first `web_table` order with server-side pricing and an idempotency key (returns a per-order access key), the outlet's static QRIS, Saya sudah bayar (`proof_submitted`, stops auto-cancel), customer cancel while unpaid, and order status read with the access key; reject unknown or replaced tokens, rate limit per token and IP. **Done** (PR #47–#51); rework: drop the WhatsApp link and QR target from the resolve response, and share the payment, claim, cancel, and status endpoints with T-141. Wave 5a: payment, claim, cancel, status, chat session, and recommendations are shared with T-141 (`public_chat.py`); `target`/`whatsapp_url` stay deprecated until T-145/T-147. | US-062 | T-026–T-030, T-037, T-133 | P0 |
| T-036 | Implement the payment step in the chat for both web channels: the outlet's static QRIS, exact total, and deadline; Saya sudah bayar (`proof_submitted`, no screenshot) stops the unpaid timer; customer cancel until then; the staff rejection reason shown in the chat (FR2.14, FR11.2). Backend **done** (Wave 5a, both scopes); chat screen in T-145. | US-017, US-062 | T-014, T-037, T-134, T-141 | P0 |
| T-034 | Implement the configurable unpaid-order timeout for pay-first orders, stopped by Saya sudah bayar, with automatic cancellation and stock reversal; the cancellation shows in the chat, no message is sent (FR10.4). Wave 5a: covers `web_online` too, still lazy (on every chat or board read) until the T-104 poller exists. | US-021 | T-030, T-032, T-036, T-104 | P0 |
| T-055 | Implement status in the chat: an order and booking status endpoint polled while the chat is open so a change shows within 10 seconds without a reload; Pesanan Saya lists the phone's own orders (by access key) until one hour after they are completed or cancelled; a saveable order link; no messages outside the chat (FR2.15, FR6.5, FR10.3). Backend **done** (Wave 5a: status and Pesanan Saya endpoints); polling in T-145. | US-015 | T-030, T-134, T-141 | P0 |
| T-145 | Build the web chat frontend on public routes `/o/<slug>` and `/t/<token>` from one build, following the T-139 wireframes: conversation layout (outlet messages, the customer's choices as replies, buttons, menu cards, text box), the flows from T-050–T-055 and T-036, device-only prefill of name/phone/address with a clear option (T-077), retry with the same idempotency key after a lost connection, and the invalid link/QR and rate-limit messages. Replaces the Q0–Q5 table page from T-135. | US-009–US-015, US-062 | T-139, T-049–T-055, T-036 | P0 |
| T-056 | Add end-to-end web chat tests at 360 px: online pickup and delivery, table order, add-ons and notes, sold-out at confirmation, double tap and retry (one order), unpaid timeout, Saya sudah bayar → confirm/reject, status within 10 s, Pesanan Saya expiry, cart expiry after 2 h, changed slug and replaced token, and "Pesan di kasir" without QRIS. | US-009–US-015, US-036, US-037, US-062 | T-034, T-036, T-049–T-055, T-145 | P0 |

## Wave 6 — Reservations and tables

| ID | Task | User stories | Depends on | Priority |
|---|---|---|---|---|
| T-057 | Implement table CRUD, capacity, area, bookable hours, duration, booking window, party limit, reminder time (used for the calendar alert), and cancellation cutoff. | US-022 | T-011, T-025 | P0 |
| T-058 | Implement timezone-aware availability calculation and smallest-fitting-table assignment. | US-022, US-023 | T-007, T-057 | P0 |
| T-059 | Add database-level exclusion/locking rule preventing overlapping reservations, including concurrent requests. | US-024 | T-057, T-058 | P0 |
| T-060 | Implement the reservation flow in the web chat and its public API (outlet slug): party size, date, available time, name and phone (privacy step, T-076), review, and confirmation with an idempotency key; at most 2 upcoming bookings per phone number per outlet, refused without holding a table (FR9.2, AC9.11). | US-023 | T-049, T-058, T-059, T-076, T-141 | P0 |
| T-061 | Implement booking confirmation and Reservasi Saya: booking code and access key, a saveable booking link, Tambah ke kalender (an `.ics` file with the booking in the outlet's time zone and an alert at the outlet's reminder time; no reminder message); Reservasi Saya lists upcoming bookings from this phone, finds a booking on another phone by booking code + phone number with rate-limited wrong attempts, and cancels or reschedules up to the cutoff (FR9.4, FR9.5, AC9.5, AC9.6, AC9.12). | US-025 | T-055, T-060 | P0 |
| T-062 | Implement staff reservation board with phone/in-person booking, table reassignment, seated/completed/cancelled/no-show states, and event audit. | US-026 | T-006, T-057, T-060 | P0 |
| T-063 | Implement table occupancy for walk-in guests (no reservation) and availability blocking. | US-027 | T-057, T-058, T-062 | P0 |
| T-064 | Implement 15-minute post-booking hold, automatic no-show, table release, and seated-before-deadline behavior. | US-027 | T-060, T-062, T-104 | P0 |
| T-065 | Add reservation tests for capacity limits, timezone display, double-booking, the 2-booking limit, calendar file times, code + phone lookup, cutoff, walk-ins, reassignment, and no-show release. | US-022–US-027 | T-057–T-064 | P0 |

## Wave 7 — Admin application and recommendations

| ID | Task | User stories | Depends on | Priority |
|---|---|---|---|---|
| T-066 | Build owner onboarding, outlet settings (including cash drawers), staff management, QRIS upload, menu, add-on, recipe, and price screens. | US-001–US-006, US-017, US-019 | T-010–T-019 | P0 |
| T-132 | Build menu photo upload (the photo part of T-016, left out of Wave 2): a private Supabase Storage bucket for menu photos, owner-only upload and replacement from the photo box in the menu edit card (wireframe O5) with size and type checks, `photo_path` saved on the item and `has_photo` returned by the API, short-lived signed URLs for previews in the admin app, the photo shown wherever the wireframes show it, with a placeholder when an item has no photo (photos are optional, FR2.11). Update `docs/architecture/screen-endpoint-map.md` for the new endpoint. | US-005, US-008 | T-014, T-016, T-066, T-079 | P0 |
| T-135 | Customer table web page (wireframe Q0–Q5 + Q2a) and the staff S2 web-order card / S4 claim review. **Done** (PR #48–#51); the customer page is replaced by the web chat (T-145), the staff side stays and gains `web_online` (T-146). | US-062 | T-134, T-066, T-068 | P0 |
| T-136 | O8: download QR per table (PNG) and all tables (PDF), and "Ganti" to replace a table's token. **Done** (PR #48); the QR target setting is removed by T-147. | US-063 | T-057, T-133, T-134 | P0 |
| T-146 | Staff side for `web_online` orders, following the T-139 wireframes: S2 order card and S4 review show the channel, pickup or delivery, name, phone, and address, and "Pelanggan bilang sudah bayar"; delivery orders get the out-for-delivery step; buttons only from `allowed_actions`. | US-012, US-017, US-062 | T-068, T-135, T-139, T-141 | P0 |
| T-147 | O8 update: set and change the outlet slug (unique, old link stops working), download the outlet QR code of the link, remove the QR target setting; owner only, including through the API (FR2.10, FR2.16). | US-063 | T-136, T-139, T-140 | P0 |
| T-067 | Build staff counter order screen with dine-in and takeaway order types, add-ons, table selection, payment, and order submission. | US-034 | T-026–T-030, T-033, T-038, T-039, T-057 | P0 |
| T-068 | Build order board with payment review, lifecycle actions, cancellation/reversal, and open-bills view. | US-016–US-021 | T-030–T-033, T-037–T-039 | P0 |
| T-138 | Build split bill per item in the admin app (wireframe S5 "⇄ Split per item", S5a dialog, S5b QRIS step for one part, S5c bill after partial payment, M3 + M3a + M3b at 360 px): pick unpaid items or portions, part totals from the server, pay each part through the S1 payment popup (cash on the part total; static QRIS showing only the part's amount with the merchant-check list), paid parts list with "Batalkan…" (reason), remaining amount on the bill card, "Bayar sisa"; buttons only from `allowed_actions` (FR10.9). | US-064 | T-068, T-072, T-137 | P0 |
| T-069 | Build stock, stock movement, low-stock, and sold-out screens. | US-006, US-007 | T-020–T-023 | P0 |
| T-070 | Build reservation/table view and cashier shift screens. | US-018, US-026, US-027 | T-039, T-062–T-064 | P0 |
| T-071 | Build owner dashboard for outlet-level and combined sales, cashflow, PB1, payment method, and stock summaries. | US-032, US-033 | T-041–T-043 | P0 |
| T-072 | Build role-aware navigation and responsive layouts for 360 px mobile width through desktop. | US-003, US-033, US-035 | T-006, T-066–T-071 | P0 |
| T-073 | Implement owner picks and tags, outlet best-seller query for the last 30 days, sold-out filtering, de-duplication, and 30-item limit. | US-028 | T-016, T-022, T-026 | P0 |
| T-074 | Implement Rekomendasi in the web chat: owner's picks and best sellers (T-073) as menu cards, add-to-cart handoff into the normal add-on, summary, and Pesan & bayar flow (FR8.2, FR8.3). | US-029 | T-052, T-073, T-145 | P0 |
| T-115 | Implement the agent gateway and AI recommendations in the Rekomendasi flow: a LangChain Deep Agents agent (`deepagents`, `create_deep_agent`, running inside the FastAPI service, no separate agent server) with the model as a LangChain chat model over an OpenAI-compatible chat completions client (`LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` per environment; the model must support tool calling), prompt versioning, the read-only tools from T-085 plus best sellers and tags; suggestions limited to active, available items at outlet prices with owner's picks first, shown as menu cards and handed to the T-074 add-to-cart flow; an immediate acknowledgement with a typing indicator before the agent starts; errors or the 30-second limit fall back to the T-073 rule-based cards; tool calls logged with actor `agent`. | US-052 | T-008, T-049, T-073, T-074, T-085 | P0 |
| T-085 | Define the agent's versioned read-only tools, scoped to the chat session's outlet (FR6.6): menu (items, add-on groups and options, outlet prices, tags), stock and sold-out state, table availability for a party size and date in the outlet's time zone, best sellers, and the server quote. No write tools and no tool that reads customers, orders, bookings, staff, or finances. Phase 2 adds FAQ data and sales lookup for forecasting. | US-042, US-043, US-052, US-066 | T-022, T-026, T-027, T-058 | P0 |
| T-086 | Extend the agent gateway from T-115 for orders and bookings: conversation context per chat session (FR6.2) so plain answers ("keju") fill the open question, the scope rules in FR6.6 (outlet only, ordering/recommendations/reservations only, off-topic refusal with the main menu buttons), at most 4 data-tool calls and 30 seconds per message (enforced by the gateway, not the prompt), the immediate acknowledgement, and fallback to the button flow. Deep Agents configuration: only our tools from T-085; built-in filesystem tools on the in-memory state backend only (or hidden); default general-purpose subagent removed; planning tool not enabled; LangSmith tracing off by default (customer messages stay in our region, NFR1). | US-042, US-043, US-066 | T-049, T-085, T-115 | P0 |
| T-087 | Implement free-text ordering in the web chat (wireframe C14): the agent reads menu, add-ons, and stock through its tools, asks clarification questions for missing required groups or unmatched items and accepts plain-word answers, names sold-out or unknown items instead of adding them, and shows the summary priced by the quote tool with Ubah and Pesan & bayar; Pesan & bayar calls the shared order-creation function (T-026) with an idempotency key (FR2.4, AC2.22, AC2.23). | US-042 | T-053, T-085, T-086, T-145 | P0 |
| T-088 | Implement free-text booking requests in the web chat (wireframe C15): the agent reads table availability in the outlet's time zone, offers the nearest free times when the asked time is full, asks for anything missing, then hands over to the C10 name, phone, privacy, and Cek lagi steps; Konfirmasi booking calls the T-060 booking function (FR9.9, AC9.13). | US-043 | T-058–T-060, T-085, T-086, T-145 | P0 |
| T-091 | Enforce the agent scope and guardrails (FR6.6): read-only, outlet-scoped tools only (checked in the tool layer, not only the prompt), no write path, no order or booking before the customer's tap, prices only from the quote tool, the 4-call / 30-second limit, off-topic refusal, actor=`agent`, and a tool-call log without personal data (AC6.8, AC6.9). | US-042, US-043, US-052, US-066 | T-085–T-088 | P0 |
| T-092 | Build the agent evaluation set and run it in CI before each prompt or model change: ambiguous orders, missing required add-ons answered in plain words, unknown and sold-out items, wrong quantities, slang and typos in Bahasa Indonesia, prices that must match the quote, booking dates and times in WIB/WITA/WIT, full time slots, off-topic and other-outlet requests, prompt injection, and duplicate confirmations. | US-042, US-043, US-052, US-066 | T-087, T-088, T-091 | P0 |
| T-101 | Build the owner audit log screen for order reversals and status changes, filterable by outlet, staff member, and date, showing order, actor, time, and reason. | US-004 | T-031, T-032, T-066 | P0 |
| T-102 | Build the owner cash count report: every shift's starting cash, expected cash, counted cash, difference, and who counted, per outlet. | US-018 | T-040, T-071 | P0 |
| T-116 | Build the attendance domain: `attendance_records` and append-only `attendance_events` (clock in, clock out, flag, correction) with outlet-local times, one open record per staff member, the tablet and the selfie stored with each clock-in and clock-out (a photo is required), RLS, and API endpoints for clock in and clock out (attendance tablet session only) and own history (staff session). | US-053 | T-005, T-006, T-007, T-008, T-011, T-012, T-121 | P0 |
| T-117 | Build the attendance tablet screens: staff list for the outlet, selfie capture with the front camera (retake, camera-denied state), clock in or out confirmation with time and duration, first-use privacy notice, and an offline message without queueing submissions (NFR7). Also build the staff's own attendance history in the admin app (read-only, with their selfies) at 360 px. | US-053 | T-072, T-116, T-121, T-122 | P0 |
| T-118 | Add the missing-clock-out check on the `scheduled_jobs` scheduler (job type `attendance_flag`, run at outlet closing time plus the owner-set grace period): flag the record "needs correction" without inventing a clock-out time, and re-check that the record is still open before acting. Add the grace-period setting to outlet settings. | US-053 | T-011, T-104, T-116 | P0 |
| T-119 | Build the owner attendance report and correction screens: filter by outlet, staff member, and date range; hours per day and in total; flagged records; clock-in and clock-out selfies for each record; correction with a required reason that keeps the original values; outlet-local day boundaries. | US-054 | T-072, T-116, T-118, T-122 | P0 |
| T-120 | Add attendance tests: one open record per staff member, clock in without a selfie, clock in for an unassigned outlet and from a staff token by direct API call, a tablet session opening other admin data, a revoked tablet, staff seeing only their own records and selfies, selfie deletion after 45 days (and staff unable to delete their own), WIB/WITA/WIT day boundaries, flagging after worker downtime, and the correction audit trail. | US-053, US-054, US-055 | T-116–T-119, T-121, T-122 | P0 |
| T-121 | Build outlet attendance tablets: owner-generated one-time pairing code per outlet, a device account and session scoped to one outlet that can only list that outlet's staff and record attendance (enforced in the API and RLS), a device list with last activity, and revocation that rejects the tablet on its next request. Add the pairing and device list to outlet settings. | US-055 | T-006, T-011, T-113 | P0 |
| T-122 | Store attendance selfies in a private Supabase Storage bucket: upload from the tablet with size and type checks, short-lived signed URLs for the owner and the staff member only, and a scheduled `attendance_photo_purge` job that deletes photos after 45 days while keeping the records (staff cannot delete selfies, not even their own). | US-053, US-054 | T-079, T-104, T-116 | P0 |
| T-123 | Implement busyness queries for the owner: orders per hour per outlet and period (outlet-local time, opening hours only) with busy (≥ 130% of the hourly average) and quiet (≤ 60%) marking, the day-by-hour average over the last 4 weeks, current crowd per outlet (occupied tables, active orders, Ramai/Normal/Sepi status), and the hour-group filter for dashboard figures. Owner-only at the API. Include tests for time zones, thresholds, and totals. | US-056 | T-007, T-013, T-026, T-030, T-057, T-063 | P1 |
| T-124 | Build the owner dashboard busyness views (wireframe O2): hour-group filter in the header, day-by-hour busyness map, current crowd per outlet, and orders-per-hour chart with busy and quiet hours marked. | US-056 | T-071, T-123 | P1 |
| T-075 | Add frontend accessibility, responsive, permission, and critical-flow tests. | US-033–US-035 | T-066–T-074, T-101, T-102, T-117, T-119, T-124, T-130, T-132, T-135, T-136, T-145–T-147 | P0 |

## Wave 8 — Customer data, compliance, and MVP hardening

| ID | Task | User stories | Depends on | Priority |
|---|---|---|---|---|
| T-076 | Implement the privacy step in the web chat: before a name, phone number, or address is submitted, show the short notice and the link to the full notice (T-106); store the customer details per order or booking in `customers` and record the notice version and time (FR12.1). No accounts and no membership. Backend part **done** in Wave 5a (`customers`, notice version check, anonymization triggers); the chat step is in T-145. | US-040 | T-004, T-106, T-140 | P0 |
| T-077 | Implement device-only prefill: the phone may remember the customer's own name, phone number, and last address in local storage and prefill them next time, with a clear option in the chat; the server never links orders from different visits into a profile (FR12.3, AC12.4). | US-041 | T-076, T-145 | P0 |
| T-103 | Implement the scheduled anonymization job for every customer record, run once its order is completed or cancelled or its booking is completed, cancelled, or no-show; orders and ledger totals stay unchanged (FR12.2). | US-041 | T-076, T-104 | P0 |
| T-078 | Ensure personal data is absent from append-only ledger and stock tables; add automated privacy regression tests. | US-040, US-041 | T-076, T-103 | P0 |
| T-080 | Add security hardening: secret management, token expiry, public web chat scoping (slug, table token, access keys, booking code + phone), rate limiting per session and IP, upload validation, and audit-log protection. | US-003, US-036, US-038, US-039 | T-006, T-008, T-014, T-141 | P0 |
| T-081 | Add queue metrics (RabbitMQ management API), structured logs, correlation IDs, retry/DLQ dashboards, and alerts for dead-lettered jobs and job backlog; web chat request latency (95% within 1 s, ACN4). | US-036, US-037, US-050 | T-111, T-112 | P0 |
| T-082 | Run performance, concurrency, tenant-isolation, backup-restore, and failure-recovery tests against MVP acceptance criteria. | US-014, US-024, US-030, US-037–US-039 | T-015, T-035, T-044, T-056, T-065, T-075, T-078, T-080, T-081, T-103, T-105, T-120, T-131, T-092 | P0 |
| T-083 | Execute full UAT with owner, cashier/waiter, and customer scenarios; triage defects and produce release checklist. | All MVP stories | T-082 | P0 |

## MVP release gates

The MVP is ready for release only when:

1. T-083 is complete and all MVP acceptance criteria pass.
2. A web chat order from the outlet link, a table-QR order, and a counter order use the same order service and produce correct stock, payment, and ledger outcomes.
3. Pay-first and open-bill outlets both work, including payment restrictions and existing-order behavior after a mode change.
4. Reservation concurrency, 15-minute no-show release, and timezone behavior pass.
5. A double tap, a retry after a lost connection, or a redelivered timer job cannot create duplicate orders, bookings, stock movements, or ledger entries.
6. Cross-tenant access tests and append-only audit checks pass, and the data-residency decision from T-108 is met (Indonesia region, or a documented and approved exception) before real merchant data is stored.
7. Every web chat flow (order, payment, status, recommendations, reservations) works at 360 px without login, and statuses refresh in the chat within 10 seconds.
8. Dead-letter queues are empty or triaged, a replay has been rehearsed (T-112), and the demo-to-pilot promotion checklist (T-114) is complete.

## Phase 2 — Agent layer

| ID | Task | User stories | Depends on | Priority |
|---|---|---|---|---|
| T-089 | Implement FAQ handling and advisory upsell without direct cart/order mutation (recommendations, free-text orders, and free-text bookings ship in the MVP as T-115, T-087, and T-088). | US-044 | T-085, T-086 | P1 |
| T-090 | Implement demand forecast, restock suggestion, and unusual-cashflow detection views for owners. | US-045 | T-043, T-085, T-086 | P1 |
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
| T-148 | WhatsApp as an optional customer channel (PRD §4 Phase 3): reuse the moved tasks below and the PR #54 branch; old screenshot intake (former T-036) and template notifications (former T-055) are re-planned here. Re-check Meta's country restriction for Indonesian numbers (error 130497) before starting. The web chat stays the main channel. | US-065 | MVP web chat | P2 |
| T-045 | Configure Meta WhatsApp Cloud API/BSP credentials, webhook verification, signature validation, and outlet-number mapping. | US-065 | T-011 | P2 |
| T-100 | Build per-outlet WhatsApp onboarding: Meta Embedded Signup or BSP flow, business verification status, phone number registration, catalog creation and linking, and setup status shown to the owner. | US-065 | T-011, T-045 | P2 |
| T-046 | Implement inbound webhook persistence and publishing to `wa.inbound` with immediate acknowledgement; process one conversation at a time (Postgres advisory lock on conversation id). | US-065 | T-045, T-008, T-110, T-111 | P2 |
| T-047 | Implement outbound WhatsApp worker on `wa.outbound.q` and catalog sync worker on `catalog.sync.q`, using the retry tiers and error classification from T-111 (429 and 5xx retry; 4xx dead-letter; outside-24-hour-window error falls back to a template once). | US-065 | T-046, T-111 | P2 |
| T-048 | Implement processed-message store and idempotent worker behavior for webhook retries and RabbitMQ redelivery. | US-065 | T-046 | P2 |
| T-051 | Implement catalog sync for item metadata, photos, outlet prices, active state, and unavailable/sold-out state. | US-065 | T-016–T-018, T-022, T-047, T-100 | P2 |
| T-084 | Create the Meta template library and submit order-update, auto-cancellation, payment-rejected, payment-request, reservation-confirmation, and reservation-reminder templates as early as possible, since Meta's review is outside our control. Keep template names and parameters in a shared registry used by T-055. | US-065 | T-001 | P2 |

## Critical path

The shortest dependency path to a usable MVP is:

`T-001 → T-004 + T-108 → T-079 → T-113 → T-005/T-006 → T-016–T-022 → T-025–T-033 → T-037–T-041 → T-139 + T-140 → T-049–T-053, T-141 → T-036/T-034 → T-055 → T-145 → T-066–T-072 → T-076–T-078/T-103 → T-082 → T-083`

One external dependency runs alongside it and can block release regardless of engineering progress, so start it early:

- The Supabase and Railway region decision (T-108), which gates any real merchant data.

The following work can proceed in parallel once the foundation is ready:

- Platform and infrastructure: T-079, T-104, T-105, T-108–T-114
- Tenant/staff administration: T-010–T-015
- Menu and inventory: T-016–T-024
- Purchase orders and supplier debt: T-125–T-131 (after the ledger, T-041; not on the order critical path)
- Admin shell and screens: T-066–T-072
- Web chat wireframes: T-139 (first; no web chat frontend before it)
- Reservations: T-057–T-065 (not on the order critical path; the chat flow needs T-049 and T-141, no-show release needs T-104)
- Recommendations: T-073–T-074, T-115
- Legal and content: T-106, T-107

## Suggested issue labels

Use these labels when importing the backlog:

- `phase:mvp`, `phase:p2`, `phase:p3`
- `domain:platform`, `domain:auth`, `domain:menu`, `domain:inventory`, `domain:orders`, `domain:payments`, `domain:webchat`, `domain:reservations`, `domain:admin`, `domain:agent`
- `type:backend`, `type:frontend`, `type:worker`, `type:database`, `type:qa`, `type:devops`
- `risk:financial`, `risk:privacy`, `risk:concurrency`, `risk:external-api`

## Appendix A — Demo hosting and RabbitMQ topology

### A.1 Hosting map

| Component | Runs on | Demo | Pilot |
|---|---|---|---|
| PostgreSQL, Auth, Storage | Supabase | Free plan, dummy data | Pro plan, backups, region per T-108 |
| FastAPI API + timer worker | Railway service `app` | One service, two processes | Two services (`api`, `worker`) |
| RabbitMQ | Railway service `rabbitmq` | Single node, no volume, memory watermark ~256 MiB | Single node with volume |
| Admin app and web chat (React) | Cloudflare Pages or Vercel | Free tier | Same |
| DB connections | Supabase transaction pooler (port 6543) | Small pool per process | Same |

### A.2 Exchanges and queues

All queues are durable, messages are persistent, and everything lives in one vhost (`sme`). The delayed-message plugin is not used.

| Exchange | Queue | Producer | Consumer | Notes |
|---|---|---|---|---|
| `jobs` (direct) | `jobs.due.q` | Scheduler poller (T-104) | Job handlers | Handlers are idempotent and re-check current state. |
| `jobs.dlx` (direct) | `jobs.dead.q` | Consumer framework (T-111) | Replay tool (T-112) | No TTL. Kept until an admin replays or discards. |

That is 1 working queue, 1 dead-letter queue, and 3 retry queues (A.3), 5 in total. The WhatsApp queues of earlier drafts (`wa.inbound`, `wa.outbound`, `catalog.sync`) come back only with the Phase 3 WhatsApp channel (T-148).

### A.3 Retry tiers (TTL + dead-letter)

Retry delays are fixed, so queue-level TTL is safe here (no head-of-line blocking).

| Retry exchange (topic) | Queue | Queue TTL | Dead-letters to |
|---|---|---|---|
| `retry.5s` | `retry.5s.q` | 5 s | `retry.return` |
| `retry.30s` | `retry.30s.q` | 30 s | `retry.return` |
| `retry.2m` | `retry.2m.q` | 2 min | `retry.return` |

- The consumer republishes a failed message to a retry exchange using the original routing key (for example `jobs`). After the TTL, RabbitMQ dead-letters it to `retry.return` (topic) with the same routing key, and `retry.return` is bound to the matching working queue.
- The app increments an `x-attempt` header on each republish. Attempt 1 uses 5 s, attempt 2 uses 30 s, attempt 3 and later use 2 min, until the queue's maximum is reached. Then the message goes to the matching dead-letter queue with `x-failure-reason`.
- **Retryable:** network timeout, DB deadlock or serialization failure, lock timeout.
- **Permanent (dead-letter immediately):** invalid payload, unknown job type.

### A.4 Scheduled jobs (not TTL)

Business timers have variable delays (the unpaid timeout is configured per outlet, and no-show depends on booking time). Per-message TTL in one queue blocks behind the oldest message, and delayed messages are lost if the broker restarts without a volume. So the source of truth is the database:

1. A job is inserted into `scheduled_jobs` (`job_key`, `type`, `run_at`, `status`, `payload`) in the same transaction as the business change, for example order creation.
2. A poller (every 15 s) selects due jobs with `FOR UPDATE SKIP LOCKED`, publishes to `jobs` with publisher confirms, and marks them `enqueued`.
3. The handler checks the current state before acting (for example the order is still unpaid and the customer has not tapped Saya sudah bayar), then marks the job `done`. A job cancelled earlier (Saya sudah bayar tapped, booking seated) is skipped.
4. Jobs that are overdue after downtime run immediately on the next poll.

| Job type | Created when | Runs at | Spec |
|---|---|---|---|
| `unpaid_timeout` | Pay-first order created (T-034) | Order time + outlet timeout | US-021 |
| `no_show_release` | Reservation confirmed (T-064) | Booking time + 15 min | US-027 |
| `anonymize_customer` | Order completed or cancelled, or booking completed, cancelled, or no-show (T-103) | Immediately after the end event | US-041 |
| `attendance_flag` | Staff member clocks in (T-118) | Outlet closing time + grace period | US-053 |
| `attendance_photo_purge` | Selfie stored (T-122) | Photo time + 45 days | US-053 |

### A.5 Consumer rules

- Manual ack, sent only after the DB transaction commits. Publisher confirms on every publish.
- Idempotency keys: the page's key for customer actions (T-029), `job_key` for jobs.
- Heartbeat 30 s, automatic reconnect with backoff, correlation id carried in message headers.
- RabbitMQ memory bound set with an absolute `vm_memory_high_watermark` so Railway usage stays predictable.
- Alert when the dead-letter queue is non-empty or `jobs.due.q` backlog stays above a threshold (T-081).

### A.6 Demo readiness checklist

- [ ] Supabase project created, Auth hook adds `tenant_id` and `app_role` to the JWT (T-113)
- [ ] RLS verified through the backend with a non-bypass role (T-005, T-015)
- [ ] Railway `app` and `rabbitmq` deployed, topology declared by code (T-109, T-110)
- [ ] Double-tap Pesan & bayar, job retry, and dead-letter replay rehearsed (T-029, T-111, T-112)
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
- The public web chat API needs to find the tenant from the outlet slug or table token before any tenant is known. A narrow `security definer` function (`app.resolve_public_scope(slug | token)`) returns only `tenant_id`, `outlet_id`, and the table if any. It is the only lookup that crosses tenants.
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
