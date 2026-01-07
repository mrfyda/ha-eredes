"""Config flow for E-REDES integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_AAT_TOKEN, CONF_CPE, DOMAIN
from .eredes_api import ERedesAuthenticationError, ERedesClient, ERedesConnectionError

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_AAT_TOKEN): str,
        vol.Required(CONF_CPE): str,
    }
)


class ERedesConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for E-REDES."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._reauth_entry: ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Check for existing entry with same CPE
            await self.async_set_unique_id(user_input[CONF_CPE])
            self._abort_if_unique_id_configured()

            # Test the token
            error = await self._test_token(user_input[CONF_AAT_TOKEN])

            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title=f"E-REDES ({user_input[CONF_CPE][-8:]})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(
        self, _entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle reauthorization request."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reauth confirmation."""
        errors: dict[str, str] = {}

        if user_input is not None:
            assert self._reauth_entry is not None

            error = await self._test_token(user_input[CONF_AAT_TOKEN])

            if error:
                errors["base"] = error
            else:
                # Update the config entry with new token
                self.hass.config_entries.async_update_entry(
                    self._reauth_entry,
                    data={
                        **self._reauth_entry.data,
                        CONF_AAT_TOKEN: user_input[CONF_AAT_TOKEN],
                    },
                )
                await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_AAT_TOKEN): str,
                }
            ),
            errors=errors,
            description_placeholders={
                "cpe": self._reauth_entry.data[CONF_CPE] if self._reauth_entry else "",
            },
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration."""
        errors: dict[str, str] = {}
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])

        if user_input is not None:
            assert entry is not None

            # If CPE changed, check for duplicates
            if user_input[CONF_CPE] != entry.data[CONF_CPE]:
                await self.async_set_unique_id(user_input[CONF_CPE])
                self._abort_if_unique_id_configured()

            # Test token
            error = await self._test_token(user_input[CONF_AAT_TOKEN])

            if error:
                errors["base"] = error
            else:
                self.hass.config_entries.async_update_entry(
                    entry,
                    title=f"E-REDES ({user_input[CONF_CPE][-8:]})",
                    data=user_input,
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reconfigure_successful")

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_AAT_TOKEN,
                        default=entry.data.get(CONF_AAT_TOKEN) if entry else "",
                    ): str,
                    vol.Required(
                        CONF_CPE,
                        default=entry.data.get(CONF_CPE) if entry else "",
                    ): str,
                }
            ),
            errors=errors,
        )

    async def _test_token(self, aat_token: str) -> str | None:
        """Test if the token is valid.

        Returns an error key if validation fails, None if successful.
        """
        session = async_get_clientsession(self.hass)
        client = ERedesClient(session, aat_token)

        try:
            valid = await client.validate_token()
            if not valid:
                return "invalid_auth"
            return None
        except ERedesAuthenticationError:
            return "invalid_auth"
        except ERedesConnectionError:
            return "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected error during token validation")
            return "unknown"

    @staticmethod
    @callback
    def async_get_options_flow(_config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return ERedesOptionsFlow()


class ERedesOptionsFlow(OptionsFlow):
    """Handle E-REDES options."""

    async def async_step_init(
        self, _user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        # Currently no options, but this allows future expansion
        return self.async_abort(reason="no_options")
