"""Diagnostics support for Moj Elektro."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_METER_ID, CONF_TOKEN, VERSION

TO_REDACT = {CONF_TOKEN, CONF_METER_ID}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return safe diagnostics without credentials or metering values."""
    runtime = getattr(entry, "runtime_data", None)
    api = runtime.api if runtime is not None else None

    diagnostics: dict[str, Any] = {
        "integration_version": VERSION,
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "runtime_available": api is not None,
    }

    if api is not None:
        diagnostics.update(
            {
                "available_reading_tags": sorted(
                    api._reading_types_by_tag or {}
                ),
                "reading_quality_catalog": dict(
                    api._reading_quality_descriptions
                ),
                "latest_reading_metadata": dict(
                    api.last_reading_metadata
                ),
                "safe_meter_metadata": dict(
                    api.safe_meter_metadata
                ),
            }
        )

    return diagnostics
