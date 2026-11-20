"""Read what a customer sent: text, a list/button choice, a cart, an image, or other."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Incoming:
    type: str  # Meta message type: text, interactive, button, order, image, ...
    text: str | None = None  # typed text (or the tapped option's title)
    reply_id: str | None = None  # id of the tapped list row / reply button
    raw: dict[str, Any] | None = None

    @property
    def keyword(self) -> str:
        """Typed text normalised for keyword checks ("Menu " → "menu")."""
        if self.type != "text" or not self.text:
            return ""
        return " ".join(self.text.split()).casefold()


def parse_message(message: dict[str, Any]) -> Incoming:
    kind = str(message.get("type") or "unknown")
    if kind == "text":
        body = (message.get("text") or {}).get("body")
        return Incoming(kind, text=body if isinstance(body, str) else None, raw=message)
    if kind == "interactive":
        inter = message.get("interactive") or {}
        reply = inter.get("list_reply") or inter.get("button_reply") or {}
        return Incoming(kind, text=reply.get("title"), reply_id=reply.get("id"), raw=message)
    if kind == "button":  # quick-reply button on a template message
        btn = message.get("button") or {}
        return Incoming(kind, text=btn.get("text"), reply_id=btn.get("payload"), raw=message)
    return Incoming(kind, raw=message)
