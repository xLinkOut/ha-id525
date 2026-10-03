"""Diagnostics for the General Mobile ID525 integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from id525.cli import to_jsonable

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .coordinator import Id525ConfigEntry

TO_REDACT = {
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    # router identity
    "imei",
    "imsi",
    "phone_number",
    "serial_number",
    "mac",
    # status payload
    "address",
    "gateway",
    "dns",
    "lan_ip",
    "ssid_2g",
    "ssid_5g",
    "fqdn",
    "ipv4_addr",
    "ipv4_gw",
    "ipv4_dns",
    "ipv6_addr",
    "ipv6_gw",
    "ipv6_dns",
    "ipv6_prefix",
    "hostIPAddr",
    "cell_id",
    "eci",
    "pci",
    "arfcn",
    "earfcn",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: Id525ConfigEntry
) -> dict[str, Any]:
    """Return redacted diagnostics. Client list and SMS contents are omitted."""
    coordinator = entry.runtime_data
    data = coordinator.data
    return async_redact_data(
        {
            "entry": {"data": dict(entry.data), "options": dict(entry.options)},
            "polling_state": coordinator.polling_state.value,
            "router": to_jsonable(coordinator.router),
            "status": dict(data.status.raw),
            "cells": [dict(cell.raw) for cell in data.cells.cells],
            "utilization": to_jsonable(data.utilization),
            "client_count": len(data.clients),
            "sms_count": len(data.sms.messages) if data.sms else None,
        },
        TO_REDACT,
    )
