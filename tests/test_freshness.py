"""Freshness diagnostics tests for Moj Elektro."""

from datetime import datetime, timedelta, timezone

from custom_components.mojelektro.binary_sensor import is_data_stale


def test_stale_threshold_boundary():
    """Data exactly on the threshold is not stale; older data is."""
    now = datetime(2026, 9, 22, 8, 0, tzinfo=timezone.utc)

    assert not is_data_stale(
        now - timedelta(hours=48),
        now,
        48,
    )
    assert is_data_stale(
        now - timedelta(hours=48, seconds=1),
        now,
        48,
    )


def test_custom_stale_threshold():
    """Configured threshold must be respected."""
    now = datetime(2026, 9, 22, 8, 0, tzinfo=timezone.utc)
    latest = now - timedelta(hours=30)

    assert is_data_stale(latest, now, 24)
    assert not is_data_stale(latest, now, 48)
