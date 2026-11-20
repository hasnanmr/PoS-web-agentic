"""O2 dashboard rules without a database (T-071, T-123): periods, opening hours, busy/quiet
hours, and the current-crowd level."""

from __future__ import annotations

from datetime import date, time

from app.core.dashboard import (
    circular_order,
    crowd_level,
    hour_summary,
    mark_hours,
    open_hours,
    period_range,
    previous_range,
)

# The O2 wireframe's "Order per jam · hari ini": 109 orders from 08 to 21.
WIREFRAME = {8: 2, 9: 4, 10: 6, 11: 9, 12: 14, 13: 12, 14: 7, 15: 3, 16: 4, 17: 8, 18: 12, 19: 14,
             20: 10, 21: 4}  # fmt: skip


def test_period_ranges_end_today() -> None:
    thu = date(2026, 11, 19)
    assert period_range(thu, "today") == (thu, thu)
    assert period_range(thu, "week") == (date(2026, 11, 16), thu)  # from Monday
    assert period_range(thu, "month") == (date(2026, 11, 1), thu)


def test_previous_ranges_compare_like_with_like() -> None:
    thu = date(2026, 11, 19)
    assert previous_range(thu, "today") == (date(2026, 11, 18), date(2026, 11, 18))
    assert previous_range(thu, "week") == (date(2026, 11, 9), date(2026, 11, 12))
    assert previous_range(thu, "month") == (date(2026, 10, 1), date(2026, 10, 19))
    # 31 March compares with the whole of February.
    assert previous_range(date(2026, 3, 31), "month") == (date(2026, 2, 1), date(2026, 2, 28))
    assert previous_range(date(2026, 1, 1), "today") == (date(2025, 12, 31), date(2025, 12, 31))


def test_open_hours_include_partial_hours_and_after_midnight() -> None:
    hours = open_hours(
        [
            {"weekday": 1, "opens_at": time(8, 0), "closes_at": time(22, 0)},
            {"weekday": 2, "opens_at": time(7, 30), "closes_at": time(9, 15)},
            {"weekday": 7, "opens_at": time(18, 0), "closes_at": time(2, 0)},  # Sun → Mon 02:00
        ]
    )
    assert hours[1] == set(range(8, 22)) | {0, 1}
    assert hours[2] == {7, 8, 9}
    assert hours[7] == set(range(18, 24))


def test_busy_and_quiet_hours_match_the_wireframe() -> None:
    series = mark_hours(WIREFRAME, range(8, 22))
    busy = [s["hour"] for s in series if s["mark"] == "busy"]
    quiet = [s["hour"] for s in series if s["mark"] == "quiet"]
    assert busy == [12, 13, 18, 19]  # "Jam ramai 12-14 & 18-20"
    assert quiet == [8, 9, 15, 16, 21]  # "Jam sepi 08-10, 15-17, 21-22"
    assert hour_summary(series, "busy") == {"hours": busy, "orders": 52, "share_pct": 48}
    assert hour_summary(series, "quiet") == {"hours": quiet, "orders": 17, "share_pct": 16}


def test_mark_hours_counts_empty_opening_hours_and_ignores_other_hours() -> None:
    series = mark_hours({10: 5, 3: 40}, [9, 10, 11])
    assert [(s["hour"], s["orders"], s["mark"]) for s in series] == [
        (9, 0, "quiet"),
        (10, 5, "busy"),
        (11, 0, "quiet"),
    ]
    assert all(s["mark"] is None for s in mark_hours({}, [9, 10]))
    empty = {"hours": [], "orders": 0, "share_pct": 0}
    assert hour_summary(mark_hours({}, [9, 10]), "busy") == empty


def test_crowd_level_by_tables_then_by_usual_orders() -> None:
    # The wireframe's four outlets.
    assert crowd_level(10, 12, 8, 0) == "ramai"
    assert crowd_level(6, 10, 4, 0) == "normal"
    assert crowd_level(2, 14, 1, 0) == "sepi"
    assert crowd_level(5, 9, 3, 0) == "normal"
    # No tables: active orders against the usual orders for this hour.
    assert crowd_level(0, 0, 4, 3.0) == "ramai"
    assert crowd_level(0, 0, 3, 3.0) == "normal"
    assert crowd_level(0, 0, 1, 3.0) == "sepi"
    assert crowd_level(0, 0, 0, 0) == "sepi"
    assert crowd_level(0, 0, 2, 0) == "normal"


def test_hours_after_midnight_follow_the_evening() -> None:
    assert circular_order([0, 1, 18, 19, 20, 21, 22, 23]) == [18, 19, 20, 21, 22, 23, 0, 1]
    assert circular_order(range(8, 22)) == list(range(8, 22))
    assert circular_order([5]) == [5] and circular_order([]) == []
    marks = mark_hours({23: 10, 0: 10, 19: 1}, [19, 20, 21, 22, 23, 0])
    assert [m["hour"] for m in marks] == [19, 20, 21, 22, 23, 0]
