"""Config flow for E-REDES integration."""

from __future__ import annotations

import logging
import time
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

from .const import (
    BASE_URL,
    CONF_ACCESS_TOKEN,
    CONF_CPE,
    DOMAIN,
    TOKEN_EXPIRY_MARGIN_SECONDS,
    TOKEN_ISSUER,
)
from .eredes_api import ERedesAuthenticationError, ERedesClient, ERedesConnectionError

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ACCESS_TOKEN): str,
        vol.Required(CONF_CPE): str,
    }
)


class ERedesConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for E-REDES."""

    VERSION = 2

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

            # Test the credentials
            error = await self._test_credentials(
                user_input[CONF_ACCESS_TOKEN], user_input[CONF_CPE]
            )

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
            description_placeholders={"setup_url": BASE_URL},
        )

    async def async_step_reauth(self, _entry_data: dict[str, Any]) -> ConfigFlowResult:
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

            # The CPE is already known to be valid: only the token changes.
            error = await self._check_renewed_token(
                user_input[CONF_ACCESS_TOKEN], self._reauth_entry.data[CONF_CPE]
            )

            if error:
                errors["base"] = error
            else:
                # Update the config entry with the new access token
                self.hass.config_entries.async_update_entry(
                    self._reauth_entry,
                    data={
                        **self._reauth_entry.data,
                        CONF_ACCESS_TOKEN: user_input[CONF_ACCESS_TOKEN],
                    },
                )
                self.hass.config_entries.async_schedule_reload(
                    self._reauth_entry.entry_id
                )
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ACCESS_TOKEN): str,
                }
            ),
            errors=errors,
            description_placeholders={
                "cpe": self._reauth_entry.data[CONF_CPE] if self._reauth_entry else "",
                "setup_url": BASE_URL,
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

            # A new CPE needs the full check against E-Redes; a token renewal
            # for the same CPE only needs the local check.
            if user_input[CONF_CPE] != entry.data[CONF_CPE]:
                error = await self._test_credentials(
                    user_input[CONF_ACCESS_TOKEN], user_input[CONF_CPE]
                )
            else:
                error = await self._check_renewed_token(
                    user_input[CONF_ACCESS_TOKEN], user_input[CONF_CPE]
                )

            if error:
                errors["base"] = error
            else:
                self.hass.config_entries.async_update_entry(
                    entry,
                    title=f"E-REDES ({user_input[CONF_CPE][-8:]})",
                    data=user_input,
                )
                self.hass.config_entries.async_schedule_reload(entry.entry_id)
                return self.async_abort(reason="reconfigure_successful")

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ACCESS_TOKEN,
                        default=entry.data.get(CONF_ACCESS_TOKEN) if entry else "",
                    ): str,
                    vol.Required(
                        CONF_CPE,
                        default=entry.data.get(CONF_CPE) if entry else "",
                    ): str,
                }
            ),
            errors=errors,
        )

    async def _check_renewed_token(self, access_token: str, cpe: str) -> str | None:
        """Check a renewed token quickly.

        E-Redes' data endpoint takes over a minute to answer an accepted token,
        which made token renewal slow; the reload after saving also did a full
        fetch while the flow waited. Instead: check the aat JWT's issuer and
        expiry locally, then ask E-Redes whether it accepts the token with a
        request that fetches no data and a short timeout (see
        ERedesClient.check_token).

        Returns an error key if the token is not usable, None otherwise.
        """
        client = ERedesClient(async_get_clientsession(self.hass), access_token)
        claims = client.token_claims()
        if claims is None or claims.get("iss") != TOKEN_ISSUER:
            return "invalid_auth"
        exp = claims.get("exp")
        if not isinstance(exp, int | float) or exp <= (
            time.time() + TOKEN_EXPIRY_MARGIN_SECONDS
        ):
            return "invalid_auth"
        try:
            await client.check_token(cpe)
        except ERedesAuthenticationError:
            return "invalid_auth"
        except ERedesConnectionError:
            return "cannot_connect"
        return None

    async def _test_credentials(self, access_token: str, cpe: str) -> str | None:
        """Test if the credentials are valid.

        Returns an error key if validation fails, None if successful.
        """
        session = async_get_clientsession(self.hass)
        client = ERedesClient(session, access_token)

        try:
            valid = await client.validate_token(cpe)
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
