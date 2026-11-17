"""Inventory units, quantities, and recipe arithmetic.

Stock is held in base units only (``g``, ``ml``, ``pcs``; DB enum ``app.stock_unit``).
Quantities are :class:`~decimal.Decimal` with 3 decimal places (never ``float``). ``kg`` and
``L`` exist only as display conversions (glossary section 4, FR4.5-FR4.9).

Recipes are mappings of ingredient key (any hashable id, e.g. a UUID) to the quantity used per
portion, in that ingredient's base unit.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

QUANTITY_PLACES = 3
QUANTUM = Decimal(1).scaleb(-QUANTITY_PLACES)  # Decimal("0.001")
_THOUSAND = Decimal(1000)


class StockUnit(StrEnum):
    """Base stock units, matching the database enum ``app.stock_unit``."""

    G = "g"
    ML = "ml"
    PCS = "pcs"


_LARGE_UNIT: dict[StockUnit, str] = {StockUnit.G: "kg", StockUnit.ML: "L"}


class NegativeQuantityError(ValueError):
    """A recipe or stock result would go below zero."""


def to_quantity(value: object, *, name: str = "quantity", allow_negative: bool = False) -> Decimal:
    """Validate and normalise a quantity to a ``Decimal`` with exactly 3 decimal places.

    Accepts ``Decimal``, ``int`` or a numeric ``str``. Rejects ``float`` and ``bool``
    (``TypeError``), non-finite values, more than 3 decimal places (no silent rounding), and
    negatives unless ``allow_negative`` is set (``ValueError``).
    """
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError(f"{name} must be a Decimal, int or str, not {type(value).__name__}")
    if isinstance(value, Decimal):
        qty = value
    elif isinstance(value, int | str):
        try:
            qty = Decimal(value)
        except ArithmeticError as exc:
            raise ValueError(f"{name} is not a valid number: {value!r}") from exc
    else:
        raise TypeError(f"{name} must be a Decimal, int or str, not {type(value).__name__}")
    if not qty.is_finite():
        raise ValueError(f"{name} must be finite, got {value!r}")
    quantized = qty.quantize(QUANTUM)
    if quantized != qty:
        raise ValueError(f"{name} has more than {QUANTITY_PLACES} decimal places: {value!r}")
    if quantized < 0 and not allow_negative:
        raise NegativeQuantityError(f"{name} must not be negative, got {value!r}")
    return quantized


def _format_number(value: Decimal, places: int) -> str:
    """Indonesian number style: ``.`` thousands, ``,`` decimals, trailing zeros trimmed."""
    rounded = value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    sign = "-" if rounded < 0 else ""
    text = f"{abs(rounded):f}"
    whole, _, frac = text.partition(".")
    frac = frac.rstrip("0")
    whole_grouped = f"{int(whole):,}".replace(",", ".")
    return f"{sign}{whole_grouped},{frac}" if frac else f"{sign}{whole_grouped}"


DISPLAY_UNITS: dict[StockUnit, frozenset[str]] = {
    StockUnit.G: frozenset({"g", "kg"}),
    StockUnit.ML: frozenset({"ml", "L"}),
    StockUnit.PCS: frozenset({"pcs"}),
}


def format_quantity(
    qty: Decimal | int | str, unit: StockUnit | str, display_unit: str | None = None
) -> str:
    """Display a base-unit quantity like the stock wireframe: ``2,4 kg``, ``180 g``, ``140 pcs``.

    ``display_unit`` is the stock item's display unit (``app.stock_items.display_unit``). The
    wireframe picks it per item: coffee beans always in kg (``0,4 kg``), oat milk in L
    (``0,8 L``), matcha in g (``180 g``). Without it, ``g``/``ml`` switch to ``kg``/``L`` from
    1000 upwards. Decimals use a comma and trailing zeros are trimmed; large-unit values show
    at most 3 decimals (rounded half up, display only); ``pcs`` groups thousands with ``.``.
    """
    stock_unit = StockUnit(unit)
    value = to_quantity(qty, allow_negative=True)
    large = _LARGE_UNIT.get(stock_unit)
    if display_unit is not None:
        if display_unit not in DISPLAY_UNITS[stock_unit]:
            raise ValueError(f"display unit {display_unit!r} does not fit base unit {stock_unit}")
        if large is not None and display_unit == large:
            return f"{_format_number(value / _THOUSAND, QUANTITY_PLACES)} {large}"
        return f"{_format_number(value, QUANTITY_PLACES)} {stock_unit.value}"
    if large is not None and abs(value) >= _THOUSAND:
        return f"{_format_number(value / _THOUSAND, QUANTITY_PLACES)} {large}"
    return f"{_format_number(value, QUANTITY_PLACES)} {stock_unit.value}"


def recipe_with_addons[K](
    base_recipe: Mapping[K, Decimal], addon_deltas: Iterable[Mapping[K, Decimal]]
) -> dict[K, Decimal]:
    """Apply add-on recipe changes (signed deltas) to one portion's recipe (FR4.9, AC4.5).

    A positive delta adds an ingredient or increases it; a negative one reduces it. Ingredients
    that end at exactly zero are dropped. Raises :class:`NegativeQuantityError` if any
    ingredient would go below zero.
    """
    result: dict[K, Decimal] = {
        key: to_quantity(qty, name=f"recipe[{key!r}]") for key, qty in base_recipe.items()
    }
    for deltas in addon_deltas:
        for key, delta in deltas.items():
            change = to_quantity(delta, name=f"addon delta[{key!r}]", allow_negative=True)
            result[key] = result.get(key, Decimal(0).quantize(QUANTUM)) + change
    for key, qty in result.items():
        if qty < 0:
            raise NegativeQuantityError(
                f"add-ons take ingredient {key!r} below zero ({qty}) for one portion"
            )
    return {key: qty for key, qty in result.items() if qty != 0}


def scale_recipe[K](recipe: Mapping[K, Decimal], quantity: int) -> dict[K, Decimal]:
    """Ingredients needed for ``quantity`` portions (AC4.4). ``quantity`` must be >= 1."""
    if isinstance(quantity, bool) or not isinstance(quantity, int):
        raise TypeError(f"quantity must be an int, got {type(quantity).__name__}")
    if quantity < 1:
        raise ValueError(f"quantity must be at least 1, got {quantity}")
    return {
        key: to_quantity(qty, name=f"recipe[{key!r}]") * quantity for key, qty in recipe.items()
    }


def portions_available[K](on_hand_by_item: Mapping[K, Decimal], recipe: Mapping[K, Decimal]) -> int:
    """Whole portions that current stock can make (FR4.7).

    The smallest ``floor(on_hand / per_portion)`` across the recipe's ingredients. An
    ingredient missing from ``on_hand_by_item`` counts as zero; negative stock counts as zero.
    Raises ``ValueError`` for a recipe with no positive ingredient quantity.
    """
    portions: int | None = None
    for key, per_portion in recipe.items():
        need = to_quantity(per_portion, name=f"recipe[{key!r}]")
        if need == 0:
            continue
        have = to_quantity(
            on_hand_by_item.get(key, 0), name=f"on_hand[{key!r}]", allow_negative=True
        )
        count = max(int(have // need), 0)
        portions = count if portions is None else min(portions, count)
    if portions is None:
        raise ValueError("recipe has no ingredient with a positive quantity")
    return portions


def is_sold_out[K](on_hand_by_item: Mapping[K, Decimal], recipe: Mapping[K, Decimal]) -> bool:
    """True when any ingredient is below one portion (FR4.7, AC4.7)."""
    return portions_available(on_hand_by_item, recipe) < 1
