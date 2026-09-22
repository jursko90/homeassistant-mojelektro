"""Binary sensors for Moj Elektro."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    CONF_METER_ID,
    CONF_STALE_AFTER_HOURS,
    DEFAULT_STALE_AFTER_HOURS,
    DOMAIN,
    VERSION,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up Moj Elektro diagnostic binary sensors."""
    runtime = entry.runtime_data
    async_add_entities(
        [
            MojElektroDataStaleBinarySensor(
                runtime.coordinator,
                runtime.api,
                entry.data[CONF_METER_ID],
                entry.options.get(
                    CONF_STALE_AFTER_HOURS,
                    DEFAULT_STALE_AFTER_HOURS,
                ),
            )
        ]
    )


class MojElektroDataStaleBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Report whether Moj Elektro source data has become stale."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_icon = "mdi:clock-alert-outline"
    _attr_translation_key = "data_stale"

    def __init__(
        self,
        coordinator,
        api,
        meter_id: str,
        stale_after_hours: int,
    ) -> None:
        """Initialize the stale-data binary sensor."""
        super().__init__(coordinator)
        self.api = api
        self.meter_id = meter_id
        self.stale_after_hours = int(stale_after_hours)
        self._attr_unique_id = (
            f"{meter_id}-binary_sensor.{DOMAIN}_data_stale"
        )

    @property
    def device_info(self):
        """Return the Moj Elektro device."""
        return {
            "identifiers": {(DOMAIN, self.meter_id)},
            "name": "Moj Elektro",
            "manufacturer": "Moj Elektro",
            "model": "Moj Elektro API",
            "sw_version": VERSION,
            "entry_type": DeviceEntryType.SERVICE,
        }

    @property
    def is_on(self):
        """Return True when the newest published reading exceeds the threshold."""
        latest = self.api.latest_source_timestamp()
        if latest is None:
            return None

        age = dt_util.now() - latest
        return age.total_seconds() > self.stale_after_hours * 3600

    @property
    def extra_state_attributes(self):
        """Expose the configured threshold and current source timestamp."""
        latest = self.api.latest_source_timestamp()
        attributes = {
            "stale_after_hours": self.stale_after_hours,
        }
        if latest is not None:
            attributes["source_timestamp"] = latest.isoformat()
        return attributes
