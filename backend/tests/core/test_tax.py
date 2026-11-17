from __future__ import annotations

import pytest

from app.core.tax import Pb1Setting, Quote, line_total, pb1_amount, quote_totals

TEN_PERCENT = Pb1Setting(enabled=True, rate_bps=1000)


def test_ac2_7_delivery_quote() -> None:
    quote = quote_totals(50_000, TEN_PERCENT, delivery_fee=10_000)
    assert quote == Quote(
        subtotal=50_000, pb1_rate_bps=1000, pb1_amount=5_000, delivery_fee=10_000, total=65_000
    )


def test_ac2_7_pickup_has_no_fee() -> None:
    quote = quote_totals(50_000, TEN_PERCENT)
    assert quote.delivery_fee == 0
    assert quote.total == 55_000


def test_ac11_5_pb1_off() -> None:
    quote = quote_totals(50_000, Pb1Setting.off())
    assert quote.pb1_amount == 0
    assert quote.pb1_rate_bps is None
    assert quote.total == 50_000


def test_pb1_off_keeps_stored_rate_but_does_not_apply_it() -> None:
    setting = Pb1Setting(enabled=False, rate_bps=1000)
    assert pb1_amount(50_000, setting) == 0
    assert quote_totals(50_000, setting).pb1_rate_bps is None


def test_delivery_fee_not_in_pb1_base() -> None:
    assert quote_totals(50_000, TEN_PERCENT, delivery_fee=99_999).pb1_amount == 5_000


@pytest.mark.parametrize(
    ("subtotal", "bps", "expected"),
    [
        (25_005, 1000, 2_501),  # exactly .5 rounds up
        (25_004, 1000, 2_500),  # .4 rounds down
        (25_006, 1000, 2_501),
        (1, 1, 0),  # 0.0001 rounds down
        (5_000, 1, 1),  # exactly 0.5 rounds up
        (4_999, 1, 0),
        (0, 1000, 0),
        (84_000, 1000, 8_400),  # wireframe S1
        (12_345, 1, 1),  # 1.2345
        (33_333, 1000, 3_333),
    ],
)
def test_pb1_half_up(subtotal: int, bps: int, expected: int) -> None:
    assert pb1_amount(subtotal, Pb1Setting(enabled=True, rate_bps=bps)) == expected


def test_pb1_large_subtotal_stays_exact() -> None:
    # Beyond float's 2**53 exact-integer range; a float path would be off.
    subtotal = 10**20 + 5
    expected = (subtotal * 1000 + 5_000) // 10_000
    result = pb1_amount(subtotal, TEN_PERCENT)
    assert result == expected == 10**19 + 1
    assert isinstance(result, int)
    assert quote_totals(subtotal, TEN_PERCENT).total == subtotal + expected


def test_pb1_rejects_float_subtotal() -> None:
    with pytest.raises(TypeError):
        pb1_amount(50_000.0, TEN_PERCENT)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("enabled", "rate", "error"),
    [
        (True, None, ValueError),
        (True, 0, ValueError),
        (True, 1001, ValueError),
        (False, 0, ValueError),
        (True, 10.0, TypeError),
        (True, True, TypeError),
    ],
)
def test_pb1_setting_validation(enabled: bool, rate: object, error: type[Exception]) -> None:
    with pytest.raises(error):
        Pb1Setting(enabled=enabled, rate_bps=rate)  # type: ignore[arg-type]


def test_pb1_setting_bounds_ok() -> None:
    assert Pb1Setting(enabled=True, rate_bps=1).effective_rate_bps == 1
    assert Pb1Setting(enabled=True, rate_bps=1000).effective_rate_bps == 1000
    assert Pb1Setting().enabled is False


def test_quote_rejects_negative() -> None:
    with pytest.raises(ValueError):
        quote_totals(-1, TEN_PERCENT)
    with pytest.raises(ValueError):
        quote_totals(1_000, TEN_PERCENT, delivery_fee=-1)


def test_line_total_ac4_5() -> None:
    # Es Kopi Susu Rp25.000 + extra shot Rp5.000.
    assert line_total(25_000, [5_000], 1) == 30_000
    assert line_total(25_000, [5_000, 0], 2) == 60_000
    assert line_total(22_000, [], 3) == 66_000


@pytest.mark.parametrize("qty", [0, -1])
def test_line_total_rejects_bad_quantity(qty: int) -> None:
    with pytest.raises(ValueError):
        line_total(25_000, [], qty)


def test_line_total_rejects_negative_addon() -> None:
    with pytest.raises(ValueError):
        line_total(25_000, [-1_000], 1)
