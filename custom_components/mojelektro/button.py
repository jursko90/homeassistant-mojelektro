"""Button platform for Moj Elektro."""

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_METER_ID, DOMAIN, VERSION


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up the manual refresh button."""
    runtime = entry.runtime_data
    async_add_entities(
        [
            MojElektroRefreshButton(
                runtime.coordinator,
                entry.data[CONF_METER_ID],
            )
        ]
    )


class MojElektroRefreshButton(CoordinatorEntity, ButtonEntity):
    """Button that requests an immediate Moj Elektro refresh."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_icon = "mdi:refresh"
    _attr_translation_key = "refresh_data"

    def __init__(self, coordinator, meter_id: str) -> None:
        """Initialize the refresh button."""
        super().__init__(coordinator)
        self.meter_id = meter_id
        self._attr_unique_id = f"{meter_id}-button.{DOMAIN}_refresh_data"

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

    async def async_press(self) -> None:
        """Request a fresh API update immediately."""
        await self.coordinator.async_request_refresh()
