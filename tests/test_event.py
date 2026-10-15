"""SMS event: fired for messages that arrive while Home Assistant runs."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from id525.parsers import parse_sms
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.id525.const import CONF_FETCH_SMS, DOMAIN

from .conftest import ROUTER_MAC, USER_INPUT, fixture_json

SMS_EVENT = "event.id525_sms"


async def _poll(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_new_sms_fires_once(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    mock_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    # messages already stored at start-up are not reported
    assert hass.states.get(SMS_EVENT).state == STATE_UNKNOWN  # type: ignore[union-attr]
    await _poll(hass, freezer)
    assert hass.states.get(SMS_EVENT).state == STATE_UNKNOWN  # type: ignore[union-attr]

    payload = fixture_json("sms_reload.json")
    payload["message"].insert(
        0,
        {
            "index": 4,
            "phone_number": "+390000000004",
            "time": "2026/10/03 09:30:00",
            "context": "Nuovo messaggio",
            "read_status": 0,
        },
    )
    mock_client.get_sms.return_value = parse_sms(payload)
    await _poll(hass, freezer)

    state = hass.states.get(SMS_EVENT)
    assert state is not None
    assert state.state != STATE_UNKNOWN
    assert state.attributes["event_type"] == "received"
    assert state.attributes["phone_number"] == "+390000000004"
    assert state.attributes["text"] == "Nuovo messaggio"
    fired_at = state.state

    await _poll(hass, freezer)
    assert hass.states.get(SMS_EVENT).state == fired_at  # type: ignore[union-attr]


async def test_no_event_without_sms(hass: HomeAssistant, mock_client: MagicMock) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, data=USER_INPUT, options={CONF_FETCH_SMS: False}, unique_id=ROUTER_MAC
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(SMS_EVENT) is None
