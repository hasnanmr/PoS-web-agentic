# CLAUDE.md

Project: SME Business Automation Platform (POS + WhatsApp ordering) for restaurants and cafes.
Specs: `PRD-SME-Automation-Platform.md`, `User-Stories-SME-Automation-Platform.md`, `Task-Breakdown-SME-Automation-Platform.md`.

## Frontend must follow the wireframes

Every frontend (admin web app, attendance tablet) screen must match the wireframes in `design/`:

- Source of truth: `design/SME-POS-Wireframe.figcraft` (zip; `document.json` holds the nodes). PNG previews in `design/previews/`.
- Before building a screen, look up its code in `design/WIREFRAME-TRACEABILITY.md` (e.g. T-067 → S1, M2) and open the matching preview. Use the same layout, sections, field order, labels, and Bahasa Indonesia copy. Do not invent screens, fields, or navigation that the wireframe does not show; if the spec and wireframe disagree, or a screen is not drawn, ask before building.
- Note the screen code (e.g. `S1`, `O3`, `M2`) in the component or route file and in the PR description.
- Behavior notes written on the canvas (grey "Catatan perilaku" boxes) are requirements, not decoration.

## Backend endpoints must follow the wireframes too

Every backend endpoint used by an admin or tablet screen must serve exactly what that wireframe screen shows and does: same fields, filters, actions, and error states.

- The contract is `docs/architecture/screen-endpoint-map.md` (screen code → method, path, fields). Conventions are in `docs/architecture/api-boundaries.md`.
- Before building or changing an endpoint, find its screen in the map and the wireframe. Do not add endpoints, fields, or actions that no screen uses (except health/infra endpoints); if a screen needs something the map lacks, update the map in the same change.
- If a screen needs data the schema cannot provide, add a migration and note it in the map.
- Order responses include `allowed_actions` computed by the server; the UI only renders those buttons.
- Mobile screens (M1–M6) reuse the desktop endpoints. WhatsApp screens (W1–W12) are worker flows, not REST.
- Domain names, enums, and money/time rules come from `docs/domain/domain-glossary-and-rules.md`.

### Design tokens (extracted from the wireframe)

| Token | Value | Use |
|---|---|---|
| primary | `#1E4FA3` | brand, primary buttons, active nav, links |
| primary-soft | `#E8EFFB` | active nav background, selected chips |
| action / CTA | `#CC4A0A` (orange `#F97316` in charts/badges) | main submit actions ("Buat order", "Simpan", "Tutup shift") |
| page background | `#F3F6FB` | app background |
| surface | `#FFFFFF` | cards, panels |
| border | `#E3E8F0` | card and table borders |
| text | `#1B2430` | primary text |
| text-muted | `#6B7280` | secondary text, captions |
| success | `#1E7A4F` on `#E3F6EC` | paid, aman, selesai |
| warning | `#8A6D1F` on `#FFF4DB` | rendah, hold, perlu dicek |
| danger | `#D93636` on `#FDECEC` | sold out, rejected, required-field errors |
| teal | `#0F766E` on `#E6F4F2` | status badges (e.g. normal crowd) |

- Font: Inter. Sizes: 11/12/13 regular for body and tables, 13 semibold for labels, 16–20 bold/semibold for headings.
- Sidebar: light, 220 px, padding 16/12, grouped sections with uppercase headings. Owner groups: OPERASIONAL, KATALOG, KEUANGAN (OWNER), PENGATURAN. Staff: OPERASIONAL only (+ "Absensi Saya") with the note "Menu, harga, laporan & pengaturan hanya untuk owner." Outlet switcher under the logo.
- Mobile 360 px (M1–M6): hamburger + title header, filter chips under the title, kanban columns become status tabs, bottom nav (Order, Counter, Bill, Reservasi, Stok), primary action as a full-width bottom bar; no horizontal scroll (AC7.2).
- Attendance tablet (K0–K4): separate full-screen app; staff clock in/out only there, never from staff phones or the admin app.
