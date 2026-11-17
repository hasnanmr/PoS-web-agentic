from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.core.localtime import (
    DEFAULT_TIMEZONE,
    OUTLET_TIMEZONES,
    NaiveDatetimeError,
    format_local_time,
    hour_bucket,
    local_date,
    local_day_bounds,
    to_local,
    validate_outlet_timezone,
    zone_label,
)


def test_constants() -> None:
    assert DEFAULT_TIMEZONE == "Asia/Jakarta"
    assert dict(OUTLET_TIMEZONES) == {
        "Asia/Jakarta": "WIB",
        "Asia/Makassar": "WITA",
        "Asia/Jayapura": "WIT",
    }


@pytest.mark.parametrize("tz", ["UTC", "Asia/Singapore", "asia/jakarta", ""])
def test_validate_rejects(tz: str) -> None:
    with pytest.raises(ValueError):
        validate_outlet_timezone(tz)


def test_zone_label() -> None:
    assert zone_label("Asia/Makassar") == "WITA"
    assert zone_label("Asia/Jayapura") == "WIT"


def test_ac9_9_makassar_booking() -> None:
    booking = datetime(2026, 11, 17, 19, 0, tzinfo=ZoneInfo("Asia/Makassar"))
    assert format_local_time(booking, "Asia/Makassar") == "19:00 WITA"
    # Same instant stored as UTC still shows 19:00 WITA.
    assert format_local_time(booking.astimezone(UTC), "Asia/Makassar") == "19:00 WITA"
    assert format_local_time(booking, "Asia/Jakarta") == "18:00 WIB"


def test_late_utc_falls_on_next_local_day() -> None:
    instant = datetime(2026, 11, 1, 23, 30, tzinfo=UTC)
    assert local_date(instant, "Asia/Jakarta") == date(2026, 11, 2)
    assert to_local(instant, "Asia/Jakarta").hour == 6


@pytest.mark.parametrize(
    ("tz", "offset"),
    [("Asia/Jakarta", 7), ("Asia/Makassar", 8), ("Asia/Jayapura", 9)],
)
def test_local_day_bounds(tz: str, offset: int) -> None:
    start, end = local_day_bounds(date(2026, 11, 1), tz)
    assert start == datetime(2026, 11, 1, tzinfo=UTC) - timedelta(hours=offset)
    assert end - start == timedelta(days=1)
    assert start.tzinfo is UTC
    assert local_date(start, tz) == date(2026, 11, 1)
    assert local_date(end - timedelta(microseconds=1), tz) == date(2026, 11, 1)
    assert local_date(end, tz) == date(2026, 11, 2)


def test_local_day_bounds_rejects_datetime() -> None:
    with pytest.raises(TypeError):
        local_day_bounds(datetime(2026, 11, 1, tzinfo=UTC), "Asia/Jakarta")


def test_hour_bucket() -> None:
    instant = datetime(2026, 11, 17, 5, 47, 12, 5, tzinfo=UTC)
    bucket = hour_bucket(instant, "Asia/Jakarta")
    assert bucket.hour == 12
    assert (bucket.minute, bucket.second, bucket.microsecond) == (0, 0, 0)
    assert bucket == datetime(2026, 11, 17, 5, tzinfo=UTC)


@pytest.mark.parametrize(
    "func",
    [to_local, format_local_time, local_date, hour_bucket],
)
def test_rejects_naive(func: object) -> None:
    naive = datetime(2026, 11, 17, 12, 0)
    with pytest.raises(NaiveDatetimeError):
        func(naive, "Asia/Jakarta")  # type: ignore[operator]


def test_accepts_fixed_offset_aware() -> None:
    instant = datetime(2026, 11, 17, 12, 0, tzinfo=timezone(timedelta(hours=7)))
    assert format_local_time(instant, "Asia/Jayapura") == "14:00 WIT"
