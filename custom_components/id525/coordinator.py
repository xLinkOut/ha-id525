"""Data update coordinator for the General Mobile ID525 integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING

from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from id525 import (
    CellularInfo,
    ConnectedClient,
    DeviceInfo,
    Id525AuthenticationError,
    Id525Client,
    Id525Error,
    Id525LoginLockedError,
    Id525SessionKickedError,
    NetworkStatus,
    SmsInbox,
    Utilization,
)

from .const import (
    CONF_FETCH_SMS,
    CONF_KICK_BACKOFF,
    DEFAULT_FETCH_SMS,
    DEFAULT_KICK_BACKOFF,
    DEFAULT_LOCKOUT_BACKOFF,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LOGGER,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

type Id525ConfigEntry = ConfigEntry[Id525Coordinator]


class PollingState(StrEnum):
    """Whether the integration is currently talking to the router."""

    ACTIVE = "active"
    PAUSED = "paused"
    """Paused by the user (switch), the admin session is free for the web UI."""
    BACKOFF = "backoff"
    """Temporarily stopped because another login took the session, or lockout."""


@dataclass(frozen=True, slots=True)
class Id525Data:
    """Snapshot of the router state."""

    status: NetworkStatus
    clients: tuple[ConnectedClient, ...]
    cells: CellularInfo
    utilization: Utilization
    sms: SmsInbox | None
    fetched_at: datetime


class Id525Coordinator(DataUpdateCoordinator[Id525Data]):
    """Polls the router, respecting its single admin session."""

    config_entry: Id525ConfigEntry
    router: DeviceInfo

    def __init__(self, hass: HomeAssistant, entry: Id525ConfigEntry, client: Id525Client) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self.client = client
        self.paused = False
        self.backoff_until: datetime | None = None
        self._explicit_login = False

    @property
    def polling_state(self) -> PollingState:
        """Return the current polling state."""
        if self.paused:
            return PollingState.PAUSED
        if self.backoff_until is not None and dt_util.utcnow() < self.backoff_until:
            return PollingState.BACKOFF
        return PollingState.ACTIVE

    async def async_pause(self) -> None:
        """Pause polling and log out, freeing the admin session for the web UI."""
        self.paused = True
        try:
            await self.client.logout()
        except Id525Error as err:
            LOGGER.debug("Logout while pausing failed: %s", err)
        self.async_update_listeners()

    async def async_resume(self) -> None:
        """Resume polling now (takes the admin session back)."""
        self.paused = False
        self.backoff_until = None
        await self.async_request_refresh()

    async def _async_setup(self) -> None:
        """Fetch static device information once."""
        try:
            self.router = await self.client.get_device_info()
        except Id525AuthenticationError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except Id525Error as err:
            raise UpdateFailed(f"cannot read device information: {err}") from err

    async def _async_update_data(self) -> Id525Data:
        if self.polling_state is not PollingState.ACTIVE:
            return self._previous_or_fail(f"polling {self.polling_state.value}")
        self.backoff_until = None
        options = self.config_entry.options
        try:
            if self._explicit_login:
                await self.client.login()  # clears the client's lockout latch
                self._explicit_login = False
            await self.client.ensure_session()  # must come first: detects kicks
            status = await self.client.get_network_status()
            clients = await self.client.get_clients()
            sms = (
                await self.client.get_sms()
                if options.get(CONF_FETCH_SMS, DEFAULT_FETCH_SMS)
                else None
            )
            cells = await self.client.get_cellular_info()
            utilization = await self.client.get_utilization()
        except Id525SessionKickedError:
            minutes = options.get(CONF_KICK_BACKOFF, DEFAULT_KICK_BACKOFF)
            self._start_backoff(timedelta(minutes=minutes))
            LOGGER.info(
                "Another login (probably the web UI) took over the router session; "
                "polling paused for %s minutes",
                minutes,
            )
            return self._previous_or_fail("router session taken over by another login")
        except Id525LoginLockedError as err:
            self._start_backoff(timedelta(seconds=err.lock_time or DEFAULT_LOCKOUT_BACKOFF))
            self._explicit_login = True
            raise UpdateFailed(f"router is refusing logins: {err}") from err
        except Id525AuthenticationError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except Id525Error as err:
            raise UpdateFailed(str(err)) from err
        return Id525Data(
            status=status,
            clients=clients,
            cells=cells,
            utilization=utilization,
            sms=sms,
            fetched_at=dt_util.utcnow(),
        )

    def _start_backoff(self, delay: timedelta) -> None:
        self.backoff_until = dt_util.utcnow() + delay

    def _previous_or_fail(self, reason: str) -> Id525Data:
        if self.data is None:
            raise UpdateFailed(reason)
        return self.data
