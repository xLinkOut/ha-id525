"""Actions of the General Mobile ID525 integration: ping and traceroute from the router."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import service

from .const import CONF_ALLOW_CHANGES, DEFAULT_ALLOW_CHANGES, DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import ServiceResponse

    from .coordinator import Id525ConfigEntry, Id525Coordinator

SERVICE_PING = "ping"
SERVICE_TRACEROUTE = "traceroute"

ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_HOST = "host"
ATTR_COUNT = "count"
ATTR_SIZE = "size"

MAX_PING_COUNT = 100
"""Each echo is one request a second apart, and the router is busy meanwhile."""

PING_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(ATTR_HOST): cv.string,
        vol.Optional(ATTR_COUNT): vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_PING_COUNT)),
        vol.Optional(ATTR_SIZE): vol.All(vol.Coerce(int), vol.Range(min=1)),
    }
)
TRACEROUTE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(ATTR_HOST): cv.string,
    }
)

_LINE_BREAK_RE = re.compile(r"<br\s*/?>|\r?\n", re.IGNORECASE)


def _coordinator(call: ServiceCall) -> Id525Coordinator:
    """Return the coordinator of the targeted router (the only one if not given)."""
    entry: Id525ConfigEntry = service.async_get_config_entry(
        call.hass, DOMAIN, call.data.get(ATTR_CONFIG_ENTRY_ID)
    )
    if not entry.options.get(CONF_ALLOW_CHANGES, DEFAULT_ALLOW_CHANGES):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="commands_disabled",
            translation_placeholders={"title": entry.title},
        )
    return entry.runtime_data


async def _async_ping(call: ServiceCall) -> ServiceResponse:
    coordinator = _coordinator(call)
    report = await coordinator.async_run(
        lambda: coordinator.client.diagnostics.ping(
            call.data.get(ATTR_HOST), call.data.get(ATTR_COUNT), call.data.get(ATTR_SIZE)
        )
    )
    return {
        "host": report.host,
        "count": report.count,
        "size": report.size,
        "completed": report.completed,
        "lines": list(report.lines),
    }


async def _async_traceroute(call: ServiceCall) -> ServiceResponse:
    coordinator = _coordinator(call)
    report = await coordinator.async_run(
        lambda: coordinator.client.diagnostics.traceroute(call.data.get(ATTR_HOST))
    )
    lines = [line.strip() for line in _LINE_BREAK_RE.split(report.output or "")]
    return {
        "host": report.host,
        "completed": report.completed,
        "lines": [line for line in lines if line],
    }


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the actions (once, for every router)."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_PING,
        _async_ping,
        schema=PING_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_TRACEROUTE,
        _async_traceroute,
        schema=TRACEROUTE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
