"""Base entity for the General Mobile ID525 integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import Id525Coordinator, PollingState


class Id525Entity(CoordinatorEntity[Id525Coordinator]):
    """Entity bound to the router device.

    Data entities are unavailable while polling is paused or backing off, so
    stale values are never presented as current.
    """

    _attr_has_entity_name = True
    _available_when_not_polling = False

    def __init__(self, coordinator: Id525Coordinator, key: str) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        router = coordinator.router
        self._attr_unique_id = f"{entry.unique_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(entry.unique_id))},
            connections={(CONNECTION_NETWORK_MAC, router.mac)} if router.mac else set(),
            name=router.model,
            manufacturer=MANUFACTURER,
            model=router.model,
            serial_number=router.serial_number,
            hw_version=router.hardware_version,
            sw_version=router.software_version,
            configuration_url=coordinator.client.host,
        )

    @property
    def available(self) -> bool:
        """Return True if the entity has fresh data."""
        if self._available_when_not_polling:
            return True
        return super().available and self.coordinator.polling_state is PollingState.ACTIVE
