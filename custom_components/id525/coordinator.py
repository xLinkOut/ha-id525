"""Data update coordinator for the General Mobile ID525 integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING

from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from id525 import (
    AccountSettings,
    CellularInfo,
    ConnectedClient,
    DeviceInfo,
    FirewallSettings,
    Id525AuthenticationError,
    Id525Client,
    Id525ConnectionError,
    Id525Error,
    Id525LoginLockedError,
    Id525SessionError,
    Id525SessionKickedError,
    Id525ValidationError,
    IpFilterSettings,
    MacFilterSettings,
    NetworkStatus,
    PortForwardingSettings,
    SimPinStatus,
    SmsInbox,
    UrlFilterSettings,
    Utilization,
    VoipSettings,
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
    SETTINGS_INTERVAL,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

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
class Id525Settings:
    """Router settings, read from the UI pages every :data:`SETTINGS_INTERVAL`."""

    firewall: FirewallSettings
    port_forwarding: PortForwardingSettings
    url_filter: UrlFilterSettings
    ip_filter: IpFilterSettings
    mac_filter: MacFilterSettings
    account: AccountSettings
    voip: VoipSettings
    sim_pin: SimPinStatus
    fetched_at: datetime


@dataclass(frozen=True, slots=True)
class Id525Data:
    """Snapshot of the router state."""

    status: NetworkStatus
    clients: tuple[ConnectedClient, ...]
    cells: CellularInfo
    utilization: Utilization
    sms: SmsInbox | None
    settings: Id525Settings | None
    """``None`` until the settings pages could be read once."""
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
        self._settings_due: datetime | None = None

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
            await self._async_open_session()  # must come first: detects kicks
            status = await self.client.get_network_status()
            clients = await self.client.get_clients()
            sms = (
                await self.client.get_sms()
                if options.get(CONF_FETCH_SMS, DEFAULT_FETCH_SMS)
                else None
            )
            cells = await self.client.get_cellular_info()
            utilization = await self.client.get_utilization()
            settings = await self._async_settings()
        except Id525SessionKickedError:
            self._kicked()
            return self._previous_or_fail("router session taken over by another login")
        except Id525LoginLockedError as err:
            self._locked_out(err)
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
            settings=settings,
            fetched_at=dt_util.utcnow(),
        )

    async def _async_settings(self) -> Id525Settings | None:
        """Return fresh settings when due, else the previous ones.

        A settings page the client cannot read is logged and the previous
        settings are kept (retried at the next interval), so the status
        sensors stay available.
        """
        previous = self.data.settings if self.data is not None else None
        now = dt_util.utcnow()
        if self._settings_due is not None and now < self._settings_due:
            return previous
        self._settings_due = now + SETTINGS_INTERVAL
        client = self.client
        try:
            settings = Id525Settings(
                firewall=await client.firewall.get_settings(),
                port_forwarding=await client.port_forwarding.get_settings(),
                url_filter=await client.url_filter.get_settings(),
                ip_filter=await client.ip_filter.get_settings(),
                mac_filter=await client.mac_filter.get_settings(),
                account=await client.account.get_settings(),
                voip=await client.voip.get_settings(),
                sim_pin=await client.status.get_sim_pin_status(),
                fetched_at=now,
            )
        except Id525AuthenticationError, Id525ConnectionError, Id525SessionError:
            raise
        except Id525Error as err:
            LOGGER.warning("Cannot read the router settings: %s", err)
            return previous
        return settings

    async def async_run[T](self, command: Callable[[], Awaitable[T]]) -> T:
        """Run a command on the router for an entity or an action.

        Refused while polling is paused or backing off: logging in now would
        take the admin session away from the web UI. Like a polling cycle, it
        validates the session first, so a take-over is detected, not undone.
        """
        state = self.polling_state
        if state is not PollingState.ACTIVE:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="polling_inactive",
                translation_placeholders={"state": state.value},
            )
        try:
            await self._async_open_session()
            return await command()
        except Id525ValidationError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_input",
                translation_placeholders={"error": str(err)},
            ) from err
        except Id525SessionKickedError as err:
            self._kicked()
            self.async_update_listeners()
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="session_taken"
            ) from err
        except Id525LoginLockedError as err:
            self._locked_out(err)
            self.async_update_listeners()
            raise self._command_failed(err) from err
        except Id525AuthenticationError as err:
            self.config_entry.async_start_reauth(self.hass)
            raise self._command_failed(err) from err
        except Id525Error as err:
            raise self._command_failed(err) from err

    @staticmethod
    def _command_failed(err: Id525Error) -> HomeAssistantError:
        return HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="command_failed",
            translation_placeholders={"error": str(err)},
        )

    async def _async_open_session(self) -> None:
        """Log in again after a lockout, then validate the session (detects kicks)."""
        if self._explicit_login:
            await self.client.login()  # clears the client's lockout latch
            self._explicit_login = False
        await self.client.ensure_session()

    def _locked_out(self, err: Id525LoginLockedError) -> None:
        self._start_backoff(timedelta(seconds=err.lock_time or DEFAULT_LOCKOUT_BACKOFF))
        self._explicit_login = True

    def _kicked(self) -> None:
        minutes = self.config_entry.options.get(CONF_KICK_BACKOFF, DEFAULT_KICK_BACKOFF)
        self._start_backoff(timedelta(minutes=minutes))
        LOGGER.info(
            "Another login (probably the web UI) took over the router session; "
            "polling paused for %s minutes",
            minutes,
        )

    def _start_backoff(self, delay: timedelta) -> None:
        self.backoff_until = dt_util.utcnow() + delay

    def _previous_or_fail(self, reason: str) -> Id525Data:
        if self.data is None:
            raise UpdateFailed(reason)
        return self.data
