"""Config-entry migration tests for Moj Elektro."""

import asyncio

from custom_components.mojelektro import async_migrate_entry
from custom_components.mojelektro.const import (
    CONF_DECIMAL,
    CONF_METER_ID,
    CONF_TOKEN,
)


class FakeConfigEntries:
    """Minimal config-entry manager used by migration tests."""

    def async_update_entry(self, entry, **changes):
        for key, value in changes.items():
            setattr(entry, key, value)


class FakeHass:
    """Minimal Home Assistant object used by migration tests."""

    def __init__(self):
        self.config_entries = FakeConfigEntries()


class FakeEntry:
    """Minimal legacy config entry."""

    version = 1

    def __init__(self):
        self.data = {
            CONF_TOKEN: "secret-token",
            CONF_METER_ID: "meter-id",
            CONF_DECIMAL: 3,
        }
        self.options = {}


def test_v1_migration_moves_decimal_to_options():
    """0.2.x runtime settings should move out of credential data."""
    entry = FakeEntry()

    assert asyncio.run(async_migrate_entry(FakeHass(), entry))

    assert entry.version == 2
    assert entry.data == {
        CONF_TOKEN: "secret-token",
        CONF_METER_ID: "meter-id",
    }
    assert entry.options[CONF_DECIMAL] == 3


def test_v1_migration_preserves_existing_option():
    """A user-saved option must win over legacy config-entry data."""
    entry = FakeEntry()
    entry.options = {CONF_DECIMAL: 6}

    assert asyncio.run(async_migrate_entry(FakeHass(), entry))

    assert entry.version == 2
    assert CONF_DECIMAL not in entry.data
    assert entry.options[CONF_DECIMAL] == 6
