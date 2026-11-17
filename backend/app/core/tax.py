"""PB1 (restaurant tax) and order totals, in integer rupiah only.

Rules (glossary section 2, FR11.5, FR2.6):

- PB1 is set per outlet: off by default, rate in basis points (1000 = 10%), allowed 1..1000.
  The rate is not known in advance, so it is never hardcoded.
- ``pb1 = round_half_up(subtotal * rate_bps / 10000)`` with integer arithmetic.
- The PB1 base is the subtotal including add-ons and excluding the delivery fee.
- ``total = subtotal + pb1 + delivery_fee``; totals themselves are never rounded.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.core.money import Rupiah, ensure_rupiah

BPS_DENOMINATOR = 10_000
PB1_MIN_RATE_BPS = 1
PB1_MAX_RATE_BPS = 1_000


def _validate_rate_bps(rate_bps: object) -> int:
    if isinstance(rate_bps, bool) or not isinstance(rate_bps, int):
        raise TypeError(f"pb1 rate_bps must be an int, got {type(rate_bps).__name__}")
    if not PB1_MIN_RATE_BPS <= rate_bps <= PB1_MAX_RATE_BPS:
        raise ValueError(
            f"pb1 rate_bps must be between {PB1_MIN_RATE_BPS} and {PB1_MAX_RATE_BPS}, "
            f"got {rate_bps}"
        )
    return rate_bps


@dataclass(frozen=True, slots=True)
class Pb1Setting:
    """An outlet's PB1 setting (``pb1_enabled`` / ``pb1_rate_bps``).

    A rate is required when enabled. When disabled the rate may still be kept (so the owner
    can switch PB1 back on), but it is validated if present and never applied.
    """

    enabled: bool = False
    rate_bps: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise TypeError("pb1 enabled must be a bool")
        if self.rate_bps is None:
            if self.enabled:
                raise ValueError("pb1 rate_bps is required when PB1 is enabled")
        else:
            _validate_rate_bps(self.rate_bps)

    @classmethod
    def off(cls) -> Pb1Setting:
        return cls(enabled=False, rate_bps=None)

    @property
    def effective_rate_bps(self) -> int | None:
        """The rate to apply and snapshot on the order, or ``None`` when PB1 is off."""
        return self.rate_bps if self.enabled else None


def round_half_up_div(numerator: int, denominator: int) -> int:
    """Integer ``numerator / denominator`` rounded half up (numerator >= 0, denominator > 0)."""
    if numerator < 0 or denominator <= 0:
        raise ValueError("round_half_up_div needs numerator >= 0 and denominator > 0")
    return (2 * numerator + denominator) // (2 * denominator)


def pb1_amount(subtotal: int, setting: Pb1Setting) -> Rupiah:
    """PB1 on ``subtotal`` (menu items plus add-ons, no delivery fee). ``0`` when PB1 is off."""
    base = ensure_rupiah(subtotal, name="subtotal")
    rate = setting.effective_rate_bps
    if rate is None:
        return Rupiah(0)
    return Rupiah(round_half_up_div(base * rate, BPS_DENOMINATOR))


@dataclass(frozen=True, slots=True)
class Quote:
    """Priced summary of an order or bill. ``pb1_rate_bps`` is the snapshot (``None`` = off)."""

    subtotal: Rupiah
    pb1_rate_bps: int | None
    pb1_amount: Rupiah
    delivery_fee: Rupiah
    total: Rupiah


def quote_totals(subtotal: int, pb1_setting: Pb1Setting, delivery_fee: int = 0) -> Quote:
    """Compute PB1 and the exact total. The delivery fee is added after PB1, never taxed."""
    sub = ensure_rupiah(subtotal, name="subtotal")
    fee = ensure_rupiah(delivery_fee, name="delivery_fee")
    pb1 = pb1_amount(sub, pb1_setting)
    return Quote(
        subtotal=sub,
        pb1_rate_bps=pb1_setting.effective_rate_bps,
        pb1_amount=pb1,
        delivery_fee=fee,
        total=Rupiah(sub + pb1 + fee),
    )


def line_total(unit_price: int, addon_prices: Iterable[int], quantity: int) -> Rupiah:
    """``(unit_price + sum(addon_prices)) * quantity`` for one order line (FR4.9, AC4.5).

    Add-on prices may be ``0`` (free option) but not negative; ``quantity`` must be >= 1.
    """
    unit = ensure_rupiah(unit_price, name="unit_price")
    addons = sum(ensure_rupiah(p, name="addon_price") for p in addon_prices)
    if isinstance(quantity, bool) or not isinstance(quantity, int):
        raise TypeError(f"quantity must be an int, got {type(quantity).__name__}")
    if quantity < 1:
        raise ValueError(f"quantity must be at least 1, got {quantity}")
    return Rupiah((unit + addons) * quantity)
