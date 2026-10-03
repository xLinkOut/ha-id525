"""Constants for the General Mobile ID525 integration."""

from __future__ import annotations

import logging
from typing import Final

from id525.const import DEFAULT_HOST as ROUTER_DEFAULT_HOST
from id525.const import DEFAULT_USERNAME as ROUTER_DEFAULT_USERNAME

DOMAIN: Final = "id525"
LOGGER = logging.getLogger(__package__)

MANUFACTURER: Final = "General Mobile"

DEFAULT_HOST: Final = ROUTER_DEFAULT_HOST
DEFAULT_USERNAME: Final = ROUTER_DEFAULT_USERNAME

CONF_KICK_BACKOFF: Final = "kick_backoff"
CONF_FETCH_SMS: Final = "fetch_sms"

DEFAULT_SCAN_INTERVAL: Final = 60  # seconds
MIN_SCAN_INTERVAL: Final = 30
MAX_SCAN_INTERVAL: Final = 3600
DEFAULT_KICK_BACKOFF: Final = 15  # minutes
MIN_KICK_BACKOFF: Final = 1
MAX_KICK_BACKOFF: Final = 240
DEFAULT_FETCH_SMS: Final = True
DEFAULT_LOCKOUT_BACKOFF: Final = 300  # seconds, if the router gives no lock_time
