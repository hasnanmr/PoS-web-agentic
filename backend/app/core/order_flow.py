"""Order status machine (T-030, T-031) — glossary §5.

The flow is fixed when the order is created (channel, type, payment mode). The server
computes `allowed_actions`; the admin app only renders those buttons (S2 note).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

Flow = Literal["online", "pay_first", "open_bill", "takeaway"]

FINAL = {"completed", "cancelled"}

_NEXT: dict[Flow, dict[str, tuple[str, ...]]] = {
    "online": {
        "pending_payment": (),  # becomes confirmed only through payment
        "confirmed": ("preparing",),
        "preparing": ("ready",),
        "ready": ("out_for_delivery", "completed"),
        "out_for_delivery": ("completed",),
    },
    "pay_first": {
        "pending_payment": (),
        "confirmed": ("preparing",),
        "preparing": ("ready",),
        "ready": ("completed",),
    },
    "open_bill": {
        "confirmed": ("preparing",),
        "preparing": ("ready",),
        "ready": ("served",),
        "served": (),  # completed when the bill is paid
    },
    "takeaway": {
        "confirmed": ("preparing",),
        "preparing": ("ready",),
        "ready": ("completed",),
    },
}


def flow_of(order: Mapping[str, Any]) -> Flow:
    if order["channel"] in ("whatsapp_online", "web_online"):
        return "online"
    if order["type"] == "takeaway":
        return "takeaway"
    if order["type"] == "dine_in" and order["payment_mode"] == "open_bill":
        return "open_bill"
    return "pay_first"


def next_statuses(order: Mapping[str, Any]) -> tuple[str, ...]:
    flow = flow_of(order)
    options = _NEXT[flow].get(order["status"], ())
    if order["type"] != "delivery":
        options = tuple(s for s in options if s != "out_for_delivery")
    if order["payment_status"] != "paid":
        # Rule 2 and 3: nothing past confirmed without payment, except open-bill orders,
        # which are paid with the bill; and never completed while unpaid.
        if flow != "open_bill":
            options = tuple(s for s in options if s not in ("preparing", "completed"))
        options = tuple(s for s in options if s != "completed")
    return options


def allowed_actions(order: Mapping[str, Any]) -> list[str]:
    """Target statuses plus `cancel` (unpaid) or `reversal` (paid), and `qris_check` for a
    paid QRIS order that staff have not yet matched against the receiving account."""
    if order["status"] in FINAL and order["payment_status"] != "paid":
        return []
    actions = list(next_statuses(order)) if order["status"] not in FINAL else []
    if order["payment_status"] in ("unpaid", "proof_submitted") and order["status"] not in FINAL:
        actions.append("cancel")
    if order["payment_status"] == "paid" and order["status"] != "cancelled":
        actions.append("reversal")
        # S2 "Cek →": a QRIS payment not yet found in the receiving account (PoC demo).
        if order.get("qris_unchecked"):
            actions.append("qris_check")
    return actions


def default_ingredients(status: str) -> Literal["waste", "return"]:
    """S3: prepared orders record the ingredients as waste; others return them."""
    return (
        "waste"
        if status in ("preparing", "ready", "served", "out_for_delivery", "completed")
        else "return"
    )
