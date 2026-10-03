"""LAN client trackers for the General Mobile ID525 integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.device_tracker.config_entry import ScannerEntity
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import Id525Coordinator, PollingState

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
    from id525 import ConnectedClient

    from .coordinator import Id525ConfigEntry

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Id525ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up trackers for current clients and for clients seen before."""
    coordinator = entry.runtime_data
    registry = er.async_get(hass)
    known: set[str] = {
        str(reg_entry.unique_id)
        for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id)
        if reg_entry.domain == "device_tracker" and reg_entry.platform == DOMAIN
    }
    async_add_entities(Id525ClientTracker(coordinator, mac) for mac in known)

    @callback
    def _add_new_clients() -> None:
        new = {c.mac for c in coordinator.data.clients if c.mac} - known
        if new:
            known.update(new)
            async_add_entities(Id525ClientTracker(coordinator, mac) for mac in new)

    _add_new_clients()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_clients))


class Id525ClientTracker(CoordinatorEntity[Id525Coordinator], ScannerEntity):  # type: ignore[misc]
    """A device in the router's LAN client list (disabled by default)."""

    def __init__(self, coordinator: Id525Coordinator, mac: str) -> None:
        """Initialise the tracker."""
        super().__init__(coordinator)
        self._mac = mac

    @property
    def _client(self) -> ConnectedClient | None:
        return next((c for c in self.coordinator.data.clients if c.mac == self._mac), None)

    @property
    def available(self) -> bool:
        """Unavailable while polling is paused or backing off."""
        return super().available and self.coordinator.polling_state is PollingState.ACTIVE

    @property
    def name(self) -> str:
        """Return the client hostname, or its MAC."""
        client = self._client
        return client.hostname if client and client.hostname else self._mac

    @property
    def mac_address(self) -> str:
        """Return the client MAC address."""
        return self._mac

    @property
    def is_connected(self) -> bool:
        """Return True if the client is in the router's client list."""
        return self._client is not None

    @property
    def ip_address(self) -> str | None:
        """Return the client IP address."""
        client = self._client
        return client.ip if client else None

    @property
    def hostname(self) -> str | None:
        """Return the client hostname."""
        client = self._client
        return client.hostname if client else None

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Return the interface the client is attached to."""
        client = self._client
        return {"interface": client.interface_raw} if client else {}
