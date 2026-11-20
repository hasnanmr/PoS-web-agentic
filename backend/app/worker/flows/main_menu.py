"""W1 · Menu utama — list message (US-009, T-050; PRD FR2.0, AC2.1, AC2.14).

Wireframe copy:
  "Selamat datang di Kopi Senja - Dago ☕ / Mau ngapain hari ini?"  [☰ Lihat pilihan]
  Pilih layanan: Pesan · Rekomendasi · Reservasi · Reservasi Saya · Data Saya
Reservasi and Reservasi Saya appear only when the outlet has reservations enabled.
"""

from __future__ import annotations

from typing import Any

from app.core.conversations import OutletProfile
from app.whatsapp import outgoing
from app.whatsapp.incoming import Incoming

PESAN = "pesan"
REKOMENDASI = "rekomendasi"
RESERVASI = "reservasi"
RESERVASI_SAYA = "reservasi_saya"
DATA_SAYA = "data_saya"

ROW_PREFIX = "menu:"

_ROWS: tuple[tuple[str, str, str], ...] = (
    (PESAN, "Pesan", "Lihat katalog & pesan"),
    (REKOMENDASI, "Rekomendasi", "Owner's picks & best seller"),
    (RESERVASI, "Reservasi", "Booking meja"),
    (RESERVASI_SAYA, "Reservasi Saya", "Lihat, batal, reschedule"),
    (DATA_SAYA, "Data Saya", "Membership & data pribadi"),
)
_RESERVATION_ROWS = frozenset({RESERVASI, RESERVASI_SAYA})


def options(profile: OutletProfile) -> list[str]:
    """Row keys shown to this outlet's customers, in wireframe order."""
    return [
        key for key, _, _ in _ROWS if profile.reservations_enabled or key not in _RESERVATION_ROWS
    ]


def message(profile: OutletProfile) -> dict[str, Any]:
    shown = set(options(profile))
    rows = [
        outgoing.Row(f"{ROW_PREFIX}{key}", title, description)
        for key, title, description in _ROWS
        if key in shown
    ]
    return outgoing.list_message(
        f"Selamat datang di {profile.display_name} ☕\nMau ngapain hari ini?",
        "Lihat pilihan",
        [outgoing.Section("Pilih layanan", rows)],
    )


def choice(incoming: Incoming, profile: OutletProfile) -> str | None:
    """The main-menu row the customer tapped, if it is one shown at this outlet."""
    if not incoming.reply_id or not incoming.reply_id.startswith(ROW_PREFIX):
        return None
    key = incoming.reply_id.removeprefix(ROW_PREFIX)
    return key if key in options(profile) else None
