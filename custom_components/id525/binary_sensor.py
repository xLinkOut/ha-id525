"""Binary sensors for the General Mobile ID525 integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory

from .entity import Id525Entity

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import Id525ConfigEntry, Id525Coordinator, Id525Data

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class Id525BinarySensorEntityDescription(BinarySensorEntityDescription):
    """Binary sensor fed from the coordinator snapshot."""

    is_on_fn: Callable[[Id525Data], bool]


BINARY_SENSORS: tuple[Id525BinarySensorEntityDescription, ...] = (
    Id525BinarySensorEntityDescription(
        key="cellular_connected",
        translation_key="cellular_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        is_on_fn=lambda d: d.status.is_connected,
    ),
    Id525BinarySensorEntityDescription(
        key="roaming",
        translation_key="roaming",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda d: d.status.is_roaming,
    ),
    Id525BinarySensorEntityDescription(
        key="wifi",
        translation_key="wifi",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda d: d.status.wifi_enabled,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Id525ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(Id525BinarySensor(coordinator, d) for d in BINARY_SENSORS)


class Id525BinarySensor(Id525Entity, BinarySensorEntity):
    """A router binary sensor."""

    entity_description: Id525BinarySensorEntityDescription

    def __init__(
        self, coordinator: Id525Coordinator, description: Id525BinarySensorEntityDescription
    ) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        """Return the state."""
        return self.entity_description.is_on_fn(self.coordinator.data)
