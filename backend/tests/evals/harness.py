"""Agent evaluation harness (T-092): run a case through the real endpoint and check the result.

A case is one or more customer messages sent to `POST /public/{o|t}/…/agent/messages` (the
same SSE stream the chat page reads). Checks are deterministic rules on the structured
result — drafts, cards, flags, the server quote, the database — not a model grading a model.
Each check returns failure strings; an empty list means the case passed.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

Final = dict[str, Any]


@dataclass
class Turn:
    text: str
    final: Final | None
    error: dict[str, Any] | None
    deltas: str


@dataclass
class World:
    """What the checks may look at: the outlet's menu, the client, and database counters."""

    client: TestClient
    base: str
    menu: dict[str, dict[str, Any]]
    timezone: str
    count_writes: Callable[[], tuple[int, int]]  # (orders, reservations) of the outlet

    def option_id(self, item: str, option: str) -> str:
        for group in self.menu[item]["addon_groups"]:
            for o in group["options"]:
                if o["name"] == option:
                    return str(o["id"])
        raise KeyError(f"{item}: {option}")

    def prices(self) -> set[int]:
        out: set[int] = set()
        for item in self.menu.values():
            out.add(item["price"])
            out.update(o["price"] for g in item["addon_groups"] for o in g["options"])
        return out


Check = Callable[[list[Turn], World], list[str]]


@dataclass
class Case:
    id: str
    title: str
    messages: list[str]
    checks: list[Check]
    context: str = "auto"
    critical: bool = False
    scope: str = "o"  # "o" (outlet link, WIB), "o_wita" (outlet link, WITA), "t" (table QR)
    tags: list[str] = field(default_factory=list)


@dataclass
class Result:
    case: Case
    failures: list[str]
    turns: list[Turn]
    trace_id: str | None = None

    @property
    def passed(self) -> bool:
        return not self.failures


def send(client: TestClient, base: str, session: str, text: str, context: str) -> Turn:
    res = client.post(
        f"{base}/agent/messages",
        headers={"X-Chat-Session": session},
        json={"text": text, "context": context},
    )
    if res.status_code != 200:
        return Turn(text, None, {"code": f"http_{res.status_code}"}, "")
    final = error = None
    deltas = ""
    for block in res.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        data = json.loads(lines.get("data", "{}"))
        if lines.get("event") == "delta":
            deltas += data.get("text", "")
        elif lines.get("event") == "final":
            final = data
        elif lines.get("event") == "error":
            error = data
    return Turn(text, final, error, deltas)


def run_case(case: Case, world: World, session: str) -> Result:
    before = world.count_writes()
    turns = [send(world.client, world.base, session, m, case.context) for m in case.messages]
    failures = [
        f"turn {i + 1}: agent error {t.error}" for i, t in enumerate(turns) if t.final is None
    ]
    if not failures:
        for check in case.checks:
            failures += check(turns, world)
    if world.count_writes() != before:
        failures.append("an order or booking was created without the customer's tap")
    return Result(case, failures, turns)


# Checks ----------------------------------------------------------------------------------------

_CLAIM = re.compile(
    r"(sudah|berhasil|telah)\s+(aku\s+|saya\s+|kami\s+)?(di)?(buat|pesan|pesankan|booking|kan|konfirmasi|proses)"
    r"|pesanan(mu| kamu)? (sudah|telah) (masuk|dibuat|diproses)",
    re.IGNORECASE,
)
_RUPIAH = re.compile(r"Rp\s?([\d.]+)")


def last(turns: list[Turn]) -> Final:
    final = turns[-1].final
    assert final is not None
    return final


def order_lines(*expected: tuple[str, int, set[str]]) -> Check:
    """The last turn's order draft has exactly these (item, quantity, add-on names) lines."""

    def check(turns: list[Turn], world: World) -> list[str]:
        draft = last(turns).get("order_draft")
        if not draft:
            return ["no order draft"]
        got = sorted((ln["name"], ln["quantity"], frozenset(ln["addons"])) for ln in draft["lines"])
        want = sorted((n, q, frozenset(a)) for n, q, a in expected)
        return [] if got == want else [f"draft lines {got} != {want}"]

    return check


def fulfillment(value: str | None) -> Check:
    def check(turns: list[Turn], world: World) -> list[str]:
        draft = last(turns).get("order_draft") or {}
        return (
            []
            if draft.get("fulfillment") == value
            else [f"fulfillment {draft.get('fulfillment')!r} != {value!r}"]
        )

    return check


def no_order_draft(turns: list[Turn], world: World) -> list[str]:
    return ["unexpected order draft"] if last(turns).get("order_draft") else []


def no_item_in_draft(name: str) -> Check:
    def check(turns: list[Turn], world: World) -> list[str]:
        draft = last(turns).get("order_draft") or {"lines": []}
        return (
            [f"{name} is in the draft"] if any(ln["name"] == name for ln in draft["lines"]) else []
        )

    return check


def reply_mentions(*words: str) -> Check:
    """The last reply mentions at least one of the words (case-insensitive)."""

    def check(turns: list[Turn], world: World) -> list[str]:
        text = last(turns)["reply_text"].lower()
        return [] if any(w.lower() in text for w in words) else [f"reply mentions none of {words}"]

    return check


def quote_matches(turns: list[Turn], world: World) -> list[str]:
    """Every amount in a draft equals the server quote for the same lines and fulfillment."""
    draft = last(turns).get("order_draft")
    if not draft:
        return []
    items = [
        {
            "product_id": ln["product_id"],
            "quantity": ln["quantity"],
            "addon_option_ids": ln["addon_option_ids"],
            "note": ln["note"],
        }
        for ln in draft["lines"]
    ]
    body: dict[str, Any] = {"items": items}
    if world.base.startswith("/api/v1/public/o/"):
        body["fulfillment"] = draft["fulfillment"]
    quote = world.client.post(f"{world.base}/quote", json=body).json()
    diffs = [
        k for k in ("subtotal", "pb1_amount", "delivery_fee", "total") if quote.get(k) != draft[k]
    ]
    return [f"draft {diffs} differ from the quote"] if diffs else []


def amounts_are_real(turns: list[Turn], world: World) -> list[str]:
    """No made-up prices: every "Rp …" in the reply is a menu price or a draft/quote amount."""
    final = last(turns)
    allowed = world.prices()
    draft = final.get("order_draft")
    if draft:
        allowed |= {draft["subtotal"], draft["pb1_amount"], draft["delivery_fee"], draft["total"]}
        allowed |= {ln["line_total"] for ln in draft["lines"]}
    bad = [
        m
        for m in _RUPIAH.findall(final["reply_text"])
        if int(m.replace(".", "") or 0) not in allowed
    ]
    return [f"reply invents amounts {bad}"] if bad else []


def no_creation_claim(turns: list[Turn], world: World) -> list[str]:
    hit = _CLAIM.search(last(turns)["reply_text"])
    return [f"reply claims something was created: {hit.group(0)!r}"] if hit else []


def out_of_scope(turns: list[Turn], world: World) -> list[str]:
    final = last(turns)
    failures = [] if final["out_of_scope"] else ["not flagged out of scope"]
    if final.get("order_draft") or final.get("booking_draft"):
        failures.append("out-of-scope reply carries a draft")
    return failures


def in_scope(turns: list[Turn], world: World) -> list[str]:
    return ["flagged out of scope"] if last(turns)["out_of_scope"] else []


def booking_at(days_ahead: int, hhmm: str, party: int) -> Check:
    """The booking draft is for `party` people at `hhmm` outlet-local time, `days_ahead` days on."""

    def check(turns: list[Turn], world: World) -> list[str]:
        draft = last(turns).get("booking_draft")
        if not draft:
            return ["no booking draft"]
        zone = ZoneInfo(world.timezone)
        start = datetime.fromisoformat(draft["start_at"]).astimezone(zone)
        today = datetime.now(zone).date()
        failures = []
        if (start.date() - today).days != days_ahead or start.strftime("%H:%M") != hhmm:
            failures.append(
                f"booking at {start:%Y-%m-%d %H:%M} {world.timezone}, wanted +{days_ahead}d {hhmm}"
            )
        if draft["party_size"] != party:
            failures.append(f"party {draft['party_size']} != {party}")
        return failures

    return check


def no_booking_at(hhmm: str) -> Check:
    def check(turns: list[Turn], world: World) -> list[str]:
        draft = last(turns).get("booking_draft")
        if not draft:
            return []
        start = datetime.fromisoformat(draft["start_at"]).astimezone(ZoneInfo(world.timezone))
        return [f"booked the full time {hhmm}"] if start.strftime("%H:%M") == hhmm else []

    return check


def offers_alternatives(turns: list[Turn], world: World) -> list[str]:
    final = last(turns)
    times = [q for q in final["quick_replies"] if re.search(r"\d{1,2}[:.]\d{2}", q)]
    text_times = re.findall(r"\d{1,2}[:.]\d{2}", final["reply_text"])
    return [] if times or len(text_times) >= 1 else ["no alternative times offered"]


def cards(min_count: int = 1, tag_items: set[str] | None = None) -> Check:
    """Recommendation cards: at least `min_count`, all on the menu and not sold out; with
    `tag_items`, at least one of those items is among them."""

    def check(turns: list[Turn], world: World) -> list[str]:
        shown = last(turns)["cards"]
        failures = []
        if len(shown) < min_count:
            failures.append(f"{len(shown)} cards, wanted ≥ {min_count}")
        for c in shown:
            item = world.menu.get(c["name"])
            if item is None or item["sold_out"]:
                failures.append(f"card {c['name']} is not orderable")
        if tag_items and not any(c["name"] in tag_items for c in shown):
            failures.append(f"none of {sorted(tag_items)} recommended")
        return failures

    return check
