"""Polling switch: turn off to free the router's single admin session."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF, EntityCategory
from homeassistant.helpers.restore_state import RestoreEntity

from .entity import Id525Entity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import Id525ConfigEntry, Id525Coordinator

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Id525ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the polling switch."""
    async_add_entities([Id525PollingSwitch(entry.runtime_data)])


class Id525PollingSwitch(Id525Entity, SwitchEntity, RestoreEntity):
    """On: Home Assistant polls the router. Off: logged out, web UI usable."""

    _attr_translation_key = "polling"
    _attr_entity_category = EntityCategory.CONFIG
    _available_when_not_polling = True

    def __init__(self, coordinator: Id525Coordinator) -> None:
        """Initialise the switch."""
        super().__init__(coordinator, "polling")

    async def async_added_to_hass(self) -> None:
        """Restore a pause that was active before a restart."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state == STATE_OFF:
            await self.coordinator.async_pause()

    @property
    def is_on(self) -> bool:
        """Return True while polling is enabled."""
        return not self.coordinator.paused

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Resume polling (takes the admin session back)."""
        await self.coordinator.async_resume()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Pause polling and log out."""
        await self.coordinator.async_pause()
        self.async_write_ha_state()
