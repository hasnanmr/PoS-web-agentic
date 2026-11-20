"""Meta webhook: signature check and splitting a delivery into inbound events (T-045, T-046).

Meta signs the raw request body with the app secret: `X-Hub-Signature-256: sha256=<hex>`.
One delivery can carry several numbers, messages, and delivery statuses; each becomes its own
event so the worker processes (and de-duplicates) them one by one.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any, Literal


def valid_signature(app_secret: str, body: bytes, header: str | None) -> bool:
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256=").strip().lower())


@dataclass(frozen=True, slots=True)
class InboundEvent:
    kind: Literal["message", "status"]
    phone_number_id: str
    idempotency_key: str  # message: Meta message id; status: "<message id>:<status>"
    payload: dict[str, Any]


def _dicts(value: Any) -> list[dict[str, Any]]:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def parse_events(data: Any) -> list[InboundEvent]:
    """Inbound messages and delivery statuses in a webhook body; anything else is ignored."""
    if not isinstance(data, dict) or data.get("object") != "whatsapp_business_account":
        return []
    events: list[InboundEvent] = []
    for entry in _dicts(data.get("entry")):
        for change in _dicts(entry.get("changes")):
            value = change.get("value")
            if change.get("field") != "messages" or not isinstance(value, dict):
                continue
            metadata = value.get("metadata")
            phone_number_id = (
                metadata.get("phone_number_id") if isinstance(metadata, dict) else None
            )
            if not isinstance(phone_number_id, str) or not phone_number_id:
                continue
            names = {
                c.get("wa_id"): (c.get("profile") or {}).get("name")
                for c in _dicts(value.get("contacts"))
            }
            for msg in _dicts(value.get("messages")):
                msg_id, sender = msg.get("id"), msg.get("from")
                if not isinstance(msg_id, str) or not isinstance(sender, str):
                    continue
                events.append(
                    InboundEvent(
                        "message",
                        phone_number_id,
                        msg_id,
                        {
                            "phone_number_id": phone_number_id,
                            "contact": {"wa_id": sender, "name": names.get(sender)},
                            "message": msg,
                        },
                    )
                )
            for status in _dicts(value.get("statuses")):
                msg_id, state = status.get("id"), status.get("status")
                if not isinstance(msg_id, str) or not isinstance(state, str):
                    continue
                events.append(
                    InboundEvent(
                        "status",
                        phone_number_id,
                        f"{msg_id}:{state}",
                        {"phone_number_id": phone_number_id, "status": status},
                    )
                )
    return events
