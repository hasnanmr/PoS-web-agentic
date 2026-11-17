"""Rupiah amounts: validation, display formatting, and cash change.

Money is always whole rupiah held in a plain ``int`` (``bigint`` in the database). There are
no decimals and no floats anywhere in money paths, and totals are never rounded: the customer
pays the exact total (glossary section 2).
"""

from __future__ import annotations

from typing import NewType

Rupiah = NewType("Rupiah", int)
"""Whole-rupiah amount. A ``NewType`` over ``int`` so type checkers flag raw mixing."""

MINUS_SIGN = chr(0x2212)
"""Typographic minus (U+2212) put before ``Rp`` for negative amounts, as in the wireframes."""


class InsufficientPaymentError(ValueError):
    """Cash received is below the total, so it cannot be recorded as full payment (AC11.6)."""

    def __init__(self, total: int, received: int) -> None:
        self.total = total
        self.received = received
        self.shortfall = total - received
        super().__init__(
            f"amount received {format_rupiah(received)} is less than the total "
            f"{format_rupiah(total)} (short by {format_rupiah(self.shortfall)})"
        )


def ensure_rupiah(value: object, *, name: str = "amount", allow_negative: bool = False) -> Rupiah:
    """Return ``value`` as :data:`Rupiah` or raise.

    Rejects anything that is not a real ``int`` (``bool``, ``float``, ``Decimal`` and ``str``
    included) with ``TypeError``, and negative values with ``ValueError`` unless
    ``allow_negative`` is set (e.g. signed ledger amounts or a cash-count difference).
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be a whole-rupiah int, got {type(value).__name__}")
    if value < 0 and not allow_negative:
        raise ValueError(f"{name} must not be negative, got {value}")
    return Rupiah(value)


def _group_thousands(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def format_rupiah(amount: int, *, space: bool = True) -> str:
    """Format whole rupiah as in the wireframes: ``Rp 92.400``, ``- Rp 350.000`` (U+2212 minus).

    Follows the admin wireframes (S1 totals, O9 "- Rp 1.230.000"): a space after ``Rp`` and,
    for negatives, the minus sign U+2212 followed by a space. ``space=False`` gives the
    compact form ``Rp92.400`` / ``-Rp350.000`` for tight places such as chart labels.
    Thousands are grouped with ``.``.
    """
    value = ensure_rupiah(amount, allow_negative=True)
    sep = " " if space else ""
    sign = (MINUS_SIGN + sep) if value < 0 else ""
    return f"{sign}Rp{sep}{_group_thousands(abs(value))}"


def change_due(total: int, received: int) -> Rupiah:
    """Cash change for a payment: ``received - total``, exact to the rupiah (FR11.6).

    Raises :class:`InsufficientPaymentError` when ``received < total`` (AC11.6).
    """
    total_r = ensure_rupiah(total, name="total")
    received_r = ensure_rupiah(received, name="received")
    if received_r < total_r:
        raise InsufficientPaymentError(total_r, received_r)
    return Rupiah(received_r - total_r)
