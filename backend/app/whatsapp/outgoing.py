"""Outgoing message bodies for the Cloud API `/messages` endpoint.

Each builder returns the type-specific part of the request; the sender adds
`messaging_product`, `recipient_type`, and `to`. Meta's size limits are checked here so a
message that Meta would reject (a permanent 4xx) fails in tests instead.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

BODY_MAX = 1024
LIST_BUTTON_MAX = 20
SECTION_TITLE_MAX = 24
ROW_TITLE_MAX = 24
ROW_DESCRIPTION_MAX = 72
ROWS_MAX = 10
REPLY_BUTTON_TITLE_MAX = 20
REPLY_BUTTONS_MAX = 3
ID_MAX = 200


def _check(value: str, limit: int, what: str) -> str:
    if not value or len(value) > limit:
        raise ValueError(f"{what} must be 1-{limit} characters: {value!r}")
    return value


def text(body: str) -> dict[str, Any]:
    return {"type": "text", "text": {"body": _check(body, 4096, "text body"), "preview_url": False}}


@dataclass(frozen=True, slots=True)
class Row:
    id: str
    title: str
    description: str | None = None


@dataclass(frozen=True, slots=True)
class Section:
    title: str
    rows: Sequence[Row]


def list_message(body: str, button: str, sections: Sequence[Section]) -> dict[str, Any]:
    rows_total = sum(len(s.rows) for s in sections)
    if not sections or rows_total == 0 or rows_total > ROWS_MAX:
        raise ValueError(f"a list message needs 1-{ROWS_MAX} rows, got {rows_total}")
    out_sections = []
    for s in sections:
        rows = []
        for r in s.rows:
            row: dict[str, str] = {
                "id": _check(r.id, ID_MAX, "row id"),
                "title": _check(r.title, ROW_TITLE_MAX, "row title"),
            }
            if r.description:
                row["description"] = _check(r.description, ROW_DESCRIPTION_MAX, "row description")
            rows.append(row)
        out_sections.append(
            {"title": _check(s.title, SECTION_TITLE_MAX, "section title"), "rows": rows}
        )
    return {
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": _check(body, BODY_MAX, "list body")},
            "action": {
                "button": _check(button, LIST_BUTTON_MAX, "list button"),
                "sections": out_sections,
            },
        },
    }


def reply_buttons(body: str, buttons: Sequence[tuple[str, str]]) -> dict[str, Any]:
    if not 1 <= len(buttons) <= REPLY_BUTTONS_MAX:
        raise ValueError(f"reply buttons need 1-{REPLY_BUTTONS_MAX} buttons, got {len(buttons)}")
    return {
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": _check(body, BODY_MAX, "button body")},
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": _check(bid, ID_MAX, "button id"),
                            "title": _check(title, REPLY_BUTTON_TITLE_MAX, "button title"),
                        },
                    }
                    for bid, title in buttons
                ]
            },
        },
    }
