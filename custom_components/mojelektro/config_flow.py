"""Config flow for Moj Elektro."""

import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_DECIMAL, CONF_METER_ID, CONF_TOKEN, DOMAIN
from .moj_elektro_api import (
    MojElektroApi,
    MojElektroAuthError,
    MojElektroError,
)

_LOGGER = logging.getLogger(__name__)


class MojeElektroFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Moj Elektro."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial configuration step."""
        errors = {}

        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            meter_id = user_input[CONF_METER_ID].strip()
            decimal = user_input.get(CONF_DECIMAL)

            session = async_get_clientsession(self.hass)
            api = MojElektroApi(token, meter_id, decimal, session)

            try:
                valid = await api.validate_token()
            except MojElektroAuthError:
                valid = False
            except MojElektroError as err:
                _LOGGER.debug("Moj Elektro connection validation failed: %s", err)
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error while validating Moj Elektro")
                errors["base"] = "unknown"
            else:
                if not valid:
                    errors["base"] = "invalid_auth"
                else:
                    await self.async_set_unique_id(meter_id)
                    self._abort_if_unique_id_configured()

                    data = dict(user_input)
                    data[CONF_TOKEN] = token
                    data[CONF_METER_ID] = meter_id

                    return self.async_create_entry(
                        title=f"Moj Elektro {meter_id}",
                        data=data,
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TOKEN): str,
                    vol.Required(CONF_METER_ID): str,
                    vol.Optional(CONF_DECIMAL): vol.All(
                        vol.Coerce(int), vol.Range(min=0, max=10)
                    ),
                }
            ),
            errors=errors,
        )
