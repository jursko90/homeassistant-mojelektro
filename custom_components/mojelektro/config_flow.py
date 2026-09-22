"""Config and options flows for Moj Elektro."""

import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_DECIMAL,
    CONF_ENABLE_15MIN,
    CONF_ENABLE_CONTRACTED_POWER,
    CONF_ENABLE_DAILY,
    CONF_ENABLE_TOTAL,
    CONF_EXTRA_READING_TAGS,
    CONF_ENABLE_TARIFF_BLOCKS,
    CONF_ENABLE_SOUPORABA,
    CONF_LOOKBACK_DAYS,
    CONF_METER_ID,
    CONF_TOKEN,
    CONF_STALE_AFTER_HOURS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_DECIMAL,
    DEFAULT_ENABLE_15MIN,
    DEFAULT_ENABLE_CONTRACTED_POWER,
    DEFAULT_ENABLE_DAILY,
    DEFAULT_ENABLE_TOTAL,
    DEFAULT_EXTRA_READING_TAGS,
    DEFAULT_ENABLE_TARIFF_BLOCKS,
    DEFAULT_ENABLE_SOUPORABA,
    DEFAULT_LOOKBACK_DAYS,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_STALE_AFTER_HOURS,
    DOMAIN,
    DAILY_SENSORS,
    FIFTEEN_MINUTE_SENSORS,
    MAX_LOOKBACK_DAYS,
    MAX_UPDATE_INTERVAL,
    MAX_STALE_AFTER_HOURS,
    MIN_LOOKBACK_DAYS,
    MIN_UPDATE_INTERVAL,
    MIN_STALE_AFTER_HOURS,
)
from .moj_elektro_api import (
    MojElektroApi,
    MojElektroAuthError,
    MojElektroError,
    MojElektroRequestError,
)

_LOGGER = logging.getLogger(__name__)


def _meter_id_already_configured(entries, meter_id: str) -> bool:
    """Return whether any existing entry already targets this EIMM."""
    return any(
        entry.data.get(CONF_METER_ID) == meter_id
        for entry in entries
    )


def _build_extra_reading_choices(
    catalogue: dict,
    selected,
) -> dict[str, str]:
    """Build advanced-reading choices while preserving saved selections."""
    choices: dict[str, str] = {}
    built_in_tags = set(FIFTEEN_MINUTE_SENSORS) | set(DAILY_SENSORS)

    for tag, definition in sorted(catalogue.items()):
        if tag in built_in_tags:
            continue

        label = (
            definition.get("naziv")
            or definition.get("opis")
            or tag
        )
        period = definition.get("perioda")
        if period:
            label = f"{label} ({period})"
        choices[tag] = f"{tag} — {label}"

    for tag in selected:
        choices.setdefault(tag, tag)

    return choices


async def async_validate_connection(
    hass,
    token: str,
    meter_id: str,
) -> str | None:
    """Validate credentials and return a config-flow error key."""
    session = async_get_clientsession(hass)
    api = MojElektroApi(
        token,
        meter_id,
        DEFAULT_DECIMAL,
        session,
    )

    try:
        await api.validate_token()
    except MojElektroAuthError:
        return "invalid_auth"
    except MojElektroRequestError:
        return "invalid_meter"
    except MojElektroError as err:
        _LOGGER.debug(
            "Moj Elektro connection validation failed: %s",
            err,
        )
        return "cannot_connect"
    except Exception as err:
        _LOGGER.debug(
            "Unexpected error while validating Moj Elektro (%s)",
            type(err).__name__,
        )
        return "unknown"

    return None


class MojeElektroFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Moj Elektro config flow."""

    VERSION = 2

    async def async_step_user(self, user_input=None):
        """Handle initial setup."""
        errors = {}

        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            meter_id = user_input[CONF_METER_ID].strip()

            error = await async_validate_connection(self.hass, token, meter_id)
            if error is not None:
                errors["base"] = error
            else:
                if _meter_id_already_configured(
                    self._async_current_entries(),
                    meter_id,
                ):
                    return self.async_abort(reason="already_configured")

                await self.async_set_unique_id(meter_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"Moj Elektro {meter_id}",
                    data={
                        CONF_TOKEN: token,
                        CONF_METER_ID: meter_id,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TOKEN): vol.All(
                        str,
                        lambda value: value.strip(),
                        vol.Length(min=1),
                    ),
                    vol.Required(CONF_METER_ID): vol.All(
                        str,
                        lambda value: value.strip(),
                        vol.Length(min=1),
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data):
        """Start reauthentication after the API rejects the stored token."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        """Request and validate a replacement API token."""
        errors = {}
        reauth_entry = self._get_reauth_entry()
        meter_id = reauth_entry.data[CONF_METER_ID]

        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            error = await async_validate_connection(self.hass, token, meter_id)

            if error is not None:
                errors["base"] = error
            else:
                await self.async_set_unique_id(meter_id)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data_updates={CONF_TOKEN: token},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TOKEN): vol.All(
                        str,
                        lambda value: value.strip(),
                        vol.Length(min=1),
                    )
                }
            ),
            errors=errors,
            description_placeholders={"meter_id": meter_id},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Create the Moj Elektro options flow."""
        return MojeElektroOptionsFlow()


class MojeElektroOptionsFlow(config_entries.OptionsFlowWithReload):
    """Manage runtime settings for Moj Elektro."""

    async def _async_extra_reading_choices(self) -> dict[str, str]:
        """Load optional reading types from the live official catalogue."""
        selected = self.config_entry.options.get(
            CONF_EXTRA_READING_TAGS,
            DEFAULT_EXTRA_READING_TAGS,
        )
        api = MojElektroApi(
            self.config_entry.data[CONF_TOKEN],
            self.config_entry.data[CONF_METER_ID],
            DEFAULT_DECIMAL,
            async_get_clientsession(self.hass),
        )
        try:
            catalogue = await api.get_reading_types()
        except MojElektroError as err:
            _LOGGER.debug(
                "Unable to load optional reading types for options: %s",
                err,
            )
            catalogue = {}

        return _build_extra_reading_choices(
            catalogue,
            selected,
        )

    async def async_step_init(self, user_input=None):
        """Manage integration options."""
        if user_input is not None:
            if CONF_DECIMAL in self.config_entry.data:
                legacy_data = dict(self.config_entry.data)
                legacy_data[CONF_DECIMAL] = user_input[CONF_DECIMAL]
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data=legacy_data,
                )
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options
        extra_reading_choices = await self._async_extra_reading_choices()

        decimal_default = current.get(
            CONF_DECIMAL,
            self.config_entry.data.get(CONF_DECIMAL, DEFAULT_DECIMAL),
        )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_DECIMAL,
                    default=decimal_default,
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=10)),
                vol.Required(
                    CONF_UPDATE_INTERVAL,
                    default=current.get(
                        CONF_UPDATE_INTERVAL,
                        DEFAULT_UPDATE_INTERVAL,
                    ),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(
                        min=MIN_UPDATE_INTERVAL,
                        max=MAX_UPDATE_INTERVAL,
                    ),
                ),
                vol.Required(
                    CONF_LOOKBACK_DAYS,
                    default=current.get(
                        CONF_LOOKBACK_DAYS,
                        DEFAULT_LOOKBACK_DAYS,
                    ),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(
                        min=MIN_LOOKBACK_DAYS,
                        max=MAX_LOOKBACK_DAYS,
                    ),
                ),
                vol.Required(
                    CONF_ENABLE_15MIN,
                    default=current.get(
                        CONF_ENABLE_15MIN,
                        DEFAULT_ENABLE_15MIN,
                    ),
                ): bool,
                vol.Required(
                    CONF_ENABLE_DAILY,
                    default=current.get(
                        CONF_ENABLE_DAILY,
                        DEFAULT_ENABLE_DAILY,
                    ),
                ): bool,
                vol.Required(
                    CONF_ENABLE_TOTAL,
                    default=current.get(
                        CONF_ENABLE_TOTAL,
                        DEFAULT_ENABLE_TOTAL,
                    ),
                ): bool,
                vol.Required(
                    CONF_ENABLE_TARIFF_BLOCKS,
                    default=current.get(
                        CONF_ENABLE_TARIFF_BLOCKS,
                        DEFAULT_ENABLE_TARIFF_BLOCKS,
                    ),
                ): bool,
                vol.Required(
                    CONF_ENABLE_CONTRACTED_POWER,
                    default=current.get(
                        CONF_ENABLE_CONTRACTED_POWER,
                        DEFAULT_ENABLE_CONTRACTED_POWER,
                    ),
                ): bool,
                vol.Required(
                    CONF_ENABLE_SOUPORABA,
                    default=current.get(
                        CONF_ENABLE_SOUPORABA,
                        DEFAULT_ENABLE_SOUPORABA,
                    ),
                ): bool,
                vol.Required(
                    CONF_STALE_AFTER_HOURS,
                    default=current.get(
                        CONF_STALE_AFTER_HOURS,
                        DEFAULT_STALE_AFTER_HOURS,
                    ),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(
                        min=MIN_STALE_AFTER_HOURS,
                        max=MAX_STALE_AFTER_HOURS,
                    ),
                ),
                vol.Optional(
                    CONF_EXTRA_READING_TAGS,
                    default=list(
                        current.get(
                            CONF_EXTRA_READING_TAGS,
                            DEFAULT_EXTRA_READING_TAGS,
                        )
                    ),
                ): cv.multi_select(extra_reading_choices),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
        )
