from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.money import (
    MINUS_SIGN,
    InsufficientPaymentError,
    change_due,
    ensure_rupiah,
    format_rupiah,
)


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (0, "Rp 0"),
        (500, "Rp 500"),
        (1_000, "Rp 1.000"),
        (92_400, "Rp 92.400"),
        (1_010_000, "Rp 1.010.000"),
        (-10_000, MINUS_SIGN + " Rp 10.000"),
        (-350_000, MINUS_SIGN + " Rp 350.000"),
    ],
)
def test_format_rupiah_default_matches_wireframe(amount: int, expected: str) -> None:
    assert format_rupiah(amount) == expected


def test_minus_sign_is_u2212() -> None:
    assert ord(MINUS_SIGN) == 0x2212


def test_format_rupiah_compact() -> None:
    assert format_rupiah(92_400, space=False) == "Rp92.400"
    assert format_rupiah(-350_000, space=False) == MINUS_SIGN + "Rp350.000"


@pytest.mark.parametrize("bad", [1.5, True, Decimal(10), "100", None])
def test_ensure_rupiah_rejects_non_int(bad: object) -> None:
    with pytest.raises(TypeError):
        ensure_rupiah(bad)


def test_ensure_rupiah_negative() -> None:
    with pytest.raises(ValueError, match="negative"):
        ensure_rupiah(-1)
    assert ensure_rupiah(-1, allow_negative=True) == -1


def test_format_rupiah_rejects_float() -> None:
    with pytest.raises(TypeError):
        format_rupiah(1000.0)  # type: ignore[arg-type]


def test_change_due_ac11_6() -> None:
    assert change_due(47_000, 50_000) == 3_000
    assert change_due(47_000, 47_000) == 0


def test_change_due_insufficient_ac11_6() -> None:
    with pytest.raises(InsufficientPaymentError) as exc_info:
        change_due(47_000, 46_999)
    assert exc_info.value.shortfall == 1
    assert "Rp 47.000" in str(exc_info.value)


def test_change_due_wireframe_example() -> None:
    # S1 counter: total Rp 92.400, received Rp 100.000, change Rp 7.600.
    assert change_due(92_400, 100_000) == 7_600
