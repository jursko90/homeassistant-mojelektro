"""Regression tests for the Moj Elektro refresh button."""

from custom_components.mojelektro.button import MojElektroRefreshButton


def test_manual_refresh_remains_available_after_update_failure():
    """Users must be able to retry manually when the coordinator is offline."""
    button = object.__new__(MojElektroRefreshButton)

    assert button.available is True
