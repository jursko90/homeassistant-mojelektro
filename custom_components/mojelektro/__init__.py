"""Moj Elektro integration."""

import json
import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_METER_ID,
    DOMAIN,
    SETUP_TAG_15_ARRAY,
    SETUP_TAG_ARRAY,
    SETUP_TAG_BLOCKS_ARRAY,
)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS = [Platform.SENSOR]


def _expected_sensor_names() -> list[str]:
    """Return all sensor keys created by this integration."""
    names: list[str] = []

    for item in json.loads(SETUP_TAG_15_ARRAY):
        names.append(item["sensor"])

    for item in json.loads(SETUP_TAG_ARRAY):
        names.append(item["sensor"])
        names.append(item["sensor"].replace("daily_", "monthly_", 1))

    for item in json.loads(SETUP_TAG_BLOCKS_ARRAY):
        names.append(item["sensor"])

    names.extend(f"casovni_blok_{block_number}" for block_number in range(1, 6))
    return names


def _migrate_legacy_sensor_unique_ids(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Migrate legacy suffixed unique IDs without changing entity IDs."""
    meter_id = entry.data[CONF_METER_ID]
    registry = er.async_get(hass)
    registry_entries = er.async_entries_for_config_entry(registry, entry.entry_id)

    for measurement_name in _expected_sensor_names():
        desired_unique_id = (
            f"{meter_id}-sensor.{DOMAIN}_{measurement_name.lower()}"
        )
        legacy_pattern = re.compile(
            rf"^{re.escape(desired_unique_id)}_(?P<suffix>[2-9]\d*)$"
        )

        for entity_entry in registry_entries:
            if entity_entry.domain != Platform.SENSOR:
                continue
            if not legacy_pattern.fullmatch(entity_entry.unique_id):
                continue

            existing_entity_id = registry.async_get_entity_id(
                entity_entry.domain,
                entity_entry.platform,
                desired_unique_id,
            )
            if existing_entity_id not in (None, entity_entry.entity_id):
                continue

            registry.async_update_entity(
                entity_entry.entity_id,
                new_unique_id=desired_unique_id,
            )
            break


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration domain."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Moj Elektro from a config entry."""
    if entry.unique_id is None:
        meter_id = entry.data[CONF_METER_ID]
        duplicate_entries = [
            existing_entry
            for existing_entry in hass.config_entries.async_entries(DOMAIN)
            if existing_entry.entry_id != entry.entry_id
            and existing_entry.data.get(CONF_METER_ID) == meter_id
        ]
        if not duplicate_entries:
            hass.config_entries.async_update_entry(entry, unique_id=meter_id)

    _migrate_legacy_sensor_unique_ids(hass, entry)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Moj Elektro config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
