"""Binary sensors for the General Mobile ID525 integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory

from .entity import Id525Entity, Id525SettingsEntity

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
    from id525 import IpFilterSettings, MacFilterSettings, UrlFilterSettings

    from .coordinator import Id525ConfigEntry, Id525Coordinator, Id525Data, Id525Settings

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


@dataclass(frozen=True, kw_only=True)
class Id525SettingsBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Binary sensor fed from the settings pages."""

    is_on_fn: Callable[[Id525Settings], bool | None]
    attributes_fn: Callable[[Id525Settings], dict[str, Any]] | None = None


def _filter_attributes(
    section: Callable[[Id525Settings], IpFilterSettings | MacFilterSettings | UrlFilterSettings],
) -> Callable[[Id525Settings], dict[str, Any]]:
    def attributes(settings: Id525Settings) -> dict[str, Any]:
        data = section(settings)
        return {"mode": data.mode.value, "rule_count": len(data.rules)}

    return attributes


SETTINGS_BINARY_SENSORS: tuple[Id525SettingsBinarySensorEntityDescription, ...] = (
    Id525SettingsBinarySensorEntityDescription(
        key="vpn_passthrough",
        translation_key="vpn_passthrough",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda s: s.firewall.vpn_passthrough,
    ),
    Id525SettingsBinarySensorEntityDescription(
        key="port_forwarding",
        translation_key="port_forwarding",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda s: s.port_forwarding.enabled,
        attributes_fn=lambda s: {"rule_count": len(s.port_forwarding.rules)},
    ),
    Id525SettingsBinarySensorEntityDescription(
        key="dmz",
        translation_key="dmz",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda s: s.port_forwarding.dmz_enabled,
    ),
    Id525SettingsBinarySensorEntityDescription(
        key="url_filter",
        translation_key="url_filter",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda s: s.url_filter.enabled,
        attributes_fn=_filter_attributes(lambda s: s.url_filter),
    ),
    Id525SettingsBinarySensorEntityDescription(
        key="ip_filter",
        translation_key="ip_filter",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda s: s.ip_filter.enabled,
        attributes_fn=_filter_attributes(lambda s: s.ip_filter),
    ),
    Id525SettingsBinarySensorEntityDescription(
        key="mac_filter",
        translation_key="mac_filter",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda s: s.mac_filter.enabled,
        attributes_fn=_filter_attributes(lambda s: s.mac_filter),
    ),
    Id525SettingsBinarySensorEntityDescription(
        key="sim_pin_lock",
        translation_key="sim_pin_lock",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda s: s.sim_pin.pin_enabled,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Id525ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors."""
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [Id525BinarySensor(coordinator, d) for d in BINARY_SENSORS]
    entities.extend(Id525SettingsBinarySensor(coordinator, d) for d in SETTINGS_BINARY_SENSORS)
    async_add_entities(entities)


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


class Id525SettingsBinarySensor(Id525SettingsEntity, BinarySensorEntity):
    """A binary sensor showing a router setting."""

    entity_description: Id525SettingsBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: Id525Coordinator,
        description: Id525SettingsBinarySensorEntityDescription,
    ) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return the state."""
        return self.entity_description.is_on_fn(self.settings)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the filter mode and the number of rules, where relevant."""
        attributes_fn = self.entity_description.attributes_fn
        return attributes_fn(self.settings) if attributes_fn else None
