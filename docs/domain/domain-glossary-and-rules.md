# Domain glossary, business rules, and enums (T-001)

Status: **draft v1 — 2026-11-17**. Baseline: PRD v0.13, US-001–US-056.
This document is the single reference for names, enums, and rules used by the database (T-004), API (T-002), and admin app. When code and this document disagree, fix one of them in the same change.

Decisions recorded from the product owner on 2026-11-17:

| Topic | Decision |
|---|---|
| Rupiah rounding | **No rounding of totals.** Totals are not rounded to Rp100/Rp500/Rp1.000; the customer pays the exact total. All amounts are whole rupiah (integers). |
| PB1 rate | **Not decided yet.** PB1 is a per-outlet setting (on/off + rate). New outlets start with PB1 **off**; the owner turns it on and sets the rate. No rate is hardcoded anywhere. |
| Default time zone | **WIB (`Asia/Jakarta`).** New outlets default to WIB; the owner can change to WITA or WIT. |

## 1. Glossary

| Term (UI, Bahasa Indonesia) | Code name | Meaning |
|---|---|---|
| Bisnis | `tenant` | A business that subscribes to the platform. Type: restaurant or cafe (dropshipper is Phase 3). |
| Outlet | `outlet` | One physical branch of a tenant. Owns prices, PB1 setting, payment mode, QRIS, WhatsApp number, cash drawers, tables, stock, reservation settings, time zone. |
| Owner | `owner` | Tenant administrator. Sees all outlets of the tenant. |
| Staf | `staff` | Invited user assigned to one or more outlets. Sees only assigned outlets. |
| Menu / item | `product` | A menu item, shared across the tenant's outlets. Price is per outlet. |
| Add-on | `addon_group`, `addon_option` | Group (e.g. Ukuran) with up to 10 options; single or multiple choice; required or optional. Options can add price and recipe changes. |
| Harga outlet | `outlet_price` | Price of a product or add-on option at one outlet. |
| Bahan | `stock_item` | An ingredient or packaging item tracked per outlet in a base unit. |
| Resep | `recipe_item` | Ingredient quantity needed for one portion of a product (or for an add-on option). |
| Pergerakan stok | `stock_movement` | Append-only change to stock: sale, sale reversal, restock, waste, adjustment. Stock level = sum of movements. |
| Sold out / habis | derived | A product is unavailable at an outlet when any ingredient is below one portion. |
| Order | `order` | One order from a channel. Has an order status and a separate payment status. |
| Kanal | `order_channel` | `whatsapp_online`, `whatsapp_table`, `counter`. |
| Tipe order | `order_type` | `delivery`, `pickup` (online); `dine_in`, `takeaway` (counter, table). |
| Open bill | `bill` | A running bill for a table or guest name at open-bill outlets; paid in full once. |
| Mode pembayaran dine-in | `payment_mode` | Outlet setting: `pay_first` or `open_bill`. Online orders are always pay first. |
| Bukti bayar | `payment_proof` | Customer's QRIS payment screenshot, reviewed by staff. |
| Cash drawer | `cash_drawer` | A physical cash drawer at an outlet (e.g. "Kasir depan", "Bar"; shown as "Drawer 1 · Kasir depan"). Every outlet starts with one. |
| Shift kasir | `cashier_shift` | Period a drawer is in use: starting cash → blind count. Not staff scheduling. |
| Ledger | `ledger_entry` | Append-only financial record per outlet. Corrections are new reversal entries. |
| Pengeluaran | ledger entry type `expense` | Manual cash expense logged by the owner. |
| PB1 | `pb1` | Regional restaurant tax (PBJT F&B, Law No. 1/2022), set per outlet, up to 10%. |
| Meja | `table` | A table at an outlet with seat capacity and optional area. |
| Reservasi | `reservation` | A table booking (or a walk-in occupancy) for a time range. |
| Kontak WhatsApp | `whatsapp_contact` | A customer identified by phone number within a tenant. |
| Membership / consent | `customer_consent` | Customer's consent for the tenant to keep their data. |
| Tablet absensi | `attendance_device` | A tablet paired to one outlet, the only place staff clock in/out. |
| Catatan kehadiran | `attendance_record` | One clock-in/clock-out pair with selfies. |
| Aktor | `actor_type` | Who did an action: `user`, `system`, `agent`, `device`. |

## 2. Money, tax, and rounding

- **Currency:** IDR only. Stored as `bigint` whole rupiah. No decimals anywhere in money columns or API payloads.
- **Display:** `Rp` + thousands separator `.` (e.g. `Rp92.400`), as in the wireframes. Formatting only happens at the edge (UI, WhatsApp text).
- **No rounding of totals:** the customer pays the exact total. Cash change = amount received − total, exact to the rupiah.
- **PB1 setting per outlet:** `pb1_enabled` (default `false`) and `pb1_rate_bps` (rate in basis points; 1000 = 10%; allowed 1–1000). Rate is required when enabled.
- **PB1 calculation:** `pb1 = round_half_up(subtotal × rate_bps / 10000)`, computed with integer arithmetic. The base is the subtotal including add-ons and excluding the delivery fee (FR11.5, US-019). Rounding to the nearest whole rupiah is only needed because a percentage of an integer can produce a fraction; it is not cash rounding.
- **Totals:** `total = subtotal + pb1 + delivery_fee`.
- **PB1 snapshot:** the rate used is stored on each order (and bill) so later setting changes never change past orders.
- **Open question (still TBD in PRD §13):** on open bills, is PB1 calculated per order and summed, or once on the bill subtotal at close? The schema stores PB1 on both orders and bills so either rule can be implemented. **Proposed default until decided:** once on the bill subtotal at close (one rounding, matches what the customer sees on the bill).
- **Ledger posting** (only when payment is confirmed): separate entries for menu revenue, PB1, and delivery fee, each tagged with outlet and payment method (AC3.2).

## 3. Time and time zones

- **Default:** `Asia/Jakarta` (WIB). Allowed outlet time zones: `Asia/Jakarta` (WIB), `Asia/Makassar` (WITA), `Asia/Jayapura` (WIT).
- **Storage:** all instants are `timestamptz` (UTC internally). Local-only values (opening hours, bookable hours) are `time` in the outlet's zone.
- **Display:** always in the outlet's zone with its label, e.g. `19:00 WITA` (AC9.9).
- **Day boundaries** for reports, attendance, and busyness use the outlet's local midnight, never UTC or the server zone (AC3.4, AC5.5).
- **Cross-outlet reports** sum per-outlet local days (1 Nov at a WIB outlet and 1 Nov at a WITA outlet are both "1 Nov").
- Indonesia has no daylight saving time, so offsets are fixed (+7, +8, +9), but code still uses IANA zone names.

## 4. Enums

Enum values are lower snake case in the database and API; UI labels are Bahasa Indonesia.

| Enum | Values | Notes |
|---|---|---|
| `tenant_type` | `restaurant`, `cafe` | `dropshipper` added in Phase 3 (T-097). |
| `user_role` | `owner`, `staff` | Also the `app_role` JWT claim (T-113). |
| `payment_mode` | `pay_first`, `open_bill` | Dine-in only. Online orders always pay first. |
| `order_channel` | `whatsapp_online`, `whatsapp_table`, `counter` | FR2.8. |
| `order_type` | `delivery`, `pickup`, `dine_in`, `takeaway` | Online: delivery/pickup. Table QR: dine_in. Counter: dine_in/takeaway. |
| `order_status` | `pending_payment`, `confirmed`, `preparing`, `ready`, `out_for_delivery`, `served`, `completed`, `cancelled` | Flows in §5. |
| `payment_status` | `unpaid`, `proof_submitted`, `paid`, `refunded` | `refunded` only through a reversal. |
| `payment_method` | `cash`, `qris` | Online orders: QRIS only. |
| `payment_proof_status` | `pending`, `accepted`, `rejected` | Rejection needs a reason. |
| `bill_status` | `open`, `closed`, `voided` | `voided`: every order on the bill was cancelled. |
| `cashier_shift_status` | `open`, `closed` | One open shift per drawer. |
| `stock_unit` | `g`, `ml`, `pcs` | Base units. kg/L are display conversions (T-007). |
| `stock_movement_type` | `sale`, `sale_reversal`, `restock`, `waste`, `adjustment` | Signed quantity. `adjustment` can be + or −. |
| `ledger_entry_type` | `revenue`, `pb1`, `delivery_fee`, `refund`, `expense`, `cash_shortage`, `cash_surplus`, `reversal` | Signed amount (+ cash in, − cash out). |
| `addon_selection` | `single`, `multiple` | Plus `is_required` flag. |
| `reservation_status` | `booked`, `seated`, `completed`, `cancelled`, `no_show` | |
| `reservation_source` | `whatsapp`, `phone`, `in_person`, `walk_in` | `walk_in` = table occupancy without booking (FR9.7). |
| `consent_status` | `granted`, `declined`, `withdrawn` | |
| `message_direction` | `inbound`, `outbound` | |
| `scheduled_job_type` | `unpaid_timeout`, `reservation_reminder`, `no_show_release`, `anonymize_declined`, `attendance_flag`, `attendance_photo_purge` | Appendix A.4. |
| `scheduled_job_status` | `pending`, `enqueued`, `done`, `cancelled`, `failed` | |
| `actor_type` | `user`, `system`, `agent`, `device` | `device` = attendance tablet. |
| `attendance_record_status` | `open`, `closed`, `needs_correction`, `corrected` | |
| `attendance_event_type` | `clock_in`, `clock_out`, `flag`, `correction` | |
| `busyness_level` (computed, not stored) | `ramai`, `normal`, `sepi` | Thresholds are placeholders (T-123). |

## 5. Order and payment flows

Allowed status transitions. Anything not listed is refused (AC10.1). `→ cancelled` is allowed from any non-final status before completion (unpaid: stock returned; paid: requires reversal with reason).

| Flow | When | Statuses |
|---|---|---|
| Online (pay first) | channel `whatsapp_online` | `pending_payment` → `confirmed` → `preparing` → `ready` → (`out_for_delivery` if delivery) → `completed` |
| Dine-in, pay first | outlet `pay_first`, type `dine_in` | `pending_payment` → `confirmed` → `preparing` → `ready` → `completed` |
| Dine-in, open bill | outlet `open_bill`, type `dine_in` | `confirmed` → `preparing` → `ready` → `served` → `completed` (when the bill is paid) |
| Takeaway, counter | type `takeaway` | `confirmed` → `preparing` → `ready` → `completed` (only once paid) |

Rules:

1. The flow is fixed when the order is created; changing the outlet's payment mode later never changes existing orders (AC10.10).
2. `pending_payment` orders cannot move to `preparing` until paid.
3. No order can become `completed` while `payment_status` ≠ `paid`.
4. Payment status: `unpaid` → `proof_submitted` (screenshot received; pauses the unpaid timer) → `paid` (staff confirmed in the merchant account) → `refunded` (reversal only).
5. Rejecting a proof (reason required) cancels the order immediately; payment stays `unpaid`; stock returns with a `sale_reversal` movement; no ledger entry.
6. Unpaid pay-first orders are cancelled after the outlet's `unpaid_timeout_minutes`, unless a proof was submitted.
7. Reversing a paid order requires a reason, posts a `refund` ledger entry, and returns stock (not yet prepared) or records `waste` (already prepared). The money is returned outside the system.
8. Every status change writes an `order_event` with old/new status, actor, time, and reason when required.

## 6. Stock rules

- Stock is never edited directly; level = sum of movements per outlet and stock item.
- Order creation checks and deducts all ingredients (items + add-ons) in **one transaction** with row locks, so stock never goes below zero and two customers cannot take the last portion (FR4.6, AC2.10).
- A product is sold out at an outlet if any ingredient's stock < one portion's requirement; same for add-on options (FR4.7).
- Low-stock warning when stock < the item's per-outlet threshold (FR4.3).
- Every movement records actor and time; movements are append-only.

## 7. Cash and shifts

- Each new outlet gets one drawer ("Kasir depan"). One open shift per drawer. Cash payments require an open shift and are linked to it.
- Blind count: staff enter counted cash before seeing expected cash. Expected = starting cash + cash received − cash paid out. Difference posts `cash_shortage` or `cash_surplus` to the ledger.

## 8. Reservations

- Tables have seat capacity and optional area. Booking assigns the smallest free table that fits.
- No overlapping active bookings (`booked`, `seated`) on one table — enforced by a database exclusion constraint (FR9.3).
- Hold: 15 minutes after booking time, then automatic `no_show` and table released (FR9.10).
- Settings per outlet: enabled, bookable hours, default duration, booking window (days ahead), max party size, reminder offset, cancellation cutoff.
- Walk-in occupancy is a reservation with source `walk_in` and status `seated`, so it blocks overlapping bookings (FR9.7).

## 9. Access and roles

Permission matrix as in PRD FR1.5. Key points:

- Staff accounts are invite-only (no public sign-up).
- Staff see only assigned outlets; checked live in the database on each request, not from token claims.
- Owner-only: menu/prices/recipes/recommendations, expenses and reports, outlet/WhatsApp/table/QRIS/PB1/staff settings, attendance report and corrections, tablet pairing.
- Attendance tablet: device session scoped to one outlet; can only list that outlet's staff and record clock in/out with a selfie.

## 10. Customer data

- Personal data lives only in customer tables (`whatsapp_contacts`, addresses, messages); never copied into ledger or stock tables (FR12.4).
- Consent is per tenant, asked once on first contact with any outlet of that tenant.
- Withdrawn or declined consent → anonymize the contact; orders and ledger stay intact.

## 11. Open items

| # | Item | Owner | Blocks |
|---|---|---|---|
| 1 | PB1 rate(s) per outlet | Product owner | Nothing in code (setting); needed before pilot data entry |
| 2 | PB1 on open bills: per order vs once per bill | Product owner | T-033 (open bills), T-041 (ledger posting) |
| 3 | Busy/quiet/crowd thresholds | Development (T-123) | T-123 |
| 4 | Who delivers (outlet staff vs courier) | Product owner | T-053 copy only |
| 5 | Cross-border data transfer basis | Legal (T-108) | Any real merchant data |
