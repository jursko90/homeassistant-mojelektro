"""Entity registry migration regression tests."""

from types import SimpleNamespace

import custom_components.mojelektro as integration
from custom_components.mojelektro.const import CONF_METER_ID


class FakeRegistry:
    """Minimal entity registry for unique-id migration tests."""

    def __init__(self, entries):
        self.entries = entries
        self.updated = []

    def async_get_entity_id(self, domain, platform, unique_id):
        for entry in self.entries:
            if (
                entry.domain == domain
                and entry.platform == platform
                and entry.unique_id == unique_id
            ):
                return entry.entity_id
        return None

    def async_update_entity(self, entity_id, *, new_unique_id):
        self.updated.append((entity_id, new_unique_id))
        for entry in self.entries:
            if entry.entity_id == entity_id:
                entry.unique_id = new_unique_id
                break


def test_suffixed_legacy_unique_id_is_migrated_without_entity_id_change(monkeypatch):
    """Legacy _2 IDs must keep the existing Home Assistant entity ID."""
    entry = SimpleNamespace(
        entry_id="entry-1",
        data={CONF_METER_ID: "meter-123"},
    )
    legacy = SimpleNamespace(
        domain="sensor",
        platform="mojelektro",
        entity_id="sensor.my_existing_dashboard_entity",
        unique_id="meter-123-sensor.mojelektro_15min_input_2",
    )
    registry = FakeRegistry([legacy])

    monkeypatch.setattr(
        integration.er,
        "async_get",
        lambda hass: registry,
    )
    monkeypatch.setattr(
        integration.er,
        "async_entries_for_config_entry",
        lambda registry_obj, entry_id: list(registry_obj.entries),
    )

    integration._migrate_legacy_sensor_unique_ids(object(), entry)

    assert registry.updated == [
        (
            "sensor.my_existing_dashboard_entity",
            "meter-123-sensor.mojelektro_15min_input",
        )
    ]
    assert legacy.entity_id == "sensor.my_existing_dashboard_entity"


def test_unique_id_migration_does_not_overwrite_existing_target(monkeypatch):
    """A conflicting deterministic target must never be overwritten."""
    entry = SimpleNamespace(
        entry_id="entry-1",
        data={CONF_METER_ID: "meter-123"},
    )
    legacy = SimpleNamespace(
        domain="sensor",
        platform="mojelektro",
        entity_id="sensor.legacy",
        unique_id="meter-123-sensor.mojelektro_15min_input_2",
    )
    existing = SimpleNamespace(
        domain="sensor",
        platform="mojelektro",
        entity_id="sensor.existing",
        unique_id="meter-123-sensor.mojelektro_15min_input",
    )
    registry = FakeRegistry([legacy, existing])

    monkeypatch.setattr(
        integration.er,
        "async_get",
        lambda hass: registry,
    )
    monkeypatch.setattr(
        integration.er,
        "async_entries_for_config_entry",
        lambda registry_obj, entry_id: list(registry_obj.entries),
    )

    integration._migrate_legacy_sensor_unique_ids(object(), entry)

    assert registry.updated == []
    assert legacy.unique_id.endswith("_2")
