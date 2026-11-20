"""The one message envelope every queue uses (api-boundaries §5).

```json
{"type": "wa.inbound.message", "version": 1, "id": "uuid", "tenant_id": "uuid",
 "outlet_id": "uuid", "occurred_at": "2026-11-17T12:00:00Z",
 "idempotency_key": "wamid.HBgM…", "payload": {}}
```

Routing metadata travels in headers: `x-correlation-id`, `x-attempt`, `x-failure-reason`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

ENVELOPE_VERSION = 1

HEADER_CORRELATION = "x-correlation-id"
HEADER_ATTEMPT = "x-attempt"
HEADER_FAILURE = "x-failure-reason"


class InvalidEnvelopeError(ValueError):
    """The message body is not a valid envelope (dead-lettered without a retry)."""


@dataclass(frozen=True, slots=True)
class Envelope:
    type: str
    tenant_id: UUID
    outlet_id: UUID
    idempotency_key: str
    payload: dict[str, Any]
    id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    version: int = ENVELOPE_VERSION

    def to_json(self) -> bytes:
        return json.dumps(
            {
                "type": self.type,
                "version": self.version,
                "id": str(self.id),
                "tenant_id": str(self.tenant_id),
                "outlet_id": str(self.outlet_id),
                "occurred_at": self.occurred_at.isoformat().replace("+00:00", "Z"),
                "idempotency_key": self.idempotency_key,
                "payload": self.payload,
            },
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()

    @classmethod
    def from_json(cls, body: bytes) -> Envelope:
        try:
            data = json.loads(body)
            if not isinstance(data, dict) or not isinstance(data.get("payload"), dict):
                raise TypeError("envelope must be an object with an object payload")
            if data.get("version") != ENVELOPE_VERSION:
                raise ValueError(f"unsupported envelope version {data.get('version')!r}")
            return cls(
                type=str(data["type"]),
                version=int(data["version"]),
                id=UUID(str(data["id"])),
                tenant_id=UUID(str(data["tenant_id"])),
                outlet_id=UUID(str(data["outlet_id"])),
                occurred_at=datetime.fromisoformat(str(data["occurred_at"])),
                idempotency_key=str(data["idempotency_key"]),
                payload=data["payload"],
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise InvalidEnvelopeError(str(exc)) from exc
