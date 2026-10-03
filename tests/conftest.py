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
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.id525.const import DOMAIN

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
    return client


@pytest.fixture
def mock_client() -> Generator[MagicMock]:
    """Patch the router client everywhere the integration creates one."""
    client = _make_client()
    with (
        patch("custom_components.id525.Id525Client", return_value=client),
        patch("custom_components.id525.async_create_clientsession", return_value=MagicMock()),
    ):
        yield client


@pytest.fixture
async def setup_integration(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> MockConfigEntry:
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry
