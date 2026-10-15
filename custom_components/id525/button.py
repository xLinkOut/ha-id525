"""Reboot button for the General Mobile ID525 integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers import entity_registry as er

from .const import CONF_ALLOW_CHANGES, DEFAULT_ALLOW_CHANGES, DOMAIN
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
    """Set up the reboot button, only when commands are allowed."""
    if entry.options.get(CONF_ALLOW_CHANGES, DEFAULT_ALLOW_CHANGES):
        async_add_entities([Id525RebootButton(entry.runtime_data)])
        return
    # commands were turned off: drop the button instead of leaving it unavailable
    registry = er.async_get(hass)
    if entity_id := registry.async_get_entity_id("button", DOMAIN, f"{entry.unique_id}_reboot"):
        registry.async_remove(entity_id)


class Id525RebootButton(Id525Entity, ButtonEntity):
    """Reboot the router (the connection drops for a few minutes)."""

    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: Id525Coordinator) -> None:
        """Initialise the button."""
        super().__init__(coordinator, "reboot")

    async def async_press(self) -> None:
        """Reboot the router."""
        await self.coordinator.async_run(
            lambda: self.coordinator.client.system.reboot(confirm=True)
        )
