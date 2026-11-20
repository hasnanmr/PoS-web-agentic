"""WhatsApp Cloud API client (Graph API `/{phone_number_id}/messages`) for the outbound worker.

Errors are classified for the retry policy (Appendix A.3): network failures, HTTP 429/5xx and
Meta's throttling codes are retryable; other 4xx are permanent. Meta's "outside the 24-hour
customer service window" error is reported separately so the sender can switch to an approved
template (T-055).
"""

from __future__ import annotations

import asyncio
import http.client
import json
import urllib.error
import urllib.request
from typing import Any, Protocol

# Meta error codes that mean "slow down / try again" even when the HTTP status is 400.
# 4 and 80007: app or account rate limit; 130429: throughput limit; 131016: service
# unavailable; 131056: too many messages to the same customer in a short time.
RETRYABLE_CODES = frozenset({4, 80007, 130429, 131016, 131056})
# Re-engagement message: more than 24 hours since the customer last wrote (FR6.2).
OUTSIDE_WINDOW_CODE = 131047


class GraphError(Exception):
    def __init__(self, status: int, code: int | None, message: str) -> None:
        super().__init__(f"graph api {status} (code {code}): {message}")
        self.status = status  # 0 = no HTTP response (network, timeout)
        self.code = code
        self.message = message

    @property
    def retryable(self) -> bool:
        return (
            self.status == 0
            or self.status == 429
            or self.status >= 500
            or self.code in RETRYABLE_CODES
        )

    @property
    def outside_window(self) -> bool:
        return self.code == OUTSIDE_WINDOW_CODE


class GraphClient(Protocol):
    async def send_message(self, phone_number_id: str, to: str, body: dict[str, Any]) -> str:
        """Send one message; return Meta's message id (wamid). Raise `GraphError`."""
        ...


class HttpGraphClient:
    def __init__(
        self, base_url: str, version: str, access_token: str, timeout: float = 10.0
    ) -> None:
        if not base_url.startswith("https://") and not base_url.startswith(
            ("http://localhost", "http://127.0.0.1")
        ):
            raise ValueError("WHATSAPP_GRAPH_URL must use https")
        self._root = f"{base_url.rstrip('/')}/{version}"
        self._token = access_token
        self._timeout = timeout

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        req = urllib.request.Request(  # noqa: S310 - scheme validated in __init__
            self._root + path,
            method="POST",
            data=json.dumps(payload, ensure_ascii=False).encode(),
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:  # noqa: S310
                raw = resp.read()
            data = json.loads(raw) if raw else {}
            return data if isinstance(data, dict) else {}
        except urllib.error.HTTPError as exc:
            code, message = None, str(exc.reason)
            try:
                err = json.loads(exc.read() or b"{}").get("error") or {}
                code = int(err["code"]) if "code" in err else None
                message = str(err.get("message") or message)[:300]
            except (OSError, ValueError, TypeError, AttributeError):
                pass
            raise GraphError(exc.code, code, message) from None
        except urllib.error.URLError as exc:
            raise GraphError(0, None, str(exc.reason)) from None
        except (OSError, http.client.HTTPException, ValueError) as exc:
            raise GraphError(0, None, f"{type(exc).__name__}: {exc}") from None

    async def send_message(self, phone_number_id: str, to: str, body: dict[str, Any]) -> str:
        payload = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": to}
        payload.update(body)
        data = await asyncio.to_thread(self._post, f"/{phone_number_id}/messages", payload)
        messages = data.get("messages")
        if not isinstance(messages, list) or not messages or "id" not in messages[0]:
            raise GraphError(200, None, f"no message id in response: {str(data)[:200]}")
        return str(messages[0]["id"])
