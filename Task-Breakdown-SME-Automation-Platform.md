# Task Breakdown — SME Business Automation Platform

This backlog breaks down the 48 user stories in [User-Stories-SME-Automation-Platform.md](User-Stories-SME-Automation-Platform.md) into implementation tasks. Each task is intended to become an issue in Jira, Linear, or a similar tracker.

## Delivery assumptions

- MVP consists of Phase 0–1 and must work without the AI agent.
- The deterministic core owns orders, payments, stock, ledger, bills, and reservations.
- Phase 2 agent features can only call validated application tools; they cannot write directly to stock or ledger tables.
- Tasks in the same wave can run in parallel after their dependencies are complete.
- `P0` is required for the relevant release; `P1` is important follow-up work; `P2` is expansion.

## Wave 0 — Product and technical foundation

| ID | Task | User stories | Depends on | Priority |
|---|---|---|---|---|
| T-001 | Confirm domain glossary, business rules, status enums, payment modes, channel enums, and timezone behavior. | US-001–US-048 | — | P0 |
| T-002 | Define API boundaries between the deterministic core, WhatsApp workers, admin app, and future agent layer. | US-014, US-036, US-042 | T-001 | P0 |
| T-003 | Bootstrap FastAPI service, React + TypeScript admin app, shared configuration, environment validation, and local development setup. | US-033–US-035 | — | P0 |
| T-004 | Create PostgreSQL migrations for tenants, outlets, users, outlet assignments, products, add-ons, prices, ingredients, recipes, orders, bills, payments, shifts, ledger, tables, reservations, customers, messages, and audit events. | US-001–US-041 | T-001 | P0 |
| T-005 | Add `tenant_id` and `outlet_id` to all operational records and create PostgreSQL row-level security policies. | US-002, US-003, US-038 | T-004 | P0 |
| T-006 | Build token authentication, password handling, session invalidation, owner/staff roles, and outlet-scope authorization. | US-003, US-033, US-038 | T-004 | P0 |
| T-007 | Build shared money, tax, rounding, inventory-unit, and local-timezone utilities. | US-011, US-012, US-019, US-022 | T-001, T-004 | P0 |
| T-008 | Create a standard actor/audit context for named users, system jobs, and `agent`, including timestamp and reason fields. | US-004, US-006, US-016, US-030 | T-004, T-006 | P0 |
| T-009 | Add CI checks, migration checks, unit-test framework, API contract checks, and seed data for local development. | All | T-003, T-004 | P0 |

## Wave 1 — Tenant, outlet, staff, and configuration

| ID | Task | User stories | Depends on | Priority |
|---|---|---|---|---|
| T-010 | Implement tenant creation with restaurant/cafe validation and owner assignment. | US-001 | T-004, T-006 | P0 |
| T-011 | Implement outlet CRUD and configuration for address, hours, timezone, WhatsApp number, delivery fee, PB1, payment mode, reservation settings, and QRIS. | US-002, US-019, US-022 | T-005, T-007 | P0 |
| T-012 | Implement owner-created staff accounts, outlet assignments, deactivation, and login/session rejection after deactivation. | US-003 | T-006, T-011 | P0 |
| T-013 | Implement permission matrix for owner and staff actions at both API and UI route levels. | US-003, US-033 | T-006, T-012 | P0 |
| T-014 | Implement secure QRIS image upload, storage metadata, replacement, and outlet-level access. | US-017 | T-011 | P0 |
| T-015 | Add API and integration tests for cross-tenant and cross-outlet access attempts, including direct API requests. | US-002, US-003, US-038 | T-005, T-006, T-013 | P0 |

## Wave 2 — Menu, add-ons, recipes, and inventory

| ID | Task | User stories | Depends on | Priority |
|---|---|---|---|---|
| T-016 | Implement menu item CRUD with required photo, description, active/inactive state, and shared tenant-level data. | US-005 | T-004, T-006 | P0 |
| T-017 | Implement add-on groups and options with required/optional selection rules, price delta, recipe delta, and a maximum of 10 options. | US-005, US-011 | T-016, T-007 | P0 |
| T-018 | Implement outlet-specific prices for menu items and add-on options. | US-002, US-005 | T-011, T-016, T-017 | P0 |
| T-019 | Implement ingredients, units, low-stock thresholds, and menu/add-on recipes. | US-006, US-007 | T-016, T-017 | P0 |
| T-020 | Implement append-only stock movements for restock, waste, adjustment, sale, and cancellation/reversal. | US-006, US-021, US-030 | T-008, T-019 | P0 |
| T-021 | Implement transactional recipe expansion and stock deduction/return, including add-ons and row-level/concurrency protection. | US-006, US-014, US-021 | T-019, T-020 | P0 |
| T-022 | Implement stock projection, low-stock warnings, sold-out calculation, and outlet-specific availability. | US-007, US-010, US-028 | T-020, T-021 | P0 |
| T-023 | Add tests for exact recipe quantities, add-on ingredient changes, no negative stock, immutable movements, and sold-out recovery after restock. | US-005–US-007, US-014 | T-020–T-022 | P0 |
| T-024 | Seed editable sample menu, sample photos, prices, and add-ons for every new tenant/outlet. | US-008 | T-016–T-018 | P0 |

## Wave 3 — Order and bill domain

| ID | Task | User stories | Depends on | Priority |
|---|---|---|---|---|
| T-025 | Define order, order-item, add-on, payment, bill, order-event, and status-transition models. | US-014, US-016, US-020 | T-004, T-007, T-008 | P0 |
| T-026 | Implement a single order-creation service used by WhatsApp, table QR, counter, and future agent tools. | US-014, US-034, US-042 | T-021, T-025 | P0 |
| T-027 | Implement quote calculation for subtotal, add-ons, PB1, delivery fee, pickup, and total using outlet settings. | US-011, US-012, US-019 | T-007, T-018, T-025 | P0 |
| T-028 | Implement confirmation-time stock recheck and atomic order creation; return item-level sold-out errors with replacement/remove options. | US-011, US-014 | T-021, T-026, T-027 | P0 |
| T-029 | Implement duplicate-safe order creation using message/request idempotency keys. | US-014, US-037 | T-026, T-028 | P0 |
| T-030 | Implement order and payment status machines for online, pay-first dine-in, open-bill dine-in, takeaway, and walk-in orders. | US-016, US-020 | T-025, T-027 | P0 |
| T-031 | Implement status transition validation and immutable order event history with actor, timestamp, and reason where required. | US-004, US-016 | T-008, T-030 | P0 |
| T-032 | Implement cancellation and paid-order reversal workflows, including stock return versus waste behavior and refund ledger hooks. | US-004, US-021 | T-020, T-030, T-031 | P0 |
| T-033 | Implement open bills per table or guest name, one open bill per table, order attachment, running total, duration, and full-bill close. | US-020 | T-025, T-027, T-030 | P0 |
| T-034 | Implement configurable unpaid-order timeout, screenshot timer pause, automatic cancellation, stock reversal, and customer notification. | US-015, US-021 | T-030, T-032, T-047 | P0 |
| T-035 | Add concurrency and transition tests for last-stock orders, invalid status changes, open-bill uniqueness, and mode changes preserving existing order flow. | US-014, US-016, US-020 | T-028–T-034 | P0 |

## Wave 4 — Payments, cashier shifts, ledger, and reports

| ID | Task | User stories | Depends on | Priority |
|---|---|---|---|---|
| T-036 | Implement QRIS payment instruction message with outlet QRIS image, exact total, and screenshot request. | US-017 | T-014, T-027 | P0 |
| T-037 | Implement payment screenshot attachment, staff payment-review queue, merchant-account confirmation, and paid action. | US-017 | T-036, T-030 | P0 |
| T-038 | Implement cash payment capture, payment-method validation, amount received, change due, and online cash restriction. | US-018 | T-025, T-027 | P0 |
| T-039 | Implement cashier shift open/close, starting cash, one active shift per drawer, and payment/refund linkage. | US-018 | T-038 | P0 |
| T-040 | Implement blind end-of-shift cash count, expected-cash calculation, difference, actor tracking, and shortage/surplus ledger entries. | US-018, US-030 | T-039 | P0 |
| T-041 | Implement append-only ledger posting for revenue, PB1, delivery fee, cash/QRIS payment, refund, expense, cash difference, and reversal. | US-019, US-030 | T-008, T-027, T-032, T-037–T-040 | P0 |
| T-042 | Implement owner-only manual expense entry with outlet, amount, description, date, and actor. | US-031 | T-006, T-041 | P0 |
| T-043 | Implement daily, weekly, monthly cashflow summaries and trends per outlet and across outlets, using outlet-local day boundaries. | US-032 | T-041, T-042, T-007 | P0 |
| T-044 | Add financial integrity tests ensuring ledger values are created only at confirmed payment and cannot be edited/deleted. | US-018–US-032 | T-040–T-043 | P0 |

## Wave 5 — WhatsApp integration and deterministic flows

| ID | Task | User stories | Depends on | Priority |
|---|---|---|---|---|
| T-045 | Configure Meta WhatsApp Cloud API/BSP credentials, webhook verification, signature validation, and outlet-number mapping. | US-002, US-036 | T-011 | P0 |
| T-046 | Implement inbound webhook persistence and RabbitMQ publishing with immediate acknowledgement. | US-036 | T-045, T-008 | P0 |
| T-047 | Implement outbound WhatsApp worker, retry policy, failure handling, and dead-letter visibility. | US-015, US-036 | T-046 | P0 |
| T-048 | Implement processed-message store and idempotent worker behavior for webhook retries and RabbitMQ redelivery. | US-037 | T-046 | P0 |
| T-049 | Implement conversation state for main menu, active order, active reservation, and safe restart/recovery behavior. | US-009–US-011, US-023 | T-046, T-048 | P0 |
| T-050 | Implement main menu buttons: Pesan, Rekomendasi, and conditional Reservasi. | US-009 | T-049 | P0 |
| T-051 | Implement catalog sync for item metadata, photos, outlet prices, active state, and unavailable/sold-out state. | US-008, US-010 | T-016–T-018, T-022, T-047 | P0 |
| T-052 | Implement catalog cart intake and post-cart add-on collection through reply buttons/list messages. | US-010, US-011 | T-017, T-049, T-051 | P0 |
| T-053 | Implement WhatsApp order summary, pickup/delivery selection, address capture, explicit confirmation, and order creation call. | US-011, US-012, US-014 | T-026–T-029, T-049, T-052 | P0 |
| T-054 | Implement table QR generation with outlet number, table identifier, and optional rotating token validation. | US-013 | T-011, T-045 | P0 |
| T-055 | Implement order confirmation, status notifications, shared notification templates, and approved-template selection outside the 24-hour window. | US-015, US-025 | T-047, T-053 | P0 |
| T-056 | Add end-to-end WhatsApp tests for online, table QR, pickup, delivery, add-ons, sold-out confirmation, duplicate messages, and template fallback. | US-009–US-015, US-037 | T-048–T-055 | P0 |

## Wave 6 — Reservations and tables

| ID | Task | User stories | Depends on | Priority |
|---|---|---|---|---|
| T-057 | Implement table CRUD, capacity, area, bookable hours, duration, booking window, party limit, reminder time, and cancellation cutoff. | US-022 | T-011, T-025 | P0 |
| T-058 | Implement timezone-aware availability calculation and smallest-fitting-table assignment. | US-022, US-023 | T-007, T-057 | P0 |
| T-059 | Add database-level exclusion/locking rule preventing overlapping reservations, including concurrent requests. | US-024 | T-057, T-058 | P0 |
| T-060 | Implement structured WhatsApp reservation flow: party size, date, available time, review, and confirmation. | US-023 | T-049, T-058, T-059 | P0 |
| T-061 | Implement reservation confirmation, reminder scheduling, cancellation, and reschedule cutoff enforcement. | US-025 | T-055, T-060 | P0 |
| T-062 | Implement staff reservation board with phone/in-person booking, table reassignment, seated/completed/cancelled/no-show states, and event audit. | US-026 | T-006, T-057, T-060 | P0 |
| T-063 | Implement walk-in table occupancy and availability blocking. | US-027 | T-057, T-058, T-062 | P0 |
| T-064 | Implement 15-minute post-booking hold, automatic no-show, table release, and seated-before-deadline behavior. | US-027 | T-061, T-062 | P0 |
| T-065 | Add reservation tests for capacity limits, timezone display, double-booking, reminders, cutoff, walk-ins, reassignment, and no-show release. | US-022–US-027 | T-057–T-064 | P0 |

## Wave 7 — Admin application and recommendations

| ID | Task | User stories | Depends on | Priority |
|---|---|---|---|---|
| T-066 | Build owner onboarding, outlet settings, staff management, QRIS upload, menu, add-on, recipe, and price screens. | US-001–US-006, US-017, US-019 | T-010–T-019 | P0 |
| T-067 | Build staff counter order screen with dine-in, takeaway, walk-in, add-ons, table selection, payment, and order submission. | US-034 | T-026–T-030, T-038 | P0 |
| T-068 | Build order board with payment review, lifecycle actions, cancellation/reversal, and open-bills view. | US-016–US-021 | T-030–T-044 | P0 |
| T-069 | Build stock, stock movement, low-stock, and sold-out screens. | US-006, US-007 | T-020–T-023 | P0 |
| T-070 | Build reservation/table view and cashier shift screens. | US-018, US-026, US-027 | T-039, T-062–T-064 | P0 |
| T-071 | Build owner dashboard for outlet-level and combined sales, cashflow, PB1, payment method, and stock summaries. | US-032, US-033 | T-041–T-043 | P0 |
| T-072 | Build role-aware navigation and responsive layouts for 360 px mobile width through desktop. | US-003, US-033, US-035 | T-006, T-066–T-071 | P0 |
| T-073 | Implement owner picks and tags, outlet best-seller query for the last 30 days, sold-out filtering, de-duplication, and 30-item limit. | US-028 | T-016, T-022, T-041 | P0 |
| T-074 | Implement WhatsApp recommendation product messages and add-to-cart handoff. | US-029 | T-051, T-073, T-052 | P0 |
| T-075 | Add frontend accessibility, responsive, permission, and critical-flow tests. | US-033–US-035 | T-066–T-074 | P0 |

## Wave 8 — Membership, compliance, and MVP hardening

| ID | Task | User stories | Depends on | Priority |
|---|---|---|---|---|
| T-076 | Implement customer/contact, consent, privacy-notice link, and business-wide membership state across outlets. | US-040 | T-004, T-045, T-049 | P0 |
| T-077 | Implement WhatsApp opt-out flow and delete/anonymize personal data without changing orders, ledger, or stock history. | US-041 | T-076, T-041 | P0 |
| T-078 | Ensure personal data is absent from append-only ledger and stock tables; add automated privacy regression tests. | US-040, US-041 | T-077 | P0 |
| T-079 | Provision Indonesia-region database, backup, object storage, and payment-screenshot storage. | US-039 | T-003, T-014 | P0 |
| T-080 | Add security hardening: secret management, token expiry, webhook verification, upload validation, rate limiting, and audit-log protection. | US-003, US-036, US-038, US-039 | T-006, T-008, T-014, T-045 | P0 |
| T-081 | Add queue metrics, structured logs, correlation IDs, retry/DLQ dashboards, and alerts for failed messages/catalog updates. | US-008, US-036, US-037 | T-047, T-048 | P0 |
| T-082 | Run performance, concurrency, tenant-isolation, backup-restore, and failure-recovery tests against MVP acceptance criteria. | US-014, US-024, US-030, US-037–US-039 | T-015, T-035, T-044, T-056, T-065, T-075, T-078–T-081 | P0 |
| T-083 | Execute full UAT with owner, cashier/waiter, and customer scenarios; triage defects and produce release checklist. | All MVP stories | T-082 | P0 |
| T-084 | Create Meta template library and submit order-update, reservation-confirmation, and reservation-reminder templates early enough for approval. | US-015, US-025 | T-055 | P0 |

## MVP release gates

The MVP is ready for release only when:

1. T-083 is complete and all MVP acceptance criteria pass.
2. An online WhatsApp order, table-QR order, and counter order use the same order service and produce correct stock, payment, and ledger outcomes.
3. Pay-first and open-bill outlets both work, including payment restrictions and existing-order behavior after a mode change.
4. Reservation concurrency, 15-minute no-show release, and timezone behavior pass.
5. Duplicate webhook delivery cannot create duplicate orders, stock movements, or ledger entries.
6. Cross-tenant access tests, Indonesia data-residency checks, and append-only audit checks pass.
7. Approved WhatsApp templates are available for every required outside-window notification, or the release is explicitly blocked with a documented Meta dependency.

## Phase 2 — Agent layer

| ID | Task | User stories | Depends on | Priority |
|---|---|---|---|---|
| T-085 | Define versioned deterministic tool contracts for quote, order creation, reservation creation, menu lookup, stock lookup, sales lookup, and FAQ data. | US-042–US-045 | T-026, T-058, T-082 | P0 |
| T-086 | Add LangChain agent gateway, conversation memory boundaries, prompt/version management, timeout, fallback, and error handling. | US-042–US-045 | T-085 | P0 |
| T-087 | Implement free-text order parsing, structured summary, clarification questions, explicit confirmation gate, and handoff to T-026. | US-042 | T-085, T-086 | P0 |
| T-088 | Implement free-text reservation parsing, detail confirmation, availability lookup, and handoff to T-060. | US-043 | T-058–T-060, T-085, T-086 | P0 |
| T-089 | Implement conversational recommendations, FAQ handling, and advisory upsell without direct cart/order mutation. | US-044 | T-085, T-086 | P1 |
| T-090 | Implement demand forecast, restock suggestion, and unusual-cashflow detection views for owners. | US-045 | T-043, T-085, T-086 | P1 |
| T-091 | Enforce agent guardrails: no direct database writes, no stock-change tool, explicit customer confirmation, actor=`agent`, and tool-call audit trail. | US-042–US-045 | T-085–T-090 | P0 |
| T-092 | Build agent evaluation set for ambiguous orders, unavailable items, incorrect quantities, timezone reservations, prompt injection, and duplicate confirmations. | US-042–US-045 | T-087–T-091 | P0 |
| T-093 | Run shadow/canary rollout with deterministic fallback and monitor tool errors, confirmation rate, and unsafe-action attempts. | US-042–US-045 | T-092 | P1 |

## Phase 3 — Scale and expansion

| ID | Task | User stories | Depends on | Priority |
|---|---|---|---|---|
| T-094 | Add staff shifts, attendance records, permissions, and reporting. | US-046 | MVP auth and staff foundation | P1 |
| T-095 | Add demand-based schedule suggestions with owner approval workflow. | US-046 | T-094, T-090 | P1 |
| T-096 | Integrate dynamic QRIS/payment gateway, webhook validation, reconciliation, and idempotent payment confirmation. | US-047 | MVP payment domain, T-081 | P1 |
| T-097 | Add dropshipper tenant type, non-physical outlet behavior, and dropshipper-specific onboarding. | US-048 | T-010–T-013 | P2 |
| T-098 | Implement marketplace connector framework and Shopee integration. | US-048 | T-097 | P2 |
| T-099 | Implement Tokopedia and TikTok Shop integrations, sync monitoring, and conflict resolution. | US-048 | T-098 | P2 |

## Critical path

The shortest dependency path to a usable MVP is:

`T-001 → T-004 → T-005/T-006 → T-016–T-022 → T-025–T-031 → T-036–T-044 → T-045–T-056 → T-057–T-065 → T-066–T-075 → T-076–T-084`

The following work can proceed in parallel once the foundation is ready:

- Tenant/staff administration: T-010–T-015
- Menu and inventory: T-016–T-024
- Admin shell and screens: T-066–T-072
- WhatsApp infrastructure: T-045–T-049
- Reservation domain: T-057–T-059

## Suggested issue labels

Use these labels when importing the backlog:

- `phase:mvp`, `phase:p2`, `phase:p3`
- `domain:platform`, `domain:auth`, `domain:menu`, `domain:inventory`, `domain:orders`, `domain:payments`, `domain:whatsapp`, `domain:reservations`, `domain:admin`, `domain:agent`
- `type:backend`, `type:frontend`, `type:worker`, `type:database`, `type:qa`, `type:devops`
- `risk:financial`, `risk:privacy`, `risk:concurrency`, `risk:external-api`
