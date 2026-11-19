"""The pure availability helpers: windows, expansion, DST and the daily cap."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.services.planning.availability import (
    DayException,
    Rule,
    Window,
    check_windows,
    expand,
    format_minute,
    local_to_utc,
    parse_minute,
    weekly_minutes,
)

SAST = ZoneInfo("Africa/Johannesburg")
LONDON = ZoneInfo("Europe/London")
MONDAY = date(2026, 11, 16)


def w(start: str, end: str) -> Window:
    return Window(parse_minute(start), parse_minute(end))


def utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


# --- windows ---------------------------------------------------------------------------


def test_times_parse_and_format_including_midnight_as_24_00() -> None:
    assert parse_minute("09:30") == 570
    assert parse_minute("00:00") == 0
    assert parse_minute("24:00") == 1440
    assert format_minute(1440) == "24:00"
    assert format_minute(65) == "01:05"


@pytest.mark.parametrize("text", ["9:00", "24:01", "12:60", "ab:cd", "", "12-00"])
def test_bad_times_are_refused(text: str) -> None:
    with pytest.raises(ValueError):
        parse_minute(text)


def test_windows_come_back_sorted_and_may_touch() -> None:
    assert check_windows([w("12:00", "13:00"), w("09:00", "12:00")]) == [
        w("09:00", "12:00"),
        w("12:00", "13:00"),
    ]


@pytest.mark.parametrize(
    "windows",
    [
        [Window(600, 600)],  # empty
        [Window(700, 600)],  # backwards
        [Window(1380, 1500)],  # crosses midnight: split it instead
        [w("09:00", "12:00"), w("11:00", "13:00")],  # overlap
        [w("09:00", "12:00"), w("10:00", "11:00")],  # one inside another
    ],
)
def test_bad_windows_are_refused(windows: list[Window]) -> None:
    with pytest.raises(ValueError):
        check_windows(windows)


# --- expansion -------------------------------------------------------------------------


def test_rules_become_utc_intervals_in_the_users_timezone() -> None:
    days = expand([Rule(0, w("18:00", "20:30"))], {}, MONDAY, MONDAY, SAST, 180)

    assert len(days) == 1
    assert days[0].source == "rules"
    assert [(i.start, i.end) for i in days[0].intervals] == [
        (utc(2026, 11, 16, 16, 0), utc(2026, 11, 16, 18, 30))  # SAST is UTC+2
    ]
    assert days[0].free_minutes == 150
    assert days[0].available_minutes == 150


def test_a_day_without_rules_is_empty_not_missing() -> None:
    days = expand([Rule(0, w("09:00", "10:00"))], {}, MONDAY, MONDAY.replace(day=22), SAST, 180)

    assert [d.date.weekday() for d in days] == [0, 1, 2, 3, 4, 5, 6]
    assert [d.free_minutes for d in days] == [60, 0, 0, 0, 0, 0, 0]
    assert all(d.intervals == () for d in days[1:])


def test_the_daily_cap_limits_whats_available_not_the_intervals() -> None:
    rules = [Rule(0, w("08:00", "12:00")), Rule(0, w("13:00", "17:00"))]

    [day] = expand(rules, {}, MONDAY, MONDAY, SAST, 180)

    assert day.free_minutes == 480
    assert day.available_minutes == 180
    assert len(day.intervals) == 2


def test_an_exception_replaces_the_rules_for_its_date_only() -> None:
    rules = [Rule(0, w("09:00", "12:00"))]
    exceptions = {MONDAY: DayException(unavailable=False, windows=(w("14:00", "15:00"),))}

    days = expand(rules, exceptions, MONDAY, MONDAY.replace(day=23), SAST, 600)

    assert days[0].source == "exception"
    assert days[0].free_minutes == 60
    assert days[0].intervals[0].start == utc(2026, 11, 16, 12, 0)
    # The next Monday is back on the rules.
    assert (days[7].source, days[7].free_minutes) == ("rules", 180)


def test_an_unavailable_day_has_nothing_even_with_rules() -> None:
    exceptions = {MONDAY: DayException(unavailable=True)}

    [day] = expand([Rule(0, w("09:00", "12:00"))], exceptions, MONDAY, MONDAY, SAST, 180)

    assert (day.source, day.intervals, day.free_minutes, day.available_minutes) == (
        "unavailable",
        (),
        0,
        0,
    )


def test_a_window_to_midnight_ends_at_the_next_local_midnight() -> None:
    [day] = expand([Rule(0, w("22:00", "24:00"))], {}, MONDAY, MONDAY, SAST, 600)

    assert day.intervals[0].end == utc(2026, 11, 16, 22, 0)  # 00:00 Tuesday SAST
    assert day.free_minutes == 120


def test_a_window_from_midnight_belongs_to_its_own_day() -> None:
    days = expand([Rule(1, w("00:00", "01:00"))], {}, MONDAY, MONDAY.replace(day=17), SAST, 600)

    assert days[0].free_minutes == 0
    assert days[1].intervals[0].start == utc(2026, 11, 16, 22, 0)


# --- DST (South Africa has none; Europe/London does) -----------------------------------

SPRING = date(2026, 3, 29)  # Europe/London: 01:00 GMT becomes 02:00 BST
AUTUMN = date(2026, 10, 25)  # Europe/London: 02:00 BST becomes 01:00 GMT


def test_a_window_across_the_spring_change_is_an_hour_shorter() -> None:
    [day] = expand([Rule(SPRING.weekday(), w("00:30", "03:00"))], {}, SPRING, SPRING, LONDON, 600)

    assert [(i.start, i.end) for i in day.intervals] == [
        (utc(2026, 3, 29, 0, 30), utc(2026, 3, 29, 2, 0))
    ]
    assert day.free_minutes == 90


def test_a_skipped_local_time_moves_forward_to_the_change() -> None:
    # 01:30 doesn't exist on the spring day; it starts when the clocks reach 02:00 BST.
    assert local_to_utc(SPRING, parse_minute("01:30"), LONDON) == utc(2026, 3, 29, 1, 0)
    [day] = expand([Rule(SPRING.weekday(), w("01:30", "03:00"))], {}, SPRING, SPRING, LONDON, 600)
    assert day.free_minutes == 60


def test_a_window_inside_the_skipped_hour_has_no_time() -> None:
    [day] = expand([Rule(SPRING.weekday(), w("01:00", "02:00"))], {}, SPRING, SPRING, LONDON, 600)

    assert (day.intervals, day.free_minutes) == ((), 0)


def test_a_window_across_the_autumn_change_is_an_hour_longer() -> None:
    [day] = expand([Rule(AUTUMN.weekday(), w("00:30", "03:00"))], {}, AUTUMN, AUTUMN, LONDON, 600)

    assert [(i.start, i.end) for i in day.intervals] == [
        (utc(2026, 10, 24, 23, 30), utc(2026, 10, 25, 3, 0))
    ]
    assert day.free_minutes == 210


def test_a_repeated_local_time_is_its_first_occurrence() -> None:
    assert local_to_utc(AUTUMN, parse_minute("01:30"), LONDON) == utc(2026, 10, 25, 0, 30)


def test_the_same_rule_keeps_its_wall_clock_time_either_side_of_a_change() -> None:
    rule = Rule(6, w("18:00", "19:00"))  # Sundays

    days = expand([rule], {}, date(2026, 3, 22), date(2026, 3, 29), LONDON, 600)

    assert days[0].intervals[0].start == utc(2026, 3, 22, 18, 0)  # GMT
    assert days[-1].intervals[0].start == utc(2026, 3, 29, 17, 0)  # BST
    assert days[0].free_minutes == days[-1].free_minutes == 60


def test_the_daily_cap_applies_to_real_time_on_a_long_day() -> None:
    [day] = expand([Rule(AUTUMN.weekday(), w("00:00", "03:00"))], {}, AUTUMN, AUTUMN, LONDON, 200)

    assert (day.free_minutes, day.available_minutes) == (240, 200)


# --- the week from the rules -----------------------------------------------------------


def test_a_typical_week_sums_each_day_capped() -> None:
    rules = [
        Rule(0, w("18:00", "20:00")),
        Rule(0, w("20:30", "22:30")),  # Monday: 4 h, capped at 3 h
        Rule(2, w("09:00", "10:30")),
    ]

    assert weekly_minutes(rules, 180) == 180 + 90
    assert weekly_minutes([], 180) == 0
