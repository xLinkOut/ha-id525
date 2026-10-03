"""The General Mobile ID525 integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

import aiohttp
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from id525 import Id525Client

from .coordinator import Id525ConfigEntry, Id525Coordinator

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.DEVICE_TRACKER,
    Platform.SENSOR,
    Platform.SWITCH,
]


def create_client(hass: HomeAssistant, data: dict[str, str]) -> Id525Client:
    """Create a router client on a dedicated HTTP session.

    The router uses a self-signed certificate (verification disabled) and the
    client manages the session cookie itself, hence the dummy cookie jar.
    """
    session = async_create_clientsession(
        hass, verify_ssl=False, cookie_jar=aiohttp.DummyCookieJar()
    )
    return Id525Client(data[CONF_HOST], data[CONF_USERNAME], data[CONF_PASSWORD], session=session)


async def async_setup_entry(hass: HomeAssistant, entry: Id525ConfigEntry) -> bool:
    """Set up the router from a config entry."""
    client = create_client(hass, dict(entry.data))
    coordinator = Id525Coordinator(hass, entry, client)
    try:
        await coordinator.async_config_entry_first_refresh()
    except BaseException:
        await client.close()  # never leave the single admin session occupied
        raise
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: Id525ConfigEntry) -> bool:
    """Unload a config entry and free the router's admin session."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.client.close()
    return unloaded


async def _async_options_updated(hass: HomeAssistant, entry: Id525ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
