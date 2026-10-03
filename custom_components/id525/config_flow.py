"""Config flow for the General Mobile ID525 integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.device_registry import format_mac
from id525 import (
    DeviceInfo,
    Id525AuthenticationError,
    Id525ConnectionError,
    Id525Error,
    Id525LoginLockedError,
)

from . import create_client
from .const import (
    CONF_FETCH_SMS,
    CONF_KICK_BACKOFF,
    DEFAULT_FETCH_SMS,
    DEFAULT_HOST,
    DEFAULT_KICK_BACKOFF,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_USERNAME,
    DOMAIN,
    LOGGER,
    MAX_KICK_BACKOFF,
    MAX_SCAN_INTERVAL,
    MIN_KICK_BACKOFF,
    MIN_SCAN_INTERVAL,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .coordinator import Id525ConfigEntry

_PASSWORD_SELECTOR = selector.TextSelector(
    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
)


def _user_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, DEFAULT_HOST)): str,
            vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, DEFAULT_USERNAME)): str,
            vol.Required(CONF_PASSWORD): _PASSWORD_SELECTOR,
        }
    )


class Id525ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the ID525 router."""

    VERSION = 1

    async def _async_validate(
        self, data: Mapping[str, Any], errors: dict[str, str]
    ) -> DeviceInfo | None:
        """Log in once, read device info, log out. Fills ``errors`` on failure."""
        client = create_client(self.hass, dict(data))
        try:
            await client.ensure_session()
            return await client.get_device_info()
        except Id525LoginLockedError:
            errors["base"] = "login_locked"
        except Id525AuthenticationError:
            errors["base"] = "invalid_auth"
        except Id525ConnectionError:
            errors["base"] = "cannot_connect"
        except Id525Error:
            LOGGER.exception("Unexpected router answer")
            errors["base"] = "unknown"
        finally:
            await client.close()
        return None

    @staticmethod
    def _unique_id(info: DeviceInfo) -> str:
        if info.mac:
            return format_mac(info.mac)
        return info.serial_number or info.imei or info.model

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for host and credentials."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._async_abort_entries_match({CONF_HOST: user_input[CONF_HOST]})
            info = await self._async_validate(user_input, errors)
            if info is not None:
                await self.async_set_unique_id(self._unique_id(info))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"{info.model} ({user_input[CONF_HOST]})", data=user_input
                )
        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(user_input or {}),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Start re-authentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new password."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            data = {**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]}
            info = await self._async_validate(data, errors)
            if info is not None:
                await self.async_set_unique_id(self._unique_id(info))
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): _PASSWORD_SELECTOR}),
            description_placeholders={CONF_USERNAME: entry.data[CONF_USERNAME]},
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change host or credentials."""
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            info = await self._async_validate(user_input, errors)
            if info is not None:
                await self.async_set_unique_id(self._unique_id(info))
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(entry, data_updates=user_input)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_user_schema(user_input or entry.data),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Id525ConfigEntry) -> Id525OptionsFlow:
        """Return the options flow."""
        return Id525OptionsFlow()


class Id525OptionsFlow(OptionsFlow):
    """Polling options."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        unit_of_measurement="s",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_KICK_BACKOFF,
                    default=options.get(CONF_KICK_BACKOFF, DEFAULT_KICK_BACKOFF),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_KICK_BACKOFF,
                        max=MAX_KICK_BACKOFF,
                        unit_of_measurement="min",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_FETCH_SMS, default=options.get(CONF_FETCH_SMS, DEFAULT_FETCH_SMS)
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
