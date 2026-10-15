"""Commands: reboot button, ping / traceroute actions, opt-in and session guards."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from id525 import Id525SessionKickedError, Id525ValidationError
from id525.sections.diagnostics import PingReport, TracerouteReport
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.id525.const import CONF_ALLOW_CHANGES, DOMAIN

REBOOT = "button.id525_restart"
POLLING_SWITCH = "switch.id525_polling"
POLLING_STATE = "sensor.id525_polling_state"


async def _press_reboot(hass: HomeAssistant) -> None:
    await hass.services.async_call("button", "press", {"entity_id": REBOOT}, blocking=True)


async def _ping(hass: HomeAssistant, **data: Any) -> Any:
    return await hass.services.async_call(DOMAIN, "ping", data, blocking=True, return_response=True)


async def test_read_only_by_default(
    hass: HomeAssistant, setup_integration: MockConfigEntry, mock_client_class: MagicMock
) -> None:
    assert mock_client_class.call_args.kwargs["read_only"] is True
    assert hass.states.get(REBOOT) is None
    with pytest.raises(ServiceValidationError) as err:
        await _ping(hass, host="1.1.1.1")
    assert err.value.translation_key == "commands_disabled"


async def test_commands_allowed(
    hass: HomeAssistant, setup_commands: MockConfigEntry, mock_client_class: MagicMock
) -> None:
    assert mock_client_class.call_args.kwargs["read_only"] is False
    assert hass.states.get(REBOOT) is not None


async def test_reboot_validates_the_session_first(
    hass: HomeAssistant, setup_commands: MockConfigEntry, mock_client: MagicMock
) -> None:
    mock_client.reset_mock()
    await _press_reboot(hass)
    mock_client.system.reboot.assert_awaited_once_with(confirm=True)
    names = [call[0] for call in mock_client.mock_calls]
    assert names.index("ensure_session") < names.index("system.reboot")


async def test_no_command_while_paused(
    hass: HomeAssistant, setup_commands: MockConfigEntry, mock_client: MagicMock
) -> None:
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": POLLING_SWITCH}, blocking=True
    )
    mock_client.reset_mock()
    await _press_reboot(hass)  # the button is unavailable: Home Assistant skips it
    with pytest.raises(HomeAssistantError) as err:
        await _ping(hass)
    assert err.value.translation_key == "polling_inactive"
    # nothing reached the router: the web UI keeps its session
    assert mock_client.mock_calls == []


async def test_kick_during_command_starts_backoff(
    hass: HomeAssistant,
    setup_commands: MockConfigEntry,
    mock_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    mock_client.ensure_session.side_effect = Id525SessionKickedError("taken")
    with pytest.raises(HomeAssistantError) as err:
        await _press_reboot(hass)
    assert err.value.translation_key == "session_taken"
    mock_client.system.reboot.assert_not_awaited()
    assert hass.states.get(POLLING_STATE).state == "backoff"  # type: ignore[union-attr]

    # the next poll leaves the router alone
    mock_client.reset_mock()
    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_client.ensure_session.await_count == 0


async def test_ping(
    hass: HomeAssistant, setup_commands: MockConfigEntry, mock_client: MagicMock
) -> None:
    mock_client.diagnostics.ping.return_value = PingReport(
        host="1.1.1.1",
        count=2,
        size=64,
        lines=("64 bytes from 1.1.1.1: seq=0 ttl=57 time=21 ms",) * 2,
        completed=True,
    )
    response = await _ping(hass, host="1.1.1.1", count=2)
    mock_client.diagnostics.ping.assert_awaited_once_with("1.1.1.1", 2, None)
    assert response == {
        "host": "1.1.1.1",
        "count": 2,
        "size": 64,
        "completed": True,
        "lines": ["64 bytes from 1.1.1.1: seq=0 ttl=57 time=21 ms"] * 2,
    }


async def test_ping_rejected_input(
    hass: HomeAssistant, setup_commands: MockConfigEntry, mock_client: MagicMock
) -> None:
    mock_client.diagnostics.ping.side_effect = Id525ValidationError("the host is empty")
    with pytest.raises(ServiceValidationError) as err:
        await _ping(hass, host="")
    assert err.value.translation_key == "invalid_input"


async def test_traceroute_lines(
    hass: HomeAssistant, setup_commands: MockConfigEntry, mock_client: MagicMock
) -> None:
    mock_client.diagnostics.traceroute.return_value = TracerouteReport(
        host="1.1.1.1",
        output="traceroute to 1.1.1.1<br> 1  10.0.0.1  4 ms<br/> 2  1.1.1.1  20 ms<br>",
        completed=True,
    )
    response = await hass.services.async_call(
        DOMAIN, "traceroute", {"host": "1.1.1.1"}, blocking=True, return_response=True
    )
    assert response == {
        "host": "1.1.1.1",
        "completed": True,
        "lines": ["traceroute to 1.1.1.1", "1  10.0.0.1  4 ms", "2  1.1.1.1  20 ms"],
    }


async def test_turning_commands_off_removes_the_button(
    hass: HomeAssistant,
    setup_commands: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    assert entity_registry.async_get(REBOOT) is not None
    hass.config_entries.async_update_entry(
        setup_commands, options={**setup_commands.options, CONF_ALLOW_CHANGES: False}
    )
    await hass.async_block_till_done()
    assert entity_registry.async_get(REBOOT) is None
    assert hass.states.get(REBOOT) is None
