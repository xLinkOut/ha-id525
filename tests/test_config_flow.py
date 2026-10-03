"""Config flow tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from id525 import (
    Id525AuthenticationError,
    Id525ConnectionError,
    Id525LoginLockedError,
    Id525ResponseError,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.id525.const import CONF_FETCH_SMS, CONF_KICK_BACKOFF, DOMAIN

from .conftest import HOST, ROUTER_MAC, USER_INPUT


@pytest.fixture(autouse=True)
def no_entry_setup(mock_client: MagicMock) -> None:
    """Config flow tests only need the mocked client."""


async def test_user_flow(hass: HomeAssistant, mock_client: MagicMock) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"ID525 ({HOST})"
    assert result["data"] == USER_INPUT
    assert result["result"].unique_id == ROUTER_MAC
    mock_client.close.assert_awaited()  # the admin session is released


@pytest.mark.parametrize(
    ("error", "key"),
    [
        (Id525AuthenticationError("bad"), "invalid_auth"),
        (Id525LoginLockedError(300), "login_locked"),
        (Id525ConnectionError("down"), "cannot_connect"),
        (Id525ResponseError("weird"), "unknown"),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant, mock_client: MagicMock, error: Exception, key: str
) -> None:
    mock_client.ensure_session.side_effect = error
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data=USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": key}
    mock_client.close.assert_awaited()

    mock_client.ensure_session.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_already_configured(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}, data={**USER_INPUT, CONF_HOST: "10.0.0.1"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_flow(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    mock_client.ensure_session.side_effect = Id525AuthenticationError("bad")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "wrong"}
    )
    assert result["errors"] == {"base": "invalid_auth"}

    mock_client.ensure_session.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-secret"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_PASSWORD] == "new-secret"
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)


async def test_reconfigure_flow(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_HOST: "192.168.224.254"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[CONF_HOST] == "192.168.224.254"
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)


async def test_reconfigure_wrong_device(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    mock_config_entry.add_to_hass(hass)
    info = mock_client.get_device_info.return_value
    mock_client.get_device_info.return_value = type(info)(
        **{**{f: getattr(info, f) for f in info.__dataclass_fields__}, "mac": "02:00:00:00:00:99"}
    )
    result = await mock_config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"


async def test_options_flow(hass: HomeAssistant, setup_integration: MockConfigEntry) -> None:
    result = await hass.config_entries.options.async_init(setup_integration.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_SCAN_INTERVAL: 120, CONF_KICK_BACKOFF: 30, CONF_FETCH_SMS: False},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert setup_integration.options == {
        CONF_SCAN_INTERVAL: 120,
        CONF_KICK_BACKOFF: 30,
        CONF_FETCH_SMS: False,
    }
    coordinator = setup_integration.runtime_data
    assert coordinator.update_interval.total_seconds() == 120
    assert coordinator.data.sms is None
