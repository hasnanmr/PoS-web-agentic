"""Deterministic WhatsApp bot flows (wireframes W1-W12). Copy is taken from the wireframe.

`handle` gets the conversation's saved flow and state plus what the customer sent, and returns
the replies to send and the new flow and state. It runs inside the inbound transaction; flows
that create orders or bookings call `core` functions with the same connection (later PRs).

Conversation state (T-049):
- `flow = None` means the customer is at the main menu (no order or booking in progress).
- Typing "menu" anywhere returns to the main menu and drops the unfinished flow; nothing is
  created from it (FR2.0, AC2.14).
- A saved flow this version does not know (renamed, removed, or corrupt state) is dropped
  and the customer gets the main menu: a safe restart instead of a stuck conversation.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.core.conversations import OutletProfile
from app.whatsapp.incoming import Incoming
from app.worker.flows import main_menu

MENU_KEYWORD = "menu"


@dataclass(frozen=True, slots=True)
class FlowResult:
    replies: list[dict[str, Any]]
    flow: str | None = None
    state: dict[str, Any] = field(default_factory=dict)


FlowHandler = Callable[[dict[str, Any], Incoming, OutletProfile], FlowResult]

# Flows reachable from the main menu. Each later PR registers its flow here
# (W2-W5 order, W10 reservation, W11 Reservasi Saya, W12 Data Saya, W9 recommendations).
FLOWS: dict[str, FlowHandler] = {}


def _main_menu(profile: OutletProfile) -> FlowResult:
    return FlowResult([main_menu.message(profile)])


def handle(
    flow: str | None, state: dict[str, Any], incoming: Incoming, profile: OutletProfile
) -> FlowResult:
    if incoming.keyword == MENU_KEYWORD:
        return _main_menu(profile)
    if flow is None:
        choice = main_menu.choice(incoming, profile)
        if choice is not None and choice in FLOWS:
            return FLOWS[choice]({}, incoming, profile)
        # Not a menu choice, or a choice whose flow is not built yet: show the menu.
        return _main_menu(profile)
    handler = FLOWS.get(flow)
    if handler is None:
        return _main_menu(profile)
    return handler(state, incoming, profile)
