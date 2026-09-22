"""Sensor platform for the Moj Elektro integration."""

from datetime import datetime
import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_METER_ID, DOMAIN, VERSION
from .moj_elektro_api import MojElektroApi

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up Moj Elektro sensors from the shared runtime."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    coordinator = runtime["coordinator"]
    api = runtime["api"]
    meter_id = entry.data[CONF_METER_ID]

    sensors = [
        MojElektroSensor(
            coordinator,
            measurement,
            meter_id,
            api,
        )
        for measurement in coordinator.data
    ]
    async_add_entities(sensors)


class MojElektroSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Moj Elektro sensor."""

    def __init__(
        self,
        coordinator,
        measurement_name: str,
        meter_id: str,
        api: MojElektroApi,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

        self.meter_id = meter_id
        self.measurement_name = measurement_name
        self.api = api
        self._last_known_state = None

        self._attr_unique_id = (
            f"{meter_id}-sensor.{DOMAIN}_{measurement_name.lower()}"
        )
        self._attr_name = f"Moj Elektro {measurement_name.replace('_', ' ')}"

        if measurement_name.startswith("casovni_blok"):
            self._attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
            self._attr_device_class = SensorDeviceClass.POWER
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_icon = "mdi:flash"
        elif measurement_name.startswith("souporaba_"):
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_icon = "mdi:account-switch"
        else:
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
            self._attr_device_class = SensorDeviceClass.ENERGY
            if measurement_name.startswith("total_"):
                self._attr_state_class = SensorStateClass.TOTAL_INCREASING
            else:
                self._attr_state_class = SensorStateClass.TOTAL
            self._attr_icon = "mdi:transmission-tower"

    @property
    def device_info(self):
        """Return device information for grouping sensors under one device."""
        return {
            "identifiers": {(DOMAIN, self.meter_id)},
            "name": "Moj Elektro",
            "manufacturer": "Moj Elektro",
            "model": self.meter_id,
            "sw_version": VERSION,
            "entry_type": DeviceEntryType.SERVICE,
        }

    @property
    def last_reset(self):
        """Return the reset point for reset-aware total sensors."""
        if self._attr_state_class != SensorStateClass.TOTAL:
            return None

        metadata = self.api.last_reading_metadata.get(
            self.measurement_name,
            {},
        )
        raw_value = metadata.get("last_reset")
        if not raw_value:
            return None

        try:
            return datetime.fromisoformat(
                str(raw_value).replace("Z", "+00:00")
            )
        except ValueError:
            return None

    @property
    def extra_state_attributes(self):
        """Return safe source and reading-quality metadata."""
        metadata = self.api.last_reading_metadata.get(
            self.measurement_name,
            {},
        )
        if not metadata:
            return None

        attributes = {}
        for key in (
            "source_timestamp",
            "source_date",
            "quality_flags_present",
            "reading_qualities",
        ):
            if key in metadata:
                attributes[key] = metadata[key]

        return attributes or None

    @property
    def native_value(self):
        """Return the native sensor value."""
        data = self.coordinator.data.get(self.measurement_name)
        if data is not None:
            try:
                self._last_known_state = float(data)
                return self._last_known_state
            except (TypeError, ValueError):
                _LOGGER.debug(
                    "Invalid value for %s: %r",
                    self.measurement_name,
                    data,
                )

        if self.measurement_name.startswith("casovni_blok"):
            return self._last_known_state

        return None
