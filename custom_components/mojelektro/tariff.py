"""Slovenian network tariff-block rules.

The current five-block schedule follows the Slovenian Energy Agency tariff
methodology. Meter-reading timestamps represent interval ends, so the interval
start is used when selecting the applicable block.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

HIGH_SEASON_MONTHS = frozenset({11, 12, 1, 2})
SLOVENIA_TIME_ZONE = ZoneInfo("Europe/Ljubljana")

# Slovenian public holidays which are legally work-free days.
FIXED_DAYS_OFF = frozenset(
    {
        (1, 1),
        (1, 2),
        (2, 8),
        (4, 27),
        (5, 1),
        (5, 2),
        (6, 25),
        (8, 15),
        (10, 31),
        (11, 1),
        (12, 25),
        (12, 26),
    }
)

# Hour -> time block. Hour ranges are half-open:
# 00-06, 06-12, 12-17, 17-20/22 and 22-24 as defined by the current act.
HIGH_WORKDAY = (
    3, 3, 3, 3, 3, 3,
    1, 1, 1, 1, 1, 1,
    2, 2, 2, 2, 2,
    1, 1, 1,
    2, 2,
    3, 3,
)
HIGH_DAY_OFF = (
    4, 4, 4, 4, 4, 4,
    3, 3, 3, 3, 3, 3,
    4, 4, 4, 4, 4,
    3, 3, 3, 3, 3,
    4, 4,
)
LOW_WORKDAY = (
    5, 5, 5, 5, 5, 5,
    3, 3, 3, 3, 3, 3,
    4, 4, 4, 4, 4,
    3, 3, 3, 3, 3,
    5, 5,
)
LOW_DAY_OFF = (
    5, 5, 5, 5, 5, 5,
    4, 4, 4, 4, 4, 4,
    5, 5, 5, 5, 5,
    4, 4, 4, 4, 4,
    5, 5,
)


def easter_sunday(year: int) -> date:
    """Return Gregorian Easter Sunday."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def is_slovenian_day_off(value: date) -> bool:
    """Return whether the date uses the work-free-day tariff schedule."""
    if value.weekday() >= 5:
        return True

    if (value.month, value.day) in FIXED_DAYS_OFF:
        return True

    easter = easter_sunday(value.year)
    return value == easter + timedelta(days=1)


def expected_quarter_hour_intervals(value: date) -> int:
    """Return the exact number of intervals on a Slovenian calendar day."""
    local_start = datetime.combine(
        value,
        time.min,
        tzinfo=SLOVENIA_TIME_ZONE,
    )
    local_end = datetime.combine(
        value + timedelta(days=1),
        time.min,
        tzinfo=SLOVENIA_TIME_ZONE,
    )
    seconds = (
        local_end.astimezone(timezone.utc)
        - local_start.astimezone(timezone.utc)
    ).total_seconds()
    return int(seconds // (15 * 60))


def slovenian_period_start(
    timestamp: str,
    period: timedelta,
) -> datetime:
    """Return a period start normalized to Slovenian civil time."""
    interval_end = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if interval_end.tzinfo is None:
        raise ValueError("timestamp has no timezone offset")

    # Subtract in UTC so spring-forward and fall-back intervals remain real
    # instants rather than imaginary or ambiguous local wall-clock times.
    return (
        interval_end.astimezone(timezone.utc) - period
    ).astimezone(SLOVENIA_TIME_ZONE)


def slovenian_interval_start(timestamp: str) -> datetime:
    """Return a 15-minute interval start in Slovenian civil time."""
    return slovenian_period_start(timestamp, timedelta(minutes=15))


def network_tariff_block(timestamp: str) -> int:
    """Return network tariff block 1-5 for an interval-end timestamp."""
    interval_start = slovenian_interval_start(timestamp)

    high_season = interval_start.month in HIGH_SEASON_MONTHS
    day_off = is_slovenian_day_off(interval_start.date())

    if high_season:
        schedule = HIGH_DAY_OFF if day_off else HIGH_WORKDAY
    else:
        schedule = LOW_DAY_OFF if day_off else LOW_WORKDAY

    return schedule[interval_start.hour]
