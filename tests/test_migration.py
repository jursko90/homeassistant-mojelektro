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
        CONF_DECIMAL: 3,
    }
    assert entry.options[CONF_DECIMAL] == 3


def test_v1_migration_preserves_existing_option():
    """A user-saved option must win over legacy config-entry data."""
    entry = FakeEntry()
    entry.options = {CONF_DECIMAL: 6}

    assert asyncio.run(async_migrate_entry(FakeHass(), entry))

    assert entry.version == 2
    assert entry.data[CONF_DECIMAL] == 3
    assert entry.options[CONF_DECIMAL] == 6


def test_v2_migration_is_idempotent():
    """Already-migrated entries must not be rewritten or lose settings."""
    entry = FakeEntry()
    entry.version = 2
    entry.options = {CONF_DECIMAL: 7}
    before_data = dict(entry.data)
    before_options = dict(entry.options)

    assert asyncio.run(async_migrate_entry(FakeHass(), entry))

    assert entry.version == 2
    assert entry.data == before_data
    assert entry.options == before_options


def test_future_entry_version_is_rejected():
    """Older integration code must not silently downgrade a newer schema."""
    entry = FakeEntry()
    entry.version = 3

    assert not asyncio.run(async_migrate_entry(FakeHass(), entry))
