"""Settings entities: read on a slower cadence than the status, never fatal."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from id525 import Id525ResponseError
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.id525.const import SETTINGS_INTERVAL

FIREWALL_LEVEL = "sensor.id525_firewall_level"
URL_FILTER = "binary_sensor.id525_url_filter"
RSRP = "sensor.id525_5g_rsrp"


async def _tick(hass: HomeAssistant, freezer: FrozenDateTimeFactory, delta: timedelta) -> None:
    freezer.tick(delta)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_settings_states(hass: HomeAssistant, setup_integration: MockConfigEntry) -> None:
    expected = {
        "binary_sensor.id525_vpn_passthrough": STATE_ON,
        "binary_sensor.id525_port_forwarding": STATE_OFF,
        "binary_sensor.id525_dmz": STATE_OFF,
        URL_FILTER: STATE_OFF,
        "binary_sensor.id525_ip_filter": STATE_OFF,
        "binary_sensor.id525_mac_filter": STATE_OFF,
        "binary_sensor.id525_sim_pin_lock": STATE_OFF,
        FIREWALL_LEVEL: "middle",
        "sensor.id525_voip_line": "up",
        "sensor.id525_sim_pin_attempts_left": "3",
        "sensor.id525_data_counters_reset": "2025-08-20",
        "sensor.id525_data_limit": STATE_UNKNOWN,  # no limit set
    }
    for entity_id, value in expected.items():
        state = hass.states.get(entity_id)
        assert state is not None, entity_id
        assert state.state == value, entity_id

    url_filter = hass.states.get(URL_FILTER)
    assert url_filter is not None
    assert url_filter.attributes["mode"] == "blacklist"
    assert url_filter.attributes["rule_count"] == 0


async def test_settings_read_on_their_own_interval(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    mock_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    get_firewall = mock_client.firewall.get_settings
    assert get_firewall.await_count == 1
    await _tick(hass, freezer, timedelta(seconds=60))
    assert mock_client.get_network_status.await_count == 2
    assert get_firewall.await_count == 1  # not on every poll
    await _tick(hass, freezer, SETTINGS_INTERVAL)
    assert get_firewall.await_count == 2


async def test_unreadable_settings_keep_status_sensors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    mock_client.voip.get_settings.side_effect = Id525ResponseError("unexpected page")
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(RSRP).state == "-79.0"  # type: ignore[union-attr]
    assert hass.states.get(FIREWALL_LEVEL).state == STATE_UNAVAILABLE  # type: ignore[union-attr]

    # not retried on every poll, but at the next settings interval
    await _tick(hass, freezer, timedelta(seconds=60))
    assert mock_client.voip.get_settings.await_count == 1
    mock_client.voip.get_settings.side_effect = None
    await _tick(hass, freezer, SETTINGS_INTERVAL)
    assert hass.states.get(FIREWALL_LEVEL).state == "middle"  # type: ignore[union-attr]
