# Screen → endpoint map (wireframe contract)

Status: **draft v1 — 2026-11-17**. Source: `design/SME-POS-Wireframe.figcraft` (screens O1–O14, S1–S9, M1–M6, K0–K4) and `design/WIREFRAME-TRACEABILITY.md`.

**Rule:** every backend endpoint used by the admin app or the attendance tablet must serve exactly what its wireframe screen shows and does: the same fields, filters, actions, and error states. When a screen needs data, add it to the endpoint listed here; when an endpoint is added or changed, update this table in the same change. A screen that is not drawn gets no endpoint until it is designed (or the product owner approves it).

Conventions (from `api-boundaries.md`): base `/api/v1`; `owner/*` = owner only, `ops/*` = owner + staff (assigned outlets only), `device/*` = attendance tablet session. Money in integer rupiah, enums as in T-001, times with offset plus `outlet.timezone`. Mobile screens (M1–M6) use the **same endpoints** as their desktop screens; only the layout changes.

Every list/action response for an order includes **`allowed_actions`**, computed by the server from the order's flow (channel, payment mode, status, payment status). The UI only renders buttons from this list (S2 note: "Tombol aksi hanya menawarkan transisi valid").

## Shared

| Purpose | Method & path | Notes |
|---|---|---|
| Current user, role, assigned outlets, outlet switcher | `GET /me` ✅ implemented | `{user, role: owner\|staff\|owner_pending, onboarding_required, tenant, outlets:[{id,name,timezone,order_prefix,payment_mode}]}`. Drives the sidebar (Owner vs Staff) and "Outlet: … ▾". `owner_pending` (invited owner without a business) → show O1 "Buat profil bisnis". |
| Login | Supabase Auth (not our API) | O1 errors: deactivated → `account_inactive`; never invited → `account_not_invited` (both from the token hook; public sign-up disabled). Owners are invited by the platform admin CLI (`app.cli invite-owner`), staff by the owner (O4). |

## Owner screens

### O1 · Login & Buat Bisnis (T-006, T-010, T-011, T-024)

| Action | Endpoint | Fields (as on screen) |
|---|---|---|
| Create business + first outlet + sample menu | `POST /owner/onboarding` ✅ implemented (sample menu: T-024, Wave 2) | `business:{name, type: cafe\|restaurant}`, `outlet:{name, timezone (default Asia/Jakarta), address, whatsapp_phone}`. Dropshipper shown disabled ("Segera, Phase 3"), so not accepted. Seeds the sample menu (FR2.12). |

### O2 · Dashboard + keramaian (T-071, T-123, T-124)

| Card | Endpoint | Query / fields |
|---|---|---|
| All cards | `GET /owner/dashboard` | Query: `outlet_id` (or all), `period=today\|week\|month`, `hours=all\|busy\|quiet`. |
| KPI tiles | ↳ `kpis` | `revenue_excl_pb1` + `change_pct` vs previous period, `orders` + `cash_count` + `qris_count`, `pb1_collected`, `delivery_fee` + `delivery_orders`. |
| Peta keramaian (day × hour, 4 weeks) | ↳ `busyness_map` | `[{weekday, hour, avg_orders}]`, opening hours only, outlet time zone. Not affected by `hours`. |
| Keramaian outlet sekarang | ↳ `current_crowd` | `[{outlet_id, name, timezone, occupied_tables, total_tables, active_orders, level: ramai\|normal\|sepi}]`. Not affected by `hours`. |
| Order per jam | ↳ `orders_per_hour` | `[{hour, orders, mark: busy\|quiet\|null}]` + `busy_summary`, `quiet_summary` (hours, orders, share). |
| Stok rendah & sold out | ↳ `low_stock` | `[{stock_item, outlet, on_hand, low_threshold, unit, status: low\|out}]`. Not affected by `hours`. |
| Komposisi per kanal / Metode bayar | ↳ `channel_mix`, `payment_methods` | `[{channel, orders, share}]`, `[{method, amount, transactions}]`. |

Staff calling it → `403` (AC7.7).

### O3 · Bisnis & Outlet (T-011, T-014, T-039, T-118, T-121)

| Section | Endpoint | Fields |
|---|---|---|
| Outlet picker, + Tambah outlet | `GET /owner/outlets`, `POST /owner/outlets` ✅ | New outlet gets default drawer and reservation settings. |
| Umum + Order, pajak & pembayaran | `GET/PATCH /owner/outlets/{id}` ✅ | `name, address, timezone (WIB/WITA/WIT), whatsapp_phone, whatsapp_status, catalog_synced_at, pb1_enabled, pb1_rate_bps, payment_mode, delivery_fee, unpaid_timeout_minutes, attendance_grace_minutes`. "Simpan perubahan" sends one PATCH. `GET` also returns `opening_hours` (shown as "Sen–Min 08:00 – 22:00"). |
| Jam buka (atur per hari) | `PUT /owner/outlets/{id}/opening-hours` ✅ | `[{weekday, opens_at, closes_at}]`. |
| QRIS statis | `POST /owner/outlets/{id}/qris` (returns signed upload URL), `GET` (signed view URL + uploaded_at) | PNG/JPG, max 2 MB. |
| Cash drawer | `GET/POST /owner/outlets/{id}/drawers`, `PATCH/DELETE /owner/drawers/{id}` ✅ | `name` (max 40), `has_open_shift`; delete refused while a shift is open (`shift_open`) or for the last drawer (`last_drawer`). |
| Tablet absensi | `GET /owner/outlets/{id}/attendance-devices` (`name, last_seen_at, revoked_at`), `POST /owner/outlets/{id}/attendance-pairing-codes` → `{code (6 digits), expires_at (10 min)}`, `POST /owner/attendance-devices/{id}/revoke` | Tenggang lupa clock out = `attendance_grace_minutes` above. |

### O4 · Staf & Akses (T-012, T-013)

| Action | Endpoint | Fields |
|---|---|---|
| Staff table | `GET /owner/staff` ✅ | `[{id, display_name, email, outlets:[…], status: active\|inactive\|invited}]`. |
| Undang staf | `POST /owner/staff/invitations` ✅ | `display_name, email, outlet_ids[]`. Sends Supabase invite email. |
| Menu ⋯: Edit outlet | `PUT /owner/staff/{id}/outlets` ✅ | `outlet_ids[]`. |
| Menu ⋯: Kirim ulang undangan | `POST /owner/staff/{id}/invitations/resend` ✅ | |
| Menu ⋯: Nonaktifkan | `POST /owner/staff/{id}/deactivate` ✅ | Revokes sessions immediately. |
| Matriks akses | static in the UI (FR1.5) | No endpoint. |

### O5 · Menu, Add-on & Harga Outlet (T-016, T-017, T-018, T-051)

| Action | Endpoint | Fields |
|---|---|---|
| List with price for one outlet | `GET /owner/products?price_outlet_id=&q=&category=&status=` | `[{id, name, category, is_owner_pick, is_sample, addon_group_count, price, status: active\|sold_out\|inactive}]`. |
| + Item menu / Edit | `POST /owner/products`, `GET/PATCH /owner/products/{id}` | `name*, category, is_owner_pick, tags[], description, is_active, photo` (upload URL via `POST /owner/products/{id}/photo`). |
| Harga per outlet | `PUT /owner/products/{id}/prices` | `[{outlet_id, price}]`. |
| Grup add-on | `POST /owner/products/{id}/addon-groups`, `PATCH/DELETE /owner/addon-groups/{id}`, `PUT /owner/products/{id}/addon-groups/order` | `name, selection: single\|multiple, is_required`, options `[{name, prices:[{outlet_id, price}]}]`, max 10 options. Option availability per outlet returned (`unavailable` when ingredients run out). |
| Simpan & sync katalog | the save calls above enqueue catalog sync automatically | Response includes `catalog_sync: queued`. |
| ✕ Hapus item | `DELETE /owner/products/{id}` | Soft delete if referenced by orders. |

### O6 · Resep & Bahan (T-019, T-021, T-022)

| Tab / action | Endpoint | Fields |
|---|---|---|
| Resep menu list | `GET /owner/products?include=recipe_summary` | `ingredient_count`. |
| Resep (1 porsi) | `GET/PUT /owner/products/{id}/recipe` | `[{stock_item_id, quantity}]`, min 1 line; unit from stock item. |
| Delta resep dari add-on | `GET/PUT /owner/addon-options/{id}/recipe` | `[{stock_item_id, quantity (±)}]`. |
| Simulasi ketersediaan per outlet | `GET /owner/products/{id}/availability` | `[{outlet_id, portions_available, sold_out, limiting_stock_item}]`. |
| Daftar bahan | `GET/POST /owner/stock-items`, `PATCH /owner/stock-items/{id}` | `name, unit: g\|ml\|pcs`. |
| Threshold per outlet | `PUT /owner/stock-items/{id}/thresholds` | `[{outlet_id, low_threshold}]`. |

### O7 · Rekomendasi (T-073, T-074)

| Action | Endpoint | Fields |
|---|---|---|
| Owner's picks (all outlets) | `GET/PUT /owner/owner-picks` | Ordered `[{product_id}]` (drag to reorder). |
| Tags | `GET /owner/tags`, tags edited on the product (O5) | |
| Preview menu Rekomendasi per outlet | `GET /owner/outlets/{id}/recommendation-preview` | `picks:[{product, skipped_reason?}]`, `best_sellers:[{product, units_30d, skipped_reason?: sold_out\|duplicate}]`, max 30. Uses the same function as the WhatsApp flow. |

### O8 · Meja & Aturan Reservasi (T-054, T-057)

| Action | Endpoint | Fields |
|---|---|---|
| Daftar meja, + Meja | `GET/POST /owner/outlets/{id}/tables`, `PATCH/DELETE /owner/tables/{id}` | `name, capacity, area, is_bookable`. |
| ⭳ Unduh QR | `GET /owner/tables/{id}/qr.png` | Encodes the outlet's wa.me link with `MEJA {name} · {qr_token}`. |
| Aturan reservasi | `GET/PUT /owner/outlets/{id}/reservation-settings` | `is_enabled, bookable_from, bookable_until, default_duration_minutes, booking_window_days, max_party_size, reminder_offset_minutes, cancellation_cutoff_minutes`. Hold 15 min is fixed (shown read-only). |

### O9 · Laporan Cashflow & Pengeluaran (T-041, T-042, T-043)

The sidebar item **Pengeluaran** opens this screen until its own detailed wireframe exists (product owner, 2026-11-17); it uses the same endpoints below. Add a new section here when that wireframe arrives.

| Card / action | Endpoint | Fields |
|---|---|---|
| All cards | `GET /owner/reports/cashflow?outlet_id=&granularity=daily\|weekly\|monthly&from=&to=` | `totals:{cash_in, cash_out, net, pb1_collected}` each with `change_pct` vs the previous period of the same length; `series:[{date, cash_in, cash_out}]` (outlet-local days); `breakdown:{revenue_excl_pb1, pb1, delivery_fee, cash, qris, refunds, expenses, cash_difference}`; `expenses_by_outlet:[{outlet, amount}]` + total and count. |
| Pengeluaran terbaru / Lihat semua | `GET /owner/expenses?outlet_id=&from=&to=&cursor=` | `[{business_date, outlet, description, amount, recorded_by}]`. |
| Catat pengeluaran | `POST /owner/expenses` | `outlet_id, amount, business_date, description`. Append-only; corrections via `POST /owner/ledger-entries/{id}/reversal` with `reason`. |

### O10 · Laporan Cash Count (T-040, T-102)

| Action | Endpoint | Fields |
|---|---|---|
| Table + summary | `GET /owner/reports/cash-count?outlet_id=&drawer_id=&from=&to=` | `summary:{shifts, shifts_with_difference, total_shortage, total_surplus}`, `rows:[{opened_at, closed_at, outlet, drawer, timezone, starting_cash, expected_cash, counted_cash, difference, counted_by}]`. |
| ⭳ Ekspor CSV | same path with `Accept: text/csv` (or `?format=csv`) | Same columns. |

### O11 · Audit Log (T-031, T-101)

| Action | Endpoint | Fields |
|---|---|---|
| List | `GET /owner/audit-log?outlet_id=&actor_id=&kind=reversal,status,payment&from=&to=&cursor=` | `[{created_at (outlet tz), order_no ("#A-1034"), order_id, kind, change ("paid → refunded"), actor:{type, name, role}, reason}]`. Read-only. |

### O12 · WhatsApp Setup & Template (T-045, T-051, T-084, T-100)

| Card | Endpoint | Fields |
|---|---|---|
| Status per outlet | `GET /owner/whatsapp/outlets` | `[{outlet, business_verified, number_status, catalog_status, catalog_retry, next_step}]`. Embedded Signup actions are links returned here (T-100). |
| Template Meta | `GET /owner/whatsapp/templates` | `[{name, status: approved\|in_review\|rejected, required}]`. |
| Kesehatan antrean pesan | `GET /owner/whatsapp/queue-health` | `inbound_today, outbound_failed (dead letters), catalog_pending, duplicates_ignored`. |

### O13 · Dead-letter & Antrean Pesan (T-081, T-112)

| Action | Endpoint | Fields |
|---|---|---|
| Counters + list | `GET /owner/dead-letters?queue=&outlet_id=&reason=` | `counts:{wa.dead.q, catalog.dead.q, jobs.dead.q}`, `inbound_backlog`, `items:[{id, failed_at, queue, outlet, reason, attempts, max_attempts}]`. |
| Detail pesan | `GET /owner/dead-letters/{id}` | `queue, outlet, type, related_order_no, correlation_id, reason, attempts, first_failed_at, last_failed_at, payload` (phone masked). |
| ↻ Putar ulang | `POST /owner/dead-letters/{id}/replay` | Audited. |
| ✕ Buang | `POST /owner/dead-letters/{id}/discard` | `reason*`. Audited. |

### O14 · Kehadiran Staf, Selfie & Koreksi (T-118, T-119, T-122)

| Action | Endpoint | Fields |
|---|---|---|
| Summary + table | `GET /owner/attendance?outlet_id=&user_id=&from=&to=` | `summary:[{user, outlets, worked_minutes, days}]`, `needs_correction_count`, `records:[{id, date, user, outlet, timezone, clock_in_at, clock_out_at, duration_minutes, has_selfie_in, has_selfie_out, status: open\|closed\|needs_correction\|corrected}]`. Flagged records excluded from totals. |
| Selfie | `GET /owner/attendance/{id}/selfies` | Short-lived signed URLs (in/out) + device name. |
| Koreksi catatan | `POST /owner/attendance/{id}/corrections` | `clock_in_at?, clock_out_at?, reason*`. Returns updated record + history. |
| Riwayat koreksi | `GET /owner/attendance/{id}` | `original`, `flagged_at`, `corrections:[{at, by, from, to, reason}]`. |
| ⭳ Ekspor CSV | `GET /owner/attendance?format=csv` | |

## Staff operational screens (owner can use them too)

All under `/ops/outlets/{outlet_id}/…`; outlet access checked live.

### S1 / M2 · Counter / POS (T-038, T-067)

| Part | Endpoint | Fields |
|---|---|---|
| Header "Shift aktif · Drawer 1 · 08:00" | `GET /ops/outlets/{id}/shifts/current` | Open shifts per drawer (also used to enable/disable Cash). |
| Product grid, search, category tabs, Owner's picks | `GET /ops/outlets/{id}/menu?q=&category=&owner_picks=` | `[{product_id, name, price, photo_url, sold_out, sold_out_reason ("Bahan tidak cukup"), addon_groups:[{…, options:[{id, name, price, available}]}]}]`. |
| Table dropdown (Dine-in) | `GET /ops/outlets/{id}/tables?include=open_bill` | `[{id, name, area, open_bill:{id, total}?}]`. |
| Live totals | `POST /ops/outlets/{id}/quotes` | Items + add-ons + order type → `subtotal, pb1_rate_bps, pb1_amount, total` (server is the only source of PB1). |
| Buat order & terima bayar (F9) | `POST /ops/outlets/{id}/orders` (`Idempotency-Key`) | `type: dine_in\|takeaway, table_id?, items[{product_id, quantity, addon_option_ids[]}], payment: {method: cash, cash_received} \| {method: qris} \| {to_open_bill: true}`. Errors: `item_sold_out` (names the item), `shift_not_open`, `cash_insufficient`. Response includes `change_due`. |

### S2 / M1 · Order Board (T-030, T-068)

| Part | Endpoint | Fields |
|---|---|---|
| Columns + filters | `GET /ops/outlets/{id}/orders/board?channel=&type=&q=` | Columns `awaiting_payment, confirmed, preparing, ready, done_today`, each card: `order_no, channel, type, table?, customer_name?, item_summary, total, payment_status, payment_method?, auto_cancel_at?, bill_id?, allowed_actions`. |
| ↻ live | same endpoint polled (MVP), `?since=` for deltas | SSE can replace polling later without changing the payload. |
| Card buttons (Mulai siapkan, Tandai ready, Out for delivery, Selesai) | `POST /ops/orders/{id}/transitions` | `to_status`. Refused with `invalid_transition` if not in `allowed_actions`. |
| Cek → (proof_submitted) | opens S4 | |

### S3 · Detail Order & Reversal (T-031, T-032)

| Part | Endpoint | Fields |
|---|---|---|
| Drawer | `GET /ops/orders/{id}` | Items with add-ons, `subtotal, pb1_amount, total, channel, status, payment_status, payment_method`, `events:[{at, from, to, kind, actor:{name, role}, data}]`, `allowed_actions`. |
| Tandai selesai | `POST /ops/orders/{id}/transitions` | `to_status: completed`. |
| Batalkan (unpaid) | `POST /ops/orders/{id}/cancel` | `reason?`; stock returned. |
| Reversal order… | `POST /ops/orders/{id}/reversal` | `reason*`, `ingredients: waste\|return` (default from status: prepared → waste). Response: refund amount + method. |

### S4 · Review Pembayaran QRIS (T-036, T-037)

| Part | Endpoint | Fields |
|---|---|---|
| Antrian proof_submitted | `GET /ops/outlets/{id}/payment-proofs?status=pending` | `[{proof_id, order_no, order_type, table?, total, received_at}]`. |
| Detail + screenshot | `GET /ops/payment-proofs/{id}` | `image_url` (signed), `order_no, channel, total, customer_phone_masked, received_at, timer_stopped: true`. |
| ✓ Tandai paid | `POST /ops/payment-proofs/{id}/accept` | `merchant_account_checked: true` (required; mirrors the checkbox). Posts ledger. |
| ✕ Tolak bukti bayar | `POST /ops/payment-proofs/{id}/reject` | `reason*`. Cancels order, returns stock, no ledger, notifies customer. |

### S5 / M3 · Open Bills (T-033)

| Part | Endpoint | Fields |
|---|---|---|
| Bill cards + mode badge | `GET /ops/outlets/{id}/bills?status=open` | `payment_mode`, `[{id, table?, guest_name?, running_total, order_count, opened_at}]`. |
| + Buka bill | `POST /ops/outlets/{id}/bills` | `table_id` or `guest_name`. `conflict` if the table already has an open bill. |
| Bill detail | `GET /ops/bills/{id}` | `orders:[{order_no, channel, created_at, items, line_total}]`, `subtotal, pb1_amount, total`. |
| Tutup bill & bayar | `POST /ops/bills/{id}/close` (`Idempotency-Key`) | `method: cash\|qris, cash_received?` → `change_due`. Full payment only. |

### S6 / M4 · Reservasi & Meja (T-062, T-063, T-064)

| Part | Endpoint | Fields |
|---|---|---|
| Day timeline | `GET /ops/outlets/{id}/reservations?date=` | `tables:[{id, name, capacity, area}]`, `reservations:[{id, table_id, guest_name, party_size, starts_at, ends_at, status, source, hold_until?, no_show_at?}]`. |
| + Booking telepon / langsung | `POST /ops/outlets/{id}/reservations` | `guest_name, guest_phone?, party_size, starts_at, table_id?` (auto-assign smallest fit), `source: phone\|in_person`. `conflict` on overlap. |
| Tandai meja terisi (tanpa reservasi) | `POST /ops/outlets/{id}/walk-ins` | `table_id, party_size`. |
| Detail | `GET /ops/reservations/{id}` | Source, masked phone, status, `events` (incl. reminder sent). |
| Seated / Pindah meja / Batalkan / No-show | `POST /ops/reservations/{id}/seat`, `/move` (`table_id`), `/cancel`, `/no-show` | Actor recorded. |

### S7 / M5 · Stok & Pergerakan (T-020, T-022, T-069)

| Part | Endpoint | Fields |
|---|---|---|
| Table + filters | `GET /ops/outlets/{id}/stock?status=all\|low\|out&q=` | `counts:{low, out}`, `[{stock_item_id, name, unit, on_hand, low_threshold, status: ok\|low\|out, affected_products:[…]}]`. |
| Catat pergerakan | `POST /ops/outlets/{id}/stock-movements` (`Idempotency-Key`) | `type: restock\|waste\|adjustment, stock_item_id, quantity (signed for adjustment), note`. |
| Riwayat movement | `GET /ops/outlets/{id}/stock-movements?stock_item_id=&cursor=` | `[{at, type, quantity, unit, stock_item, order_no?, note, actor}]`. |

### S8 · Shift Kasir & Blind Count (T-039, T-040)

| Part | Endpoint | Fields |
|---|---|---|
| Drawer cards | `GET /ops/outlets/{id}/drawers?include=current_shift` | `[{drawer, shift?:{id, opened_by, opened_at, starting_cash, cash_in, cash_in_count, cash_refunds}}]` — **no expected cash** before the count. |
| Buka shift | `POST /ops/drawers/{id}/shifts` | `starting_cash`. `conflict` if one is open. |
| Submit hitungan & tutup shift | `POST /ops/shifts/{id}/close` | `count_breakdown:{"100000":12, …, "coins":4400}` → server sums `counted_cash`; response then reveals `expected_cash, difference, kind: shortage\|surplus\|none`. |

### S9 / M6 · Absensi Saya (T-116, T-117, T-122)

| Part | Endpoint | Fields |
|---|---|---|
| Status hari ini + banner | `GET /ops/me/attendance/today` | `status: working\|not_clocked_in`, `clock_in_at, device_name, outlet`, `flagged_records:[{date, outlet}]`. |
| Riwayat minggu ini | `GET /ops/me/attendance?from=&to=` | Own records only + `total_minutes` (flagged excluded). |
| Lihat selfie sendiri | `GET /ops/me/attendance/{id}/selfies` | Signed URLs. No clock-in endpoint exists for staff tokens. |

## Attendance tablet (K0–K4)

| Screen | Endpoint | Fields |
|---|---|---|
| K0 Pairing | `POST /device/pair` | `code` (6 digits, one-time, 10 min) → `{device_token, outlet:{name, timezone}}`. |
| K1 Pilih nama | `GET /device/staff` | `[{user_id, display_name, status: not_clocked_in\|working, since?}]` — only staff assigned to this outlet; `server_time`. |
| K2/K3 Selfie | `POST /device/selfies` → `{upload_url, selfie_id}` | Upload JPEG/WebP, max 2 MB. |
| K3 Simpan | `POST /device/attendance` | `user_id, selfie_id`. Server decides clock in vs clock out (working → clock out). Response: `{action: clock_in\|clock_out, at, duration_minutes?, first_time_notice: bool}`. |
| K4 errors | error codes | `selfie_required`, `device_revoked` (→ back to K0), `not_assigned`. Offline is detected client-side; nothing is queued. |

## Customer screens (W1–W12)

WhatsApp flows, not REST endpoints. They use the same core functions (quote, create order, reservations, consent) through the workers, with message formats from the wireframe. Covered in T-049–T-061 and T-076–T-077.

## Schema fields added for the wireframes

Added to T-004 when this map was written: `outlets.order_prefix` (#A-1036), `outlets.whatsapp_status`, `outlets.catalog_synced_at` (O3/O12), `users.invited_at`, `users.invitation_accepted_at` ("Diundang", O4), `cashier_shifts.count_breakdown` (S8), `order_events.data` (S3 timeline), default drawer name "Kasir depan" (O3/S8); removed configurable hold minutes (O8 shows 15 minutes fixed).

Still needed later: a WhatsApp template registry table (O12, T-084).
