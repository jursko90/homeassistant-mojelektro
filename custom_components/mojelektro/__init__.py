"""Moj Elektro integration."""

from dataclasses import dataclass
from datetime import timedelta
import logging
import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_DECIMAL,
    CONF_ENABLE_15MIN,
    CONF_ENABLE_CONTRACTED_POWER,
    CONF_ENABLE_DAILY,
    CONF_ENABLE_SOUPORABA,
    CONF_ENABLE_TARIFF_BLOCKS,
    CONF_ENABLE_TOTAL,
    CONF_LOOKBACK_DAYS,
    CONF_METER_ID,
    CONF_TOKEN,
    CONF_UPDATE_INTERVAL,
    CONTRACTED_POWER_SENSORS,
    DAILY_SENSORS,
    DEFAULT_DECIMAL,
    DEFAULT_ENABLE_15MIN,
    DEFAULT_ENABLE_CONTRACTED_POWER,
    DEFAULT_ENABLE_DAILY,
    DEFAULT_ENABLE_SOUPORABA,
    DEFAULT_ENABLE_TARIFF_BLOCKS,
    DEFAULT_ENABLE_TOTAL,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    FIFTEEN_MINUTE_SENSORS,
    SOUPORABA_SENSORS,
    TARIFF_BLOCK_SENSORS,
    TOTAL_REGISTER_SENSORS,
)
from .moj_elektro_api import (
    MojElektroApi,
    MojElektroAuthError,
    MojElektroError,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS = [Platform.SENSOR, Platform.BUTTON, Platform.BINARY_SENSOR]


@dataclass
class MojElektroRuntimeData:
    """Runtime objects shared by Moj Elektro platforms."""

    api: MojElektroApi
    coordinator: DataUpdateCoordinator


def _expected_sensor_names() -> list[str]:
    """Return all sensor keys ever created by this integration."""
    names = list(FIFTEEN_MINUTE_SENSORS.values())

    for sensor in DAILY_SENSORS.values():
        names.append(sensor)
        names.append(sensor.replace("daily_", "monthly_", 1))

    names.extend(TARIFF_BLOCK_SENSORS.values())
    names.extend(TOTAL_REGISTER_SENSORS.values())
    names.extend(CONTRACTED_POWER_SENSORS)
    names.extend(SOUPORABA_SENSORS.values())
    return names


def _migrate_legacy_sensor_unique_ids(
    hass: HomeAssistant,
    entry: ConfigEntry,
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


async def async_migrate_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    """Migrate legacy config-entry data to the 0.3.0 schema."""
    if entry.version > 2:
        return False

    if entry.version < 2:
        data = dict(entry.data)
        options = dict(entry.options)

        legacy_decimal = data.pop(CONF_DECIMAL, None)
        if legacy_decimal is not None and CONF_DECIMAL not in options:
            options[CONF_DECIMAL] = legacy_decimal

        hass.config_entries.async_update_entry(
            entry,
            data=data,
            options=options,
            version=2,
        )

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

    options = entry.options
    meter_id = entry.data[CONF_METER_ID]
    api = MojElektroApi(
        entry.data[CONF_TOKEN],
        meter_id,
        options.get(
            CONF_DECIMAL,
            entry.data.get(CONF_DECIMAL, DEFAULT_DECIMAL),
        ),
        async_get_clientsession(hass),
        lookback_days=options.get(
            CONF_LOOKBACK_DAYS,
            DEFAULT_LOOKBACK_DAYS,
        ),
        enable_15min=options.get(
            CONF_ENABLE_15MIN,
            DEFAULT_ENABLE_15MIN,
        ),
        enable_daily=options.get(
            CONF_ENABLE_DAILY,
            DEFAULT_ENABLE_DAILY,
        ),
        enable_total=options.get(
            CONF_ENABLE_TOTAL,
            DEFAULT_ENABLE_TOTAL,
        ),
        enable_tariff_blocks=options.get(
            CONF_ENABLE_TARIFF_BLOCKS,
            DEFAULT_ENABLE_TARIFF_BLOCKS,
        ),
        enable_contracted_power=options.get(
            CONF_ENABLE_CONTRACTED_POWER,
            DEFAULT_ENABLE_CONTRACTED_POWER,
        ),
        enable_souporaba=options.get(
            CONF_ENABLE_SOUPORABA,
            DEFAULT_ENABLE_SOUPORABA,
        ),
    )

    async def async_update_data():
        """Fetch data and translate API errors to Home Assistant errors."""
        try:
            return await api.getData()
        except MojElektroAuthError as err:
            raise ConfigEntryAuthFailed(
                "Moj Elektro authentication failed"
            ) from err
        except MojElektroError as err:
            raise UpdateFailed(str(err)) from err
        except Exception as err:
            raise UpdateFailed(
                f"Unexpected Moj Elektro update error: {err}"
            ) from err

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}_{meter_id}",
        update_method=async_update_data,
        update_interval=timedelta(
            minutes=options.get(
                CONF_UPDATE_INTERVAL,
                DEFAULT_UPDATE_INTERVAL,
            )
        ),
    )

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = MojElektroRuntimeData(
        api=api,
        coordinator=coordinator,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Moj Elektro config entry."""
    return await hass.config_entries.async_unload_platforms(
        entry,
        PLATFORMS,
    )
