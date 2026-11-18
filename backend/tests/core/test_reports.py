"""Pure rules behind O9 and S8: comparison period, percent change, buckets, blind count."""

from __future__ import annotations

from datetime import date

import pytest

from app.core.errors import ValidationFailedError
from app.core.proofs import mask_phone
from app.core.reports import bucket, change_pct, previous_period, validate_range
from app.core.shifts import counted_total, difference_kind


@pytest.mark.parametrize(
    ("start", "end", "prev"),
    [
        # O9 "▲ 12% vs 1-17 Okt": month to date compares with the same days a month earlier.
        (date(2026, 11, 1), date(2026, 11, 17), (date(2026, 10, 1), date(2026, 10, 17))),
        # A full month compares with the full previous month.
        (date(2026, 11, 1), date(2026, 11, 30), (date(2026, 10, 1), date(2026, 10, 31))),
        (date(2026, 3, 1), date(2026, 3, 31), (date(2026, 2, 1), date(2026, 2, 28))),
        # Day 31 that the previous month lacks is clamped.
        (date(2026, 3, 1), date(2026, 3, 30), (date(2026, 2, 1), date(2026, 2, 28))),
        # Two months back to back.
        (date(2026, 1, 1), date(2026, 2, 28), (date(2025, 11, 1), date(2025, 12, 31))),
        # Any other range: the same number of days just before.
        (date(2026, 11, 10), date(2026, 11, 16), (date(2026, 11, 3), date(2026, 11, 9))),
        (date(2026, 11, 17), date(2026, 11, 17), (date(2026, 11, 16), date(2026, 11, 16))),
    ],
)
def test_previous_period(start: date, end: date, prev: tuple[date, date]) -> None:
    assert previous_period(start, end) == prev


def test_change_pct() -> None:
    assert change_pct(112, 100) == 12
    assert change_pct(90, 100) == -10
    assert change_pct(5, 0) is None
    assert change_pct(-50, -100) == 50


def test_bucket() -> None:
    wed = date(2026, 11, 18)
    assert bucket(wed, "daily") == wed
    assert bucket(wed, "weekly") == date(2026, 11, 16)  # Monday
    assert bucket(wed, "monthly") == date(2026, 11, 1)


def test_validate_range() -> None:
    validate_range(date(2026, 1, 1), date(2026, 12, 31))
    with pytest.raises(ValidationFailedError):
        validate_range(date(2026, 2, 1), date(2026, 1, 1))
    with pytest.raises(ValidationFailedError):
        validate_range(date(2024, 12, 31), date(2026, 1, 1))


def test_counted_total_matches_s8_example() -> None:
    # S8: 12 x 100k, 6 x 50k, 9 x 20k, 5 x 10k, 4 x 5k, 3 x 2k and Rp 4.400 in coins = Rp 1.760.400.
    count = {"100000": 12, "50000": 6, "20000": 9, "10000": 5, "5000": 4, "2000": 3, "coins": 4400}
    assert counted_total(count) == 1_760_400
    assert counted_total({}) == 0


@pytest.mark.parametrize(
    "count", [{"1000": 2}, {"100000": -1}, {"coins": 1.5}, {"50000": True}, {"2000": 10**6}]
)
def test_counted_total_refuses_bad_input(count: dict) -> None:
    with pytest.raises(ValidationFailedError):
        counted_total(count)


def test_difference_kind() -> None:
    # S8: expected 1.678.400, counted 1.760.400 → +82.000 SURPLUS.
    assert difference_kind(1_760_400 - 1_678_400) == "surplus"
    assert difference_kind(-50_000) == "shortage"
    assert difference_kind(0) == "none"


def test_mask_phone() -> None:
    assert mask_phone("+6281234567221") == "+62 812-xxxx-221"
    assert mask_phone("081234567221") == "081-xxxx-221"
    assert mask_phone(None) is None
    assert mask_phone("123") == "xxxx"
