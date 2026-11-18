from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.units import (
    NegativeQuantityError,
    StockUnit,
    format_quantity,
    is_sold_out,
    portions_available,
    recipe_with_addons,
    scale_recipe,
    to_quantity,
)

D = Decimal

ES_KOPI_SUSU = {
    "coffee_beans": D("18"),
    "milk": D("150"),
    "palm_sugar_syrup": D("20"),
    "cup": D("1"),
}


def test_stock_unit_values_match_db_enum() -> None:
    assert [u.value for u in StockUnit] == ["g", "ml", "pcs"]


@pytest.mark.parametrize(
    ("qty", "unit", "expected"),
    [
        (D("2400"), "g", "2,4 kg"),
        (D("12000"), "ml", "12 L"),
        (D("1500"), "ml", "1,5 L"),
        (D("1000"), "g", "1 kg"),
        (D("999.5"), "g", "999,5 g"),
        (D("180"), "g", "180 g"),
        (D("180.000"), "g", "180 g"),
        (D("800"), "ml", "800 ml"),
        (D("140"), "pcs", "140 pcs"),
        (D("1200"), "pcs", "1.200 pcs"),
        (D("0"), "pcs", "0 pcs"),
        (D("2400.5"), "g", "2,401 kg"),
        (D("1234567"), "g", "1.234,567 kg"),
        (D("-40"), "g", "-40 g"),
        (D("-1500"), "ml", "-1,5 L"),
        (3000, StockUnit.G, "3 kg"),
    ],
)
def test_format_quantity(qty: Decimal | int, unit: str, expected: str) -> None:
    assert format_quantity(qty, unit) == expected


def test_format_quantity_rejects_unknown_unit() -> None:
    with pytest.raises(ValueError):
        format_quantity(D("1"), "kg")


def test_to_quantity() -> None:
    assert to_quantity("1.5") == D("1.500")
    assert str(to_quantity(2)) == "2.000"
    with pytest.raises(TypeError):
        to_quantity(1.5)
    with pytest.raises(TypeError):
        to_quantity(True)
    with pytest.raises(ValueError, match="decimal places"):
        to_quantity(D("0.0001"))
    with pytest.raises(NegativeQuantityError):
        to_quantity(D("-1"))
    with pytest.raises(ValueError):
        to_quantity("abc")
    with pytest.raises(ValueError):
        to_quantity(D("NaN"))


def test_scale_recipe_ac4_4() -> None:
    assert scale_recipe(ES_KOPI_SUSU, 2) == {
        "coffee_beans": D("36"),
        "milk": D("300"),
        "palm_sugar_syrup": D("40"),
        "cup": D("2"),
    }


@pytest.mark.parametrize("qty", [0, -2])
def test_scale_recipe_rejects_bad_quantity(qty: int) -> None:
    with pytest.raises(ValueError):
        scale_recipe(ES_KOPI_SUSU, qty)


def test_recipe_with_addons_ac4_5() -> None:
    recipe = recipe_with_addons(ES_KOPI_SUSU, [{"coffee_beans": D("18")}])
    assert recipe["coffee_beans"] == D("36")
    assert recipe["milk"] == D("150")


def test_recipe_with_addons_swap_and_new_ingredient() -> None:
    # Oat milk option: replace dairy milk with oat milk.
    recipe = recipe_with_addons(ES_KOPI_SUSU, [{"milk": D("-150"), "oat_milk": D("150")}])
    assert "milk" not in recipe
    assert recipe["oat_milk"] == D("150")


def test_recipe_with_addons_rejects_below_zero() -> None:
    with pytest.raises(NegativeQuantityError):
        recipe_with_addons(ES_KOPI_SUSU, [{"palm_sugar_syrup": D("-25")}])
    with pytest.raises(NegativeQuantityError):
        recipe_with_addons(ES_KOPI_SUSU, [{"ice": D("-1")}])


def test_recipe_with_addons_does_not_mutate_base() -> None:
    recipe_with_addons(ES_KOPI_SUSU, [{"coffee_beans": D("18")}])
    assert ES_KOPI_SUSU["coffee_beans"] == D("18")


def test_portions_available() -> None:
    on_hand = {
        "coffee_beans": D("2400"),
        "milk": D("1000"),
        "palm_sugar_syrup": D("1500"),
        "cup": D("140"),
    }
    assert portions_available(on_hand, ES_KOPI_SUSU) == 6  # milk limits: 1000 // 150
    assert not is_sold_out(on_hand, ES_KOPI_SUSU)


def test_sold_out_ac4_7() -> None:
    on_hand = {
        "coffee_beans": D("2400"),
        "milk": D("100"),
        "palm_sugar_syrup": D("1500"),
        "cup": D("140"),
    }
    assert portions_available(on_hand, ES_KOPI_SUSU) == 0
    assert is_sold_out(on_hand, ES_KOPI_SUSU)
    # Exactly one portion is still available.
    on_hand["milk"] = D("150")
    assert not is_sold_out(on_hand, ES_KOPI_SUSU)


def test_sold_out_missing_or_negative_stock() -> None:
    assert is_sold_out({"coffee_beans": D("100")}, ES_KOPI_SUSU)
    stock = dict.fromkeys(ES_KOPI_SUSU, D("1000"))
    stock["cup"] = D("-3")
    assert portions_available(stock, ES_KOPI_SUSU) == 0


def test_portions_fractional_quantities() -> None:
    assert portions_available({"x": D("1.000")}, {"x": D("0.333")}) == 3


def test_portions_empty_recipe() -> None:
    with pytest.raises(ValueError):
        portions_available({}, {})


@pytest.mark.parametrize(
    ("qty", "unit", "display", "expected"),
    [
        # Values and units as drawn in the stock wireframe (S7) and dashboard (O2).
        (D("800"), "ml", "L", "0,8 L"),
        (D("400"), "g", "kg", "0,4 kg"),
        (D("2400"), "g", "kg", "2,4 kg"),
        (D("180"), "g", "g", "180 g"),
        (D("12000"), "ml", "L", "12 L"),
        (D("150"), "ml", "ml", "150 ml"),
        (D("0"), "pcs", "pcs", "0 pcs"),
    ],
)
def test_format_quantity_with_item_display_unit(
    qty: Decimal, unit: str, display: str, expected: str
) -> None:
    assert format_quantity(qty, unit, display) == expected


def test_display_unit_must_fit_base_unit() -> None:
    with pytest.raises(ValueError, match="does not fit"):
        format_quantity(D("1"), "g", "L")
