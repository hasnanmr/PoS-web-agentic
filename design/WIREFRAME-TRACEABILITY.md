# Wireframe Traceability — SME POS

This document links every wireframe screen in [`SME-POS-Wireframe.figcraft`](SME-POS-Wireframe.figcraft) to the user stories in [User-Stories-SME-Automation-Platform.md](../User-Stories-SME-Automation-Platform.md) and the tasks in [Task-Breakdown-SME-Automation-Platform.md](../Task-Breakdown-SME-Automation-Platform.md).

- **Baseline:** PRD v0.19, US-001–US-064, T-001–T-138.
- **Open the file:** FigCraft (`figcraft SME-POS-Wireframe.figcraft`). PNG previews of each page are in [`previews/`](previews/).
- **Labels:** every screen on the canvas has a label above it in the form `Code · Name — US-xxx · T-xxx`, matching the tables below.
- **Fidelity:** low-to-mid fidelity wireframes. The colours follow the agreed reference (light sidebar, navy primary `#1E4FA3`, light-blue background `#F3F6FB`). Copy is in Bahasa Indonesia, as in the product.

## Pages

| Page | Contents | Preview |
|---|---|---|
| 00 · Sitemap & Flow | Sitemap per role, user flows A–H, and a story-to-screen coverage table | [00-sitemap-flow.png](previews/00-sitemap-flow.png) |
| 01 · Admin — Owner | O1–O17 | [01-admin-owner.png](previews/01-admin-owner.png) |
| 02 · Admin — Staff Ops | S1–S12 | [02-admin-staff.png](previews/02-admin-staff.png) |
| 03 · WhatsApp Customer | W1–W12 (MVP), A1–A2 (Phase 2) | [03-whatsapp-customer.png](previews/03-whatsapp-customer.png) |
| 04 · Mobile 360 | M1–M6 | [04-mobile-360.png](previews/04-mobile-360.png) |
| 05 · Tablet Absensi Outlet | K0–K4 | [05-tablet-absensi.png](previews/05-tablet-absensi.png) |
| 06 · QR Meja Pelanggan | Q0–Q5, Q2a, S2 kartu order web (table QR web page, issue #44) | [06-qr-meja-pelanggan.png](previews/06-qr-meja-pelanggan.png) |
| 99 · Components | `Sidebar/Owner`, `Sidebar/Staff` (with the Thinker logo + name), "Logo Thinker · 2 opsi" (option 1 · Gelembung T chosen) | — |

## Screen → user story → task

### Owner (web admin)

| Screen | User stories | Tasks |
|---|---|---|
| O1 Login (invite-only) & Buat Bisnis | US-001, US-002, US-003, US-008 | T-006, T-010, T-011, T-024, T-066 |
| O2 Dashboard — tab Ringkasan + keramaian (busy/quiet hours, busyness map, current crowd, item terlaris); header tabs Ringkasan · PO & Supplier | US-007, US-032, US-033, US-056 | T-043, T-071, T-123, T-124 |
| O3 Bisnis & Outlet (PB1, payment mode, QRIS, cash drawers, attendance tablets, grace period) | US-002, US-017, US-018, US-019, US-020, US-053, US-055 | T-011, T-014, T-039, T-066, T-118, T-121 |
| O4 Staf & Akses (staff invitation, access matrix) | US-003, US-033 | T-006, T-012, T-013, T-066 |
| O5 Menu, Add-on & Harga Outlet | US-002, US-005, US-008 | T-016, T-017, T-018, T-051, T-066 |
| O6 Resep & Bahan | US-006, US-007 | T-019, T-021, T-022, T-066 |
| O7 Rekomendasi (owner's picks & tags) | US-028, US-029 | T-073, T-074 |
| O8 Meja & Aturan Reservasi (+ table QR: unduh / ganti token / tujuan QR web · WhatsApp) | US-013, US-022, US-063 | T-054, T-057, T-136 |
| O9 Laporan Cashflow & Pengeluaran (biaya saja; PO tidak lagi di sini) | US-030, US-031, US-032 | T-041, T-042, T-043 |
| O9b Pengeluaran (menu sidebar: pembayaran PO supplier — PO dibuka staf di S12, dibayar owner — disorot + pengeluaran langsung; KPI, per supplier, riwayat dengan chip sumber, Catat pengeluaran) | US-031, US-057, US-058 | T-042, T-130 |
| O10 Laporan Cash Count | US-018 | T-040, T-102 |
| O11 Audit Log | US-004, US-016, US-021 | T-031, T-101 |
| O12 WhatsApp Setup & Template | US-002, US-008, US-015, US-036 | T-045, T-051, T-084, T-100 |
| O13 Dead-letter & Antrean Pesan | US-036, US-037, US-050 | T-081, T-112 |
| O14 Kehadiran Staf, Selfie & Koreksi | US-053, US-054 | T-118, T-119, T-122 |
| O15 Dashboard — tab PO & Supplier: Daftar PO (chip status, filter outlet + bulan milik tab), detail PO dengan alur, riwayat, sisa hutang, Daftar supplier, + Buka PO | US-031, US-057, US-058, US-059, US-060, US-061 | T-125, T-126, T-127, T-128, T-130 |
| O15 Daftar supplier (dialog from the PO & Supplier tab header; owner only: list, add, edit, deactivate, no delete) | US-057 | T-126, T-130 |
| O16 Buka PO (owner dari Dashboard › PO & Supplier; staf memakai S12 dengan form yang sama; skema bayar mundur / bayar di muka, item bahan atau teks bebas) | US-057 | T-126, T-130 |
| O17 Dashboard — tab PO & Supplier, kartu di atas O15: Ringkasan PO (bulan), Pembayaran supplier (hutang per hari ini, termasuk angka KPI lama O15), PO ada selisih (tutup dengan catatan, owner saja) + dialog Catat pembayaran | US-058, US-059, US-061 | T-128, T-130 |

### Staff (web admin)

| Screen | User stories | Tasks |
|---|---|---|
| S1 Counter / POS (dine-in, takeaway) | US-011, US-018, US-019, US-020, US-034 | T-038, T-067 |
| S1 · Popup Pembayaran — Cash (uang diterima → kembalian) & QRIS (gambar QRIS → bukti bayar); also used by S5 Tutup bill. Order / bill completes only on "Pembayaran selesai" | US-018, US-020, US-034 | T-038, T-067, T-068 |
| S2 Order Board | US-013, US-014, US-015, US-016 | T-030, T-031, T-068 |
| S3 Detail Order & Reversal | US-004, US-016, US-021 | T-031, T-032, T-068 |
| S4 Review Pembayaran QRIS | US-017, US-021 | T-036, T-037, T-068 |
| S5 Open Bills (+ "⇄ Split per item"; bayar penuh atau split) | US-013, US-020, US-064 | T-033, T-068, T-138 |
| S5a Split bill per item (dialog dari S5: pilih item / porsi, bagian lunas + "Batalkan…", total bagian dengan PB1 kumulatif, sisa, Cash / QRIS → popup S1) | US-064, US-020 | T-137, T-138 |
| S6 Reservasi & Meja (today) | US-024, US-026, US-027 | T-062, T-063, T-064, T-070 |
| S7 Stok & Pergerakan | US-006, US-007 | T-020, T-022, T-069 |
| S8 Shift Kasir & Blind Count | US-018, US-030 | T-039, T-040, T-070 |
| S9 Absensi Saya (own history and selfies; no clock-in here) | US-053 | T-116, T-117, T-122 |
| S10 Purchase Order outlet (staf: daftar PO outlet, buka PO, status bayar hanya baca) | US-057, US-060 | T-126, T-130 |
| S11 Cross-check barang datang vs PO (qty PO / diterima / datang sekarang / sisa, ada selisih, Tutup PO) | US-060 | T-127, T-130 |
| S12 Buka PO (staf; outlet yang ditugaskan, langsung terbuka tanpa persetujuan) — same form as O16 | US-057 | T-126, T-130 |

### Customer (WhatsApp)

| Screen | User stories | Tasks |
|---|---|---|
| W1 Menu utama (list message) | US-009 | T-049, T-050 |
| W2 Katalog & keranjang | US-008, US-010 | T-051, T-052 |
| W3 Add-on setelah cart | US-011 | T-052 |
| W4 Pickup / Delivery | US-012 | T-053 |
| W5 Ringkasan & Confirm (+ sold out) | US-011, US-014, US-019 | T-027, T-028, T-053 |
| W6 Pembayaran QRIS & bukti bayar | US-017, US-021 | T-034, T-036 |
| W7 Notifikasi status & pembatalan (templates) | US-015, US-017, US-021 | T-034, T-055, T-084 |
| W8 Order dari QR meja | US-013, US-020 | T-033, T-054 |
| W9 Rekomendasi + AI (MVP, 30-second fallback) | US-028, US-029, US-052 | T-073, T-074, T-115 |
| W10 Reservasi meja | US-023, US-025 | T-060, T-061 |
| W11 Reservasi Saya (cancel / reschedule) | US-025 | T-061 |
| W12 Consent membership & Data Saya | US-039, US-040, US-041 | T-076, T-077, T-106 |
| A1 Order teks bebas oleh AI (Phase 2) | US-042 | T-087, T-091 |
| A2 Reservasi teks bebas oleh AI (Phase 2) | US-043 | T-088, T-091 |

### Mobile 360 px

| Screen | User stories | Tasks |
|---|---|---|
| M1 Order Board | US-016, US-035 | T-068, T-072 |
| M2 Counter | US-034, US-035 | T-067, T-072 |
| M3 Open Bill (+ "⇄ Split per item") | US-020, US-035, US-064 | T-068, T-072, T-138 |
| M3a Split bill per item (mobile, sama dengan S5a, bar bawah "Bayar bagian …") | US-064, US-035 | T-138 |
| M4 Reservasi hari ini | US-026, US-027, US-035 | T-070, T-072 |
| M5 Stok | US-006, US-007, US-035 | T-069, T-072 |
| M6 Absensi Saya (own history) | US-035, US-053 | T-072, T-117 |

### Outlet attendance tablet

| Screen | User stories | Tasks |
|---|---|---|
| K0 Pairing tablet ke outlet | US-055 | T-121 |
| K1 Pilih nama staf | US-053, US-055 | T-116, T-117, T-121 |
| K2 Ambil selfie (required) | US-053 | T-117, T-122 |
| K3 Cek foto & simpan (+ first-use privacy notice) | US-053 | T-117, T-122 |
| K4 Berhasil + error states (camera, offline, already clocked in, revoked tablet) | US-053, US-055 | T-117, T-121 |

### Customer table QR web page (issue #44)

| Screen | User stories | Tasks |
|---|---|---|
| Q0 QR tidak berlaku (token diganti / tidak dikenal) | US-063 | T-134, T-135 |
| Q1 Scan QR meja — pilih cara pesan (Pesan di sini / Pesan via WhatsApp) | US-062, US-013 | T-134, T-135 |
| Q2 Menu (harga outlet, add-on, item habis; "bayar dulu via QRIS") | US-062 | T-134, T-135 |
| Q2a Pilih add-on (dari "+" di Q2: grup wajib / opsional, jumlah, "Tambah ke pesanan") | US-062 | T-134, T-135 |
| Q3 Pesanan kamu (catatan, nama opsional, PB1, "Pesan & bayar") | US-062 | T-134, T-135 |
| Q4 Bayar dengan QRIS outlet (QRIS statis, total, batas waktu, "Saya sudah bayar", batalkan) | US-062 | T-134, T-135 |
| Q5 Status pesanan (live: menunggu konfirmasi staf → disiapkan → siap; ditolak/batal + alasan) | US-062 | T-134, T-135 |
| S2 kartu order web (kolom Menunggu bayar: "Pelanggan bilang sudah bayar", Cek & konfirmasi lunas, Tolak) — drawn on page 06 | US-062 | T-135 |

Role-aware navigation (`Sidebar/Owner`, `Sidebar/Staff`) covers US-003 and US-033 through T-013 and T-072.

## User story → screens

Every MVP story has at least one screen, except the backend-only stories marked "—".

| Story | Screens |
|---|---|
| US-001 | O1 |
| US-002 | O1, O3, O5, O12 |
| US-003 | O1, O4, sidebars |
| US-004 | S3, O11 |
| US-005 | O5 |
| US-006 | O6, S7, M5 |
| US-007 | O6, S7, M5, O2 |
| US-008 | O1, O5, O12, W2 |
| US-009 | W1 |
| US-010 | W2 |
| US-011 | W3, W5, S1 |
| US-012 | W4 |
| US-013 | W8, O8, S2, S5, Q1 |
| US-014 | W5, S2 |
| US-015 | W7, S2, O12 |
| US-016 | S2, S3, O11, M1 |
| US-017 | W6, S4, O3 |
| US-018 | S1, S8, O3, O10 |
| US-019 | O3, S1, W5 |
| US-020 | S5, S5a, W8, S1, O3, M3 |
| US-021 | S3, S4, W6, W7, O11 |
| US-022 | O8 |
| US-023 | W10 |
| US-024 | S6 |
| US-025 | W10, W11 |
| US-026 | S6, M4 |
| US-027 | S6, M4 |
| US-028 | O7, W9 |
| US-029 | W9, O7 |
| US-030 | O9, S8 |
| US-031 | O9, O15 |
| US-032 | O2, O9 |
| US-033 | O2, O4, sidebars |
| US-034 | S1, M2 |
| US-035 | M1–M6 |
| US-036 | O12, O13 |
| US-037 | O13 |
| US-038 | — (tenant isolation, backend: T-005, T-015, T-113) |
| US-039 | W12 (data location shown in the consent message) |
| US-040 | W12 |
| US-041 | W12 |
| US-049 | — (hosting: T-079, T-105, T-108, T-109, T-114) |
| US-050 | O13 |
| US-051 | — (scheduled jobs: T-104; the results show in W7, S6 and O14) |
| US-052 | W9 |
| US-053 | K1–K4, S9, M6, O3 |
| US-054 | O14 |
| US-055 | K0, K1, K4, O3 |
| US-056 | O2 |
| US-057 | S12, O16, O15, S10 |
| US-058 | O15, O17 |
| US-059 | O15, O17, S10 |
| US-060 | S11, S10, O15 |
| US-061 | O15, O17 |
| US-062 | Q1–Q5, Q2a, S2, S4 |
| US-063 | O8 |
| US-064 | S5, S5a, M3, M3a |
| US-042 (Phase 2) | A1 |
| US-043 (Phase 2) | A2 |
| US-044, US-045 (Phase 2) | Not drawn yet |
| US-046–US-048 (Phase 3) | Not drawn yet |

## UI tasks → screens

Tasks that build a screen or a WhatsApp flow, and where to find them.

| Task | Screens |
|---|---|
| T-050 Main menu list message | W1 |
| T-051 Catalog sync | W2, O5, O12 |
| T-052 Cart intake + add-on collection | W2, W3 |
| T-053 Order summary, pickup/delivery, confirm | W4, W5 |
| T-054 Table QR | W8, O8 |
| T-134 Public table API (token-scoped) | Q0–Q5 |
| T-135 Customer table web page | Q0–Q5, Q2a, S2, S4 |
| T-136 Table QR settings, download, replace token | O8 |
| T-036 QRIS payment request + screenshot intake | W6, S4 |
| T-034 Unpaid-order timeout | W6, W7, S2 |
| T-055 Order notifications + templates | W7 |
| T-060 WhatsApp reservation flow | W10 |
| T-061 Reservation confirmation, reminder, Reservasi Saya | W10, W11 |
| T-066 Owner onboarding, settings, staff, menu, recipe, prices | O1, O3, O4, O5, O6 |
| T-067 Counter order screen | S1, M2 |
| T-068 Order board, payment review, reversal, open bills | S2, S3, S4, S5, M1, M3 |
| T-137 Split bill per item (domain + API) | S5, S5a, M3a |
| T-138 Split bill per item (admin UI) | S5, S5a, M3, M3a |
| T-069 Stock screens | S7, M5 |
| T-057 Tables and reservation rules | O8 |
| T-062, T-063, T-064 Staff reservation board, walk-ins, no-show hold (Wave 6) | S6, M4 |
| T-070 Reservation/table view and cashier shift | S6, S8, M4 |
| T-071 Owner dashboard | O2 |
| T-128 Dashboard PO figures (tab PO & Supplier) | O17, O15 |
| T-130 PO screens | O15, O16, O17, S10, S11, S12 |
| T-123, T-124 Busyness queries and dashboard views | O2 |
| T-072 Role-aware navigation, 360 px responsive | sidebars, M1–M6 |
| T-073 Owner picks, best sellers | O7, W9 |
| T-074 Recommendation product message + add to cart | W9 |
| T-115 AI-assisted recommendations | W9 |
| T-076 Consent and membership | W12 |
| T-077 Data Saya flow | W12 |
| T-100 Per-outlet WhatsApp onboarding | O12 |
| T-101 Audit log screen | O11 |
| T-102 Cash count report | O10 |
| T-112 Dead-letter visibility and replay | O13 |
| T-116 Attendance domain (tablet session, selfie required) | K1, S9 |
| T-117 Attendance tablet screens + staff own history | K1–K4, S9, M6 |
| T-118 Missing clock-out flag + grace-period setting | O3, O14, S9 |
| T-119 Owner attendance report, selfies and corrections | O14 |
| T-121 Outlet attendance tablet pairing and device session | K0, K4, O3 |
| T-122 Selfie storage, signed links, 45-day deletion | K2, K3, O14, S9 |
| T-087, T-088 Phase 2 free-text order and reservation | A1, A2 |

## Decisions reflected in the wireframes

- Counter orders are **dine-in or takeaway** only; "walk-in" appears only as table occupancy for guests without a reservation (S6, M4).
- AI in the MVP is limited to **Rekomendasi** (W9): read-only suggestions, an immediate "Sebentar ya…" reply, and a fallback to owner's picks + best sellers after an error or 30 seconds. Free-text ordering and booking are Phase 2 (A1, A2).
- Staff accounts are **invite-only**; there is no public sign-up (O1, O4).
- Attendance is recorded only on the outlet's paired tablet (K0–K4): the staff member taps their name and takes a required selfie, so they must be at the outlet. Staff phones and the admin app only show their own history (S9, M6). No PIN is needed. Selfies are private, visible to the owner and the staff member, and deleted after 45 days; staff cannot delete them (the owner can, through the API).
- All purchase-order screens for the owner live in their own Dashboard tab **PO & Supplier** (issue #16): O17 cards on top, the O15 list and detail below, Buka PO (O16) and Daftar supplier from the tab header. The tab has its own outlet + month filter (PRD v0.15). The month applies only to Ringkasan PO (by PO open date, FR3.12). Pembayaran supplier and PO ada selisih always show every PO that needs action (FR3.11). The list uses the status chips (FR3.10), and a Ringkasan figure opens it with exactly those POs. Each number appears once: the old O15 KPI row was merged into O17's Pembayaran supplier card. Pengeluaran (O9) is for expenses only. Staff keep S10–S12.
- S6 / M4 add a **Selesai** action for seated reservations and walk-ins (US-026 "completed"; not drawn on the canvas, approved by the product owner on 2026-11-19) so the table is freed when the guests leave. The canvas should get the button in the next wireframe pass.
- The table QR opens the Thinker web page `/t/<token>`, not WhatsApp directly (issue #44, PRD v0.18). From one printed QR the customer orders on the web (Q2–Q4, channel `web_table`) or continues in WhatsApp (W8, `whatsapp_table`). Web orders are always **paid first with the outlet's static QRIS**: the customer taps "Saya sudah bayar" (no screenshot) and staff confirm in S2/S4 against the merchant account; web orders never join the table's open bill and the page shows only the phone's own orders (no table bill, so no bill code). The owner picks web + WhatsApp, web only, or WhatsApp only on O8; while WhatsApp isn't connected the QR always goes to the web page. Online payment (#43) later replaces the static QRIS + staff confirmation.
- Open bills can be **split per item** (issue #42, PRD v0.19): staff only (S5a, M3a); the table QR web page still shows no bill. PB1 per part is cumulative (PB1 on everything paid so far minus PB1 already paid), so the parts add up to the bill total; a paid part is undone only with a reason while the bill is open.
- A forgotten clock-out is flagged "perlu dikoreksi" 1 hour after closing time (default) without inventing a time; the owner checks selfies and corrects the record with a required reason (O14).

## Open points

- Busy, quiet, and crowded thresholds on O2 are placeholders. T-123 uses busy ≥ 130% and quiet ≤ 60% of the average orders per opening hour, and crowd Ramai at ≥ 75% of tables occupied, Sepi at ≤ 30% (constants in `backend/app/core/dashboard.py`); the product owner can still change them.
- Phase 2 screens for US-044 (FAQ, upsell) and US-045 (forecast, restock suggestions), and all Phase 3 screens, are not drawn yet.
