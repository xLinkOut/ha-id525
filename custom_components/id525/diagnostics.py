"""Diagnostics for the General Mobile ID525 integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from id525.cli import to_jsonable

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .coordinator import Id525ConfigEntry, Id525Settings

TO_REDACT = {
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    "RequestVerifyToken",  # CSRF token of the live session
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


def _settings_summary(settings: Id525Settings | None) -> dict[str, Any] | None:
    """Return the settings without rules, addresses, names or credentials."""
    if settings is None:
        return None
    return {
        "fetched_at": settings.fetched_at,
        "firewall_level": settings.firewall.level.value,
        "vpn_passthrough": settings.firewall.vpn_passthrough,
        "port_forwarding": {
            "enabled": settings.port_forwarding.enabled,
            "dmz_enabled": settings.port_forwarding.dmz_enabled,
            "rule_count": len(settings.port_forwarding.rules),
        },
        **{
            name: {
                "enabled": section.enabled,
                "mode": section.mode.value,
                "rule_count": len(section.rules),
            }
            for name, section in (
                ("url_filter", settings.url_filter),
                ("ip_filter", settings.ip_filter),
                ("mac_filter", settings.mac_filter),
            )
        },
        "voip": {
            "registration_status": settings.voip.registration_status,
            "line_enabled": settings.voip.line_enabled,
        },
        "data_counters_reset": settings.account.statistics_reset_date,
        "data_limit": settings.account.data_limit,
        "data_limit_unit": settings.account.data_limit_unit,
        "sim_pin": {
            "pin_enabled": settings.sim_pin.pin_enabled,
            "pin_retries": settings.sim_pin.pin_retries,
            "puk_retries": settings.sim_pin.puk_retries,
        },
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: Id525ConfigEntry
) -> dict[str, Any]:
    """Return redacted diagnostics.

    Client list, SMS contents and the settings' rules / credentials are omitted.
    """
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
            "settings": to_jsonable(_settings_summary(data.settings)),
        },
        TO_REDACT,
    )
