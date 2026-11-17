"""Outlet-local time: allowed zones, labels, display, business dates, and report bounds.

All instants are timezone-aware (``timestamptz``, UTC internally). Display, business dates and
day boundaries always use the outlet's IANA zone (glossary section 3, AC3.4, AC9.9). Indonesia
has no DST, but code still goes through ``zoneinfo`` rather than fixed offsets.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from types import MappingProxyType
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "Asia/Jakarta"

OUTLET_TIMEZONES: MappingProxyType[str, str] = MappingProxyType(
    {
        "Asia/Jakarta": "WIB",
        "Asia/Makassar": "WITA",
        "Asia/Jayapura": "WIT",
    }
)
"""Allowed outlet zones mapped to their Indonesian label."""


class NaiveDatetimeError(ValueError):
    """A datetime without tzinfo was passed where an instant is required."""


def validate_outlet_timezone(tz: str) -> str:
    """Return ``tz`` if it is an allowed outlet zone, else raise ``ValueError``."""
    if tz not in OUTLET_TIMEZONES:
        allowed = ", ".join(OUTLET_TIMEZONES)
        raise ValueError(f"unsupported outlet time zone {tz!r}; allowed: {allowed}")
    return tz


def _zone(tz: str) -> ZoneInfo:
    return ZoneInfo(validate_outlet_timezone(tz))


def _require_aware(dt: datetime) -> datetime:
    if not isinstance(dt, datetime):
        raise TypeError(f"expected a datetime, got {type(dt).__name__}")
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise NaiveDatetimeError("naive datetime given; pass a timezone-aware instant")
    return dt


def zone_label(tz: str) -> str:
    """``WIB`` / ``WITA`` / ``WIT`` for an allowed outlet zone."""
    return OUTLET_TIMEZONES[validate_outlet_timezone(tz)]


def to_local(dt_utc: datetime, tz: str) -> datetime:
    """Convert an aware instant to the outlet's local time (still aware)."""
    return _require_aware(dt_utc).astimezone(_zone(tz))


def format_local_time(dt: datetime, tz: str) -> str:
    """``HH:MM`` in the outlet zone plus its label, e.g. ``19:00 WITA`` (AC9.9)."""
    return f"{to_local(dt, tz):%H:%M} {zone_label(tz)}"


def local_date(dt: datetime, tz: str) -> date:
    """The outlet-local calendar date of an instant (ledger ``business_date``)."""
    return to_local(dt, tz).date()


def local_day_bounds(day: date, tz: str) -> tuple[datetime, datetime]:
    """UTC ``[start, end)`` of the outlet-local day ``day`` for report queries (AC3.4)."""
    if isinstance(day, datetime) or not isinstance(day, date):
        raise TypeError("day must be a date, not a datetime")
    zone = _zone(tz)
    start_local = datetime.combine(day, time.min, tzinfo=zone)
    end_local = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def hour_bucket(dt: datetime, tz: str) -> datetime:
    """The instant truncated to the start of its outlet-local hour (aware, outlet zone).

    Used for orders-per-hour charts (AC7.4); ``.hour`` gives the local hour 0..23.
    """
    return to_local(dt, tz).replace(minute=0, second=0, microsecond=0)
