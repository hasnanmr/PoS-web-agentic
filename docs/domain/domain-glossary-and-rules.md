# Domain glossary, business rules, and enums (T-001)

Status: **draft v1 — 2026-11-17**. Baseline: PRD v0.14, US-001–US-061.
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
| Admin platform | — (CLI only) | Operator of the platform. Invites every new owner (decision 2026-11-17). Not a tenant user; no screen. |
| Owner | `owner` | Tenant administrator. Sees all outlets of the tenant. Before creating the business the invited owner has app role `owner_pending`. |
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
| Pengeluaran | ledger entry type `expense` | Money paid out: a direct expense logged by the owner, or a supplier payment for a purchase order. |
| Supplier | `supplier` | A business the tenant buys from (name, optional phone, note). Tenant-level. |
| Purchase order (PO) | `purchase_order` | An order to a supplier for one outlet, numbered per outlet (`PO-A-0012`), with lines, a payment term, a goods status, and a payment status. |
| Bayar mundur / tempo | payment term `pay_later` | Goods first; the outlet owes the supplier until the due date and may pay in instalments. |
| Bayar di muka | payment term `pay_in_advance` | Paid when ordered; goods arrive later. |
| Hutang supplier | derived | Amount still owed on pay-later POs. Shown in reports, never posted to the ledger until paid. |
| Penerimaan barang | `purchase_order_receipt` | One delivery against a PO; ingredient lines add stock through restock movements. |
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
- **Display:** `Rp`, a space, and `.` as thousands separator (e.g. `Rp 92.400`, negative `− Rp 350.000`), as in the wireframes. Formatting only happens at the edge (UI, WhatsApp text); `app.core.money.format_rupiah`.
- **Quantities:** stored in base units (g, ml, pcs); shown in the item's display unit as in the stock wireframe (`0,8 L`, `0,4 kg`, `180 g`), comma as decimal separator; `app.core.units.format_quantity`.
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
| `user_role` | `owner`, `staff` | Stored role. The `app_role` JWT claim (T-113) is `owner`, `staff`, or `owner_pending` (invited owner, no tenant yet). |
| `payment_mode` | `pay_first`, `open_bill` | Dine-in only. Online orders always pay first. |
| `order_channel` | `whatsapp_online`, `whatsapp_table`, `counter` | FR2.8. |
| `order_type` | `delivery`, `pickup`, `dine_in`, `takeaway` | Online: delivery/pickup. Table QR: dine_in. Counter: dine_in/takeaway. |
| `order_status` | `pending_payment`, `confirmed`, `preparing`, `ready`, `out_for_delivery`, `served`, `completed`, `cancelled` | Flows in §5. |
| `payment_status` | `unpaid`, `proof_submitted`, `paid`, `refunded` | `refunded` only through a reversal. |
| `payment_method` | `cash`, `qris`, `transfer` (T-125) | Online orders: QRIS only. `transfer` only for supplier payments. |
| `payment_proof_status` | `pending`, `accepted`, `rejected` | Rejection needs a reason. |
| `bill_status` | `open`, `closed`, `voided` | `voided`: every order on the bill was cancelled. |
| `cashier_shift_status` | `open`, `closed` | One open shift per drawer. |
| `stock_unit` | `g`, `ml`, `pcs` | Base units. kg/L are display conversions (T-007). |
| `stock_movement_type` | `sale`, `sale_reversal`, `restock`, `waste`, `adjustment` | Signed quantity. `adjustment` can be + or −. |
| `ledger_entry_type` | `revenue`, `pb1`, `delivery_fee`, `refund`, `expense`, `cash_shortage`, `cash_surplus`, `reversal` | Signed amount (+ cash in, − cash out). |
| `po_payment_term` (T-125) | `pay_later`, `pay_in_advance` | Fixed when the PO is created. |
| `po_status` (T-125) | `open`, `difference_found`, `closed`, `cancelled` | `open` until goods are checked; `difference_found` while a line is short; `closed` by staff when every line matches, or only by the owner with a note; `cancelled` only with no payment and no goods. |
| `po_payment_status` (T-125) | `unpaid`, `partially_paid`, `paid` | From payments; never above the PO total. Overdue = a closed pay-later PO (its payment reminder is showing, FR3.7), not fully paid, past the due date (outlet time zone); an open PO past its due date is not overdue yet. |
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

## 7a. Purchase orders (PRD v0.14, FR3.5–FR3.10, FR4.10)

- Scheme 1, pay later: open → goods arrive and are checked against PO quantities → PO closed → payment reminder on the owner dashboard until paid.
- Scheme 2, pay in advance: open → payment request on the owner dashboard → paid → goods arrive and are checked → PO closed (not allowed while unpaid).
- Who: owner, or staff for an assigned outlet, open POs (no approval; creator recorded) and cross-check goods; staff close a matching PO. Suppliers, payments, cancellation, close-with-difference (note required), debt, and dashboard reminders are owner-only.
- Cash basis: opening, checking, or closing a PO never posts to the ledger; each supplier payment posts one `expense` entry (negative amount) on the payment date with method, PO number, and supplier.
- Pay later: payments may be split; the sum never exceeds the PO total. Pay in advance: the full payment is recorded before goods arrive; the PO then waits for goods.
- A cash supplier payment may be taken from an open shift's drawer; it is then cash paid out in that shift's expected cash (§7).
- Goods check: owner or assigned staff enter received vs ordered per line; quantity never above the ordered quantity; a short line keeps the PO in `difference_found` (staff can't close; listed on the owner dashboard) until the rest arrives or the owner closes it with a note (pay later: amount owed = received × unit price, decided; refunds for short pay-in-advance POs are out of the MVP); ingredient lines create `restock` movements (base units) referencing the PO; free-text lines add no stock.
- Cancel: only with no payment and no receipt, reason required. Payments and receipts are append-only.
- Open (PRD §13): short deliveries and supplier returns, separate PPN, approvals and WhatsApp reminders.

## 8. Reservations

- Tables have seat capacity and optional area. Booking assigns the smallest free table that fits.
- No overlapping active bookings (`booked`, `seated`) on one table — enforced by a database exclusion constraint (FR9.3).
- Hold: 15 minutes after booking time, then automatic `no_show` and table released (FR9.10).
- Settings per outlet: enabled, bookable hours, default duration, booking window (days ahead), max party size, reminder offset, cancellation cutoff.
- Walk-in occupancy is a reservation with source `walk_in` and status `seated`, so it blocks overlapping bookings (FR9.7).

## 9. Access and roles

Permission matrix as in PRD FR1.5. Key points:

- Accounts are invite-only (no public sign-up): the platform admin invites owners; owners invite staff.
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
| 6 | Detailed wireframe for the Pengeluaran menu (direct expenses only since PRD v0.15; POs moved to the Dashboard tab PO & Supplier, drawn as O15–O17) | Design | Pengeluaran screen; until then the menu opens O9 |
| 5 | Cross-border data transfer basis | Legal (T-108) | Any real merchant data |
