"""SMS event for the General Mobile ID525 integration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.event import EventEntity
from homeassistant.core import callback

from .entity import Id525Entity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
    from id525 import SmsInbox, SmsMessage

    from .coordinator import Id525ConfigEntry, Id525Coordinator

PARALLEL_UPDATES = 0

EVENT_RECEIVED = "received"

type _MessageKey = tuple[int, str, str]


def _key(message: SmsMessage) -> _MessageKey:
    return (message.index, message.phone_number, message.time_raw)


def _inbound_keys(sms: SmsInbox | None) -> set[_MessageKey]:
    return {_key(m) for m in sms.inbound} if sms is not None else set()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Id525ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the SMS event, if SMS messages are read."""
    coordinator = entry.runtime_data
    if coordinator.data.sms is not None:
        async_add_entities([Id525SmsEvent(coordinator)])


class Id525SmsEvent(Id525Entity, EventEntity):
    """Fires once for every inbound SMS that shows up while Home Assistant runs.

    Messages already in the router when the integration starts are not
    reported. Sender and text stay out of the recorder database.
    """

    _attr_translation_key = "sms"
    _unrecorded_attributes = frozenset({"phone_number", "text", "time"})

    def __init__(self, coordinator: Id525Coordinator) -> None:
        """Initialise the event, treating the messages stored now as already seen."""
        super().__init__(coordinator, "sms")
        self._attr_event_types = [EVENT_RECEIVED]
        self._seen = _inbound_keys(coordinator.data.sms)

    @callback
    def _handle_coordinator_update(self) -> None:
        sms = self.coordinator.data.sms
        if sms is not None:
            new = [m for m in sms.inbound if _key(m) not in self._seen]
            new.sort(key=lambda m: (m.time.timestamp() if m.time else float("-inf"), m.index))
            for message in new:
                self._trigger_event(
                    EVENT_RECEIVED,
                    {
                        "phone_number": message.phone_number,
                        "text": message.text,
                        "time": message.time.isoformat() if message.time else message.time_raw,
                    },
                )
            self._seen = _inbound_keys(sms)
        super()._handle_coordinator_update()
