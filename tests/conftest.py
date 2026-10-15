"""Fixtures for the General Mobile ID525 integration tests.

The router client is fully mocked: these tests never talk to a real router.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from id525 import LoginState
from id525.parsers import (
    parse_about_page,
    parse_cellular_page,
    parse_clients,
    parse_network_status,
    parse_sms,
    parse_utilization_page,
)
from id525.sections.account import parse_account_page
from id525.sections.firewall import parse_firewall_page
from id525.sections.ip_filter import parse_ip_filter_page
from id525.sections.mac_filter import parse_mac_filter_page
from id525.sections.port_forwarding import parse_port_forwarding_page
from id525.sections.status import parse_sim_pin_page
from id525.sections.url_filter import parse_url_filter_page
from id525.sections.voip import parse_voip_page
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.id525.const import CONF_ALLOW_CHANGES, DOMAIN

FIXTURES = Path(__file__).parent / "fixtures"
HOST = "192.168.224.1"
ROUTER_MAC = "02:00:5e:00:00:07"
USER_INPUT = {CONF_HOST: HOST, CONF_USERNAME: "admin", CONF_PASSWORD: "secret"}


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text()


def fixture_json(name: str) -> Any:
    return json.loads(fixture_text(name))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading custom integrations in all tests."""


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title=f"ID525 ({HOST})",
        data=USER_INPUT,
        unique_id=ROUTER_MAC,
    )


def _make_client() -> MagicMock:
    client = MagicMock()
    client.host = f"https://{HOST}"
    client.ensure_session = AsyncMock(return_value=LoginState.LOGGED_IN)
    client.login = AsyncMock()
    client.logout = AsyncMock()
    client.close = AsyncMock()
    client.get_device_info = AsyncMock(
        return_value=parse_about_page(fixture_text("help-about.html"))
    )
    client.get_network_status = AsyncMock(
        return_value=parse_network_status(fixture_json("net_status.json"))
    )
    client.get_clients = AsyncMock(return_value=parse_clients(fixture_json("client_status.json")))
    client.get_cellular_info = AsyncMock(
        return_value=parse_cellular_page(fixture_text("cellular-status.html"))
    )
    client.get_utilization = AsyncMock(
        return_value=parse_utilization_page(fixture_text("util-status.html"))
    )
    client.get_sms = AsyncMock(return_value=parse_sms(fixture_json("sms_reload.json")))
    settings_pages = {
        client.firewall: (parse_firewall_page, "fw-adv.html"),
        client.port_forwarding: (parse_port_forwarding_page, "fw-portfwd.html"),
        client.url_filter: (parse_url_filter_page, "fw-urlfilter.html"),
        client.ip_filter: (parse_ip_filter_page, "fw-ipfilter.html"),
        client.mac_filter: (parse_mac_filter_page, "fw-macfilter.html"),
        client.account: (parse_account_page, "adm-user.html"),
        client.voip: (parse_voip_page, "voip-settings.html"),
    }
    for section, (parse, page) in settings_pages.items():
        section.get_settings = AsyncMock(return_value=parse(fixture_text(page)))
    client.status.get_sim_pin_status = AsyncMock(
        return_value=parse_sim_pin_page(fixture_text("net-status.html"))
    )
    client.system.reboot = AsyncMock()
    client.diagnostics.ping = AsyncMock()
    client.diagnostics.traceroute = AsyncMock()
    return client


@pytest.fixture
def mock_client_class() -> Generator[MagicMock]:
    """Patch the router client class everywhere the integration creates one."""
    with (
        patch("custom_components.id525.Id525Client", return_value=_make_client()) as cls,
        patch("custom_components.id525.async_create_clientsession", return_value=MagicMock()),
    ):
        yield cls


@pytest.fixture
def mock_client(mock_client_class: MagicMock) -> MagicMock:
    """The router client instance the integration gets."""
    client: MagicMock = mock_client_class.return_value
    return client


@pytest.fixture
def commands_entry() -> MockConfigEntry:
    """A config entry with commands allowed."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=f"ID525 ({HOST})",
        data=USER_INPUT,
        options={CONF_ALLOW_CHANGES: True},
        unique_id=ROUTER_MAC,
    )


@pytest.fixture
async def setup_commands(
    hass: HomeAssistant, commands_entry: MockConfigEntry, mock_client: MagicMock
) -> MockConfigEntry:
    commands_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(commands_entry.entry_id)
    await hass.async_block_till_done()
    return commands_entry


@pytest.fixture
async def setup_integration(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> MockConfigEntry:
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry
