"""Sensors for the General Mobile ID525 integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfDataRate,
    UnitOfFrequency,
    UnitOfInformation,
)
from id525 import Cell, SimState

from .coordinator import Id525Coordinator, Id525Data, PollingState
from .entity import Id525Entity

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime, timedelta

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
    from homeassistant.helpers.typing import StateType

    from .coordinator import Id525ConfigEntry

PARALLEL_UPDATES = 0

SIM_STATE_OPTIONS = [state.name.lower() for state in SimState]


def _since(fetched_at: datetime, elapsed: timedelta | None) -> datetime | None:
    """Turn an elapsed duration into a stable (minute-rounded) start timestamp."""
    if elapsed is None:
        return None
    return (fetched_at - elapsed).replace(second=0, microsecond=0)


@dataclass(frozen=True, kw_only=True)
class Id525SensorEntityDescription(SensorEntityDescription):
    """Sensor fed from the coordinator snapshot."""

    value_fn: Callable[[Id525Data], StateType | datetime]


def _cell_value(network: str, attr: str) -> Callable[[Id525Data], StateType]:
    def value(data: Id525Data) -> StateType:
        cell: Cell | None = data.cells.primary(network)
        return getattr(cell, attr) if cell is not None else None

    return value


def _cell_descriptions(network: str, slug: str) -> tuple[Id525SensorEntityDescription, ...]:
    """Radio sensors for the primary cell of one RAT (``slug`` = nr / lte)."""
    return (
        Id525SensorEntityDescription(
            key=f"{slug}_rsrp",
            translation_key=f"{slug}_rsrp",
            native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
            device_class=SensorDeviceClass.SIGNAL_STRENGTH,
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=_cell_value(network, "rsrp"),
        ),
        Id525SensorEntityDescription(
            key=f"{slug}_rsrq",
            translation_key=f"{slug}_rsrq",
            native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS,
            device_class=SensorDeviceClass.SIGNAL_STRENGTH,
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=_cell_value(network, "rsrq"),
        ),
        Id525SensorEntityDescription(
            key=f"{slug}_sinr",
            translation_key=f"{slug}_sinr",
            native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS,
            device_class=SensorDeviceClass.SIGNAL_STRENGTH,
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=_cell_value(network, "snr"),
        ),
        Id525SensorEntityDescription(
            key=f"{slug}_band",
            translation_key=f"{slug}_band",
            value_fn=_cell_value(network, "band"),
        ),
        Id525SensorEntityDescription(
            key=f"{slug}_bandwidth",
            translation_key=f"{slug}_bandwidth",
            native_unit_of_measurement=UnitOfFrequency.MEGAHERTZ,
            device_class=SensorDeviceClass.FREQUENCY,
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=_cell_value(network, "bandwidth_mhz"),
        ),
        Id525SensorEntityDescription(
            key=f"{slug}_pci",
            translation_key=f"{slug}_pci",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
            value_fn=_cell_value(network, "pci"),
        ),
        Id525SensorEntityDescription(
            key=f"{slug}_arfcn",
            translation_key=f"{slug}_arfcn",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
            value_fn=_cell_value(network, "arfcn"),
        ),
        Id525SensorEntityDescription(
            key=f"{slug}_cell_id",
            translation_key=f"{slug}_cell_id",
            entity_category=EntityCategory.DIAGNOSTIC,
            entity_registry_enabled_default=False,
            value_fn=_cell_value(network, "cell_id"),
        ),
    )


SENSORS: tuple[Id525SensorEntityDescription, ...] = (
    Id525SensorEntityDescription(
        key="sim_state",
        translation_key="sim_state",
        device_class=SensorDeviceClass.ENUM,
        options=SIM_STATE_OPTIONS,
        value_fn=lambda d: d.status.sim_state.name.lower(),
    ),
    Id525SensorEntityDescription(
        key="signal_level",
        translation_key="signal_level",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.status.signal_level,
    ),
    Id525SensorEntityDescription(
        key="network",
        translation_key="network",
        value_fn=lambda d: d.status.operation_mode or None,
    ),
    Id525SensorEntityDescription(
        key="connected_since",
        translation_key="connected_since",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: (
            _since(d.fetched_at, d.status.connection_duration) if d.status.is_connected else None
        ),
    ),
    Id525SensorEntityDescription(
        key="data_sent",
        translation_key="data_sent",
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=lambda d: d.status.data_sent_gb,
    ),
    Id525SensorEntityDescription(
        key="data_received",
        translation_key="data_received",
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=lambda d: d.status.data_received_gb,
    ),
    Id525SensorEntityDescription(
        key="wan_ipv4",
        translation_key="wan_ipv4",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.status.ipv4.address,
    ),
    Id525SensorEntityDescription(
        key="wan_ipv6",
        translation_key="wan_ipv6",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.status.ipv6.address,
    ),
    Id525SensorEntityDescription(
        key="connected_clients",
        translation_key="connected_clients",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: len(d.clients),
    ),
    Id525SensorEntityDescription(
        key="wifi_clients_2g",
        translation_key="wifi_clients_2g",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.status.wifi_clients_2g,
    ),
    Id525SensorEntityDescription(
        key="wifi_clients_5g",
        translation_key="wifi_clients_5g",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.status.wifi_clients_5g,
    ),
    *_cell_descriptions("5G", "nr"),
    *_cell_descriptions("4G", "lte"),
    Id525SensorEntityDescription(
        key="cpu_usage",
        translation_key="cpu_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
        value_fn=lambda d: d.utilization.cpu_percent.current,
    ),
    Id525SensorEntityDescription(
        key="memory_usage",
        translation_key="memory_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
        value_fn=lambda d: d.utilization.memory_percent.current,
    ),
    Id525SensorEntityDescription(
        key="download_rate",
        translation_key="download_rate",
        native_unit_of_measurement=UnitOfDataRate.BITS_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda d: d.utilization.downlink_bps.current,
    ),
    Id525SensorEntityDescription(
        key="upload_rate",
        translation_key="upload_rate",
        native_unit_of_measurement=UnitOfDataRate.BITS_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda d: d.utilization.uplink_bps.current,
    ),
    Id525SensorEntityDescription(
        key="last_boot",
        translation_key="last_boot",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: _since(d.fetched_at, d.utilization.uptime),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Id525ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        Id525Sensor(coordinator, description) for description in SENSORS
    ]
    entities.append(Id525PollingStateSensor(coordinator))
    if coordinator.data.sms is not None:
        entities.append(Id525SmsSensor(coordinator))
    async_add_entities(entities)


class Id525Sensor(Id525Entity, SensorEntity):
    """A router sensor."""

    entity_description: Id525SensorEntityDescription

    def __init__(
        self, coordinator: Id525Coordinator, description: Id525SensorEntityDescription
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType | datetime:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)


class Id525SmsSensor(Id525Entity, SensorEntity):
    """Unread SMS counter; the latest message is exposed as attributes."""

    _attr_translation_key = "unread_sms"
    _attr_state_class = SensorStateClass.MEASUREMENT
    # message contents and numbers stay out of the recorder database
    _unrecorded_attributes = frozenset(
        {"last_message_from", "last_message_text", "last_message_time"}
    )

    def __init__(self, coordinator: Id525Coordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, "unread_sms")

    @property
    def native_value(self) -> int | None:
        """Return the number of unread messages."""
        sms = self.coordinator.data.sms
        return sms.unread_count if sms is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the total count and the latest inbound message."""
        sms = self.coordinator.data.sms
        if sms is None:
            return {}
        latest = sms.latest
        return {
            "total_messages": len(sms.inbound),
            "last_message_from": latest.phone_number if latest else None,
            "last_message_text": latest.text if latest else None,
            "last_message_time": (
                (latest.time.isoformat() if latest.time else latest.time_raw) if latest else None
            ),
        }


class Id525PollingStateSensor(Id525Entity, SensorEntity):
    """Shows whether the integration is polling, paused or backing off."""

    _attr_translation_key = "polling_state"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _available_when_not_polling = True

    def __init__(self, coordinator: Id525Coordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, "polling_state")
        self._attr_options = [state.value for state in PollingState]

    @property
    def native_value(self) -> str:
        """Return the polling state."""
        return self.coordinator.polling_state.value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return when polling resumes after a back-off."""
        until = self.coordinator.backoff_until
        if self.coordinator.polling_state is PollingState.BACKOFF and until is not None:
            return {"resumes_at": until.isoformat()}
        return {}
