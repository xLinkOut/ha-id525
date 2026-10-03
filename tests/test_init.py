"""Setup, polling, pause and back-off tests."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from id525 import (
    Id525AuthenticationError,
    Id525ConnectionError,
    Id525LoginLockedError,
    Id525SessionKickedError,
)
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    mock_restore_cache,
)
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

RSRP = "sensor.id525_5g_rsrp"
POLLING_STATE = "sensor.id525_polling_state"
SWITCH = "switch.id525_polling"


async def _tick(hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: float) -> None:
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_setup_and_unload(
    hass: HomeAssistant, setup_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    assert setup_integration.state is ConfigEntryState.LOADED
    assert await hass.config_entries.async_unload(setup_integration.entry_id)
    assert setup_integration.state is ConfigEntryState.NOT_LOADED
    mock_client.close.assert_awaited_once()  # admin session released


@pytest.mark.parametrize(
    ("error", "state"),
    [
        (Id525ConnectionError("down"), ConfigEntryState.SETUP_RETRY),
        (Id525AuthenticationError("bad"), ConfigEntryState.SETUP_ERROR),
    ],
)
async def test_setup_failure_releases_session(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: MagicMock,
    error: Exception,
    state: ConfigEntryState,
) -> None:
    mock_client.get_device_info.side_effect = error
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is state
    mock_client.close.assert_awaited()


async def test_sensor_states(hass: HomeAssistant, setup_integration: MockConfigEntry) -> None:
    expected = {
        "sensor.id525_sim_state": "connected",
        "sensor.id525_signal_level": "4",
        "sensor.id525_network": "5G I TIM",
        "sensor.id525_data_received": "4177.1",
        RSRP: "-79.0",
        "sensor.id525_5g_band": "n78",
        "sensor.id525_4g_band": "B3",
        "sensor.id525_cpu_usage": "30.6",
        "sensor.id525_connected_clients": "6",
        "sensor.id525_unread_sms": "1",
        POLLING_STATE: "active",
        "binary_sensor.id525_cellular_connection": STATE_ON,
        "binary_sensor.id525_roaming": STATE_OFF,
        SWITCH: STATE_ON,
    }
    for entity_id, value in expected.items():
        state = hass.states.get(entity_id)
        assert state is not None, entity_id
        assert state.state == value, entity_id

    sms = hass.states.get("sensor.id525_unread_sms")
    assert sms is not None
    assert sms.attributes["last_message_text"] == "Hai consumato il 50% del traffico."
    assert sms.attributes["total_messages"] == 2

    download = hass.states.get("sensor.id525_download_rate")
    assert download is not None
    assert download.attributes["unit_of_measurement"] == "Mbit/s"


async def test_disabled_by_default(
    hass: HomeAssistant, setup_integration: MockConfigEntry, entity_registry: er.EntityRegistry
) -> None:
    for entity_id in ("sensor.id525_5g_pci", "sensor.id525_wan_ipv6_address"):
        entry = entity_registry.async_get(entity_id)
        assert entry is not None
        assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    trackers = [
        e
        for e in er.async_entries_for_config_entry(entity_registry, setup_integration.entry_id)
        if e.domain == "device_tracker"
    ]
    assert len(trackers) == 6
    assert all(t.disabled_by is er.RegistryEntryDisabler.INTEGRATION for t in trackers)


async def test_polling_order_detects_kick_first(
    hass: HomeAssistant, setup_integration: MockConfigEntry, mock_client: MagicMock
) -> None:
    """ensure_session must be the first router call of every cycle."""
    mock_client.reset_mock()
    await setup_integration.runtime_data.async_refresh()
    first_call = mock_client.mock_calls[0]
    assert first_call[0] == "ensure_session"


async def test_kick_backoff_and_resume(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    mock_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    mock_client.ensure_session.side_effect = Id525SessionKickedError("taken")
    await _tick(hass, freezer, 60)

    assert hass.states.get(RSRP).state == STATE_UNAVAILABLE  # type: ignore[union-attr]
    polling = hass.states.get(POLLING_STATE)
    assert polling is not None
    assert polling.state == "backoff"
    assert "resumes_at" in polling.attributes

    # during the back-off the router is left alone (web UI keeps its session)
    mock_client.reset_mock()
    mock_client.ensure_session.side_effect = None
    await _tick(hass, freezer, 60)
    await _tick(hass, freezer, 60)
    assert mock_client.ensure_session.await_count == 0
    assert mock_client.get_network_status.await_count == 0

    # after 15 minutes polling resumes
    await _tick(hass, freezer, 15 * 60)
    assert mock_client.ensure_session.await_count == 1
    assert hass.states.get(RSRP).state == "-79.0"  # type: ignore[union-attr]
    assert hass.states.get(POLLING_STATE).state == "active"  # type: ignore[union-attr]


async def test_pause_switch(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    mock_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    await hass.services.async_call("switch", "turn_off", {"entity_id": SWITCH}, blocking=True)
    mock_client.logout.assert_awaited_once()
    assert hass.states.get(SWITCH).state == STATE_OFF  # type: ignore[union-attr]
    assert hass.states.get(RSRP).state == STATE_UNAVAILABLE  # type: ignore[union-attr]
    assert hass.states.get(POLLING_STATE).state == "paused"  # type: ignore[union-attr]

    mock_client.reset_mock()
    await _tick(hass, freezer, 3600)
    assert mock_client.ensure_session.await_count == 0

    await hass.services.async_call("switch", "turn_on", {"entity_id": SWITCH}, blocking=True)
    await hass.async_block_till_done()
    assert mock_client.ensure_session.await_count == 1
    assert hass.states.get(RSRP).state == "-79.0"  # type: ignore[union-attr]


async def test_pause_restored_after_restart(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    mock_restore_cache(hass, [State(SWITCH, STATE_OFF)])
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(SWITCH).state == STATE_OFF  # type: ignore[union-attr]
    mock_client.logout.assert_awaited()


async def test_lockout_backoff_then_explicit_login(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    mock_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    mock_client.ensure_session.side_effect = Id525LoginLockedError(120)
    await _tick(hass, freezer, 60)
    assert hass.states.get(POLLING_STATE).state == "backoff"  # type: ignore[union-attr]

    mock_client.ensure_session.side_effect = None
    mock_client.reset_mock()
    await _tick(hass, freezer, 60)
    assert mock_client.login.await_count == 0  # still locked out
    await _tick(hass, freezer, 120)
    mock_client.login.assert_awaited_once()  # deliberate retry after the lock
    assert hass.states.get(RSRP).state == "-79.0"  # type: ignore[union-attr]


async def test_auth_failure_starts_reauth(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    mock_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    mock_client.ensure_session.side_effect = Id525AuthenticationError("bad")
    await _tick(hass, freezer, 60)
    flows = hass.config_entries.flow.async_progress()
    assert any(flow["context"]["source"] == "reauth" for flow in flows)


async def test_diagnostics_are_redacted(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    setup_integration: MockConfigEntry,
) -> None:
    diagnostics = await get_diagnostics_for_config_entry(hass, hass_client, setup_integration)
    text = str(diagnostics)
    for secret in ("secret", "350000000000000", "222010000000000", "192.168.1.10", "TestNet"):
        assert secret not in text
    assert diagnostics["client_count"] == 6
    assert diagnostics["polling_state"] == "active"
