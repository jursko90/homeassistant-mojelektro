"""Moj Elektro integration."""

import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from .const import (
    CONTRACTED_POWER_SENSORS,
    DAILY_SENSORS,
    DOMAIN,
    FIFTEEN_MINUTE_SENSORS,
    TARIFF_BLOCK_SENSORS,
    TOTAL_REGISTER_SENSORS,
    CONF_METER_ID,
)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS = [Platform.SENSOR]


def _expected_sensor_names() -> list[str]:
    """Return all sensor keys ever created by this integration."""
    names = list(FIFTEEN_MINUTE_SENSORS.values())

    for sensor in DAILY_SENSORS.values():
        names.append(sensor)
        names.append(sensor.replace("daily_", "monthly_", 1))

    names.extend(TARIFF_BLOCK_SENSORS.values())
    names.extend(TOTAL_REGISTER_SENSORS.values())
    names.extend(CONTRACTED_POWER_SENSORS)
    return names


def _migrate_legacy_sensor_unique_ids(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Migrate legacy suffixed unique IDs without changing entity IDs."""
    meter_id = entry.data[CONF_METER_ID]
    registry = er.async_get(hass)
    registry_entries = er.async_entries_for_config_entry(
        registry,
        entry.entry_id,
    )

    for measurement_name in _expected_sensor_names():
        desired_unique_id = (
            f"{meter_id}-sensor.{DOMAIN}_{measurement_name.lower()}"
        )
        legacy_pattern = re.compile(
            rf"^{re.escape(desired_unique_id)}_(?P<suffix>(?:[2-9]|[1-9]\d+))$"
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
            hass.config_entries.async_update_entry(
                entry,
                unique_id=meter_id,
            )

    _migrate_legacy_sensor_unique_ids(hass, entry)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Moj Elektro config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry,
        PLATFORMS,
    )
    if unload_ok:
        domain_data = hass.data.get(DOMAIN, {})
        domain_data.pop(entry.entry_id, None)
        if not domain_data:
            hass.data.pop(DOMAIN, None)
    return unload_ok
