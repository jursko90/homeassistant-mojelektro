"""Tests for the Slovenian network tariff profile."""

from datetime import date

import pytest

from custom_components.mojelektro.tariff import (
    expected_quarter_hour_intervals,
    is_slovenian_day_off,
    network_tariff_block,
)


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        # Higher season, workday (Monday 12 January 2026).
        ("2026-01-12T06:15:00+01:00", 1),  # interval 06:00-06:15
        ("2026-01-12T05:15:00Z", 1),  # same instant, expressed in UTC
        ("2026-01-12T12:15:00+01:00", 2),
        ("2026-01-12T17:15:00+01:00", 1),
        ("2026-01-12T20:15:00+01:00", 2),
        ("2026-01-12T22:15:00+01:00", 3),
        # Higher season, day off (Sunday 11 January 2026).
        ("2026-01-11T06:15:00+01:00", 3),
        ("2026-01-11T12:15:00+01:00", 4),
        ("2026-01-11T17:15:00+01:00", 3),
        ("2026-01-11T22:15:00+01:00", 4),
        # Lower season, workday (Monday 13 July 2026).
        ("2026-07-13T06:15:00+02:00", 3),
        ("2026-07-13T12:15:00+02:00", 4),
        ("2026-07-13T17:15:00+02:00", 3),
        ("2026-07-13T22:15:00+02:00", 5),
        # Lower season, day off (Sunday 12 July 2026).
        ("2026-07-12T06:15:00+02:00", 4),
        ("2026-07-12T12:15:00+02:00", 5),
        ("2026-07-12T17:15:00+02:00", 4),
        ("2026-07-12T22:15:00+02:00", 5),
    ],
)
def test_current_network_tariff_schedule(timestamp, expected):
    """Official schedule boundaries should map to the correct block."""
    assert network_tariff_block(timestamp) == expected


def test_easter_monday_is_day_off():
    """Easter Monday is a statutory work-free day in Slovenia."""
    assert is_slovenian_day_off(date(2026, 4, 6))


def test_non_work_free_state_holiday_is_not_forced_day_off():
    """A state holiday which is not work-free should keep weekday rules."""
    # Primož Trubar Day is a state holiday but explicitly not work-free.
    assert not is_slovenian_day_off(date(2026, 6, 8))


def test_expected_interval_count_follows_slovenian_dst():
    """Only actual DST transition days may contain 92 or 100 intervals."""
    assert expected_quarter_hour_intervals(date(2026, 3, 29)) == 92
    assert expected_quarter_hour_intervals(date(2026, 9, 19)) == 96
    assert expected_quarter_hour_intervals(date(2026, 10, 25)) == 100
