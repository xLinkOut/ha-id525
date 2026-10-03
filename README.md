# General Mobile ID525 for Home Assistant

Custom integration (HACS) for the **General Mobile ID525** 5G FWA router
(sold in Italy by TIM as *FWA 5G*). Built on the read-only
[`id525`](https://github.com/xLinkOut/python-id525) client library.

> Unofficial project, not affiliated with General Mobile or TIM.

## What you get

| Platform | Entities |
|---|---|
| Sensor | SIM state, signal level, network, data sent/received, connected clients, 5G and 4G RSRP / RSRQ / SINR / band, CPU and memory usage, download/upload rate, unread SMS (latest message as attributes), plus diagnostics: WAN IPs, bandwidth, PCI, ARFCN, cell ID, connected since, last boot, polling state |
| Binary sensor | Cellular connection, roaming, Wi-Fi |
| Device tracker | One per LAN client (disabled by default) |
| Switch | **Polling**: turn it off to free the router's admin session |

The integration is **read-only**: it never changes the router's configuration
and never marks SMS messages as read.

## The single admin session

The router accepts **one administrator session at a time**:

- While Home Assistant polls, logging into the router's web UI kicks Home
  Assistant out. The integration notices it and **stays away for a while**
  (15 minutes by default, configurable), so your web UI session isn't kicked
  back. Entities are *unavailable* in the meantime and the *Polling state*
  sensor shows `backoff`.
- For longer web UI sessions, turn off the **Polling** switch. Home Assistant
  logs out and doesn't log in again until you turn it back on, even after a
  restart.
- The router ends every session after 5 minutes (configurable in the web UI),
  regardless of activity, so the integration logs in again periodically. If
  you log into the web UI right after such an expiry, the integration notices
  that too and backs off instead of kicking you out.
- After a router restart the integration can't tell a restart from a web UI
  login, so it also waits for the back-off period before polling again.

## Installation

1. HACS → ⋮ → *Custom repositories* → add `https://github.com/xLinkOut/ha-id525`
   (category *Integration*), then install **General Mobile ID525**.
2. Restart Home Assistant.
3. *Settings → Devices & services → Add integration → General Mobile ID525*,
   then enter the router address (default `192.168.224.1`), username and password.

## Options

| Option | Default | |
|---|---|---|
| Update interval | 60 s | Time between two reads of the router |
| Pause after a web UI login | 15 min | Back-off after another login took the session |
| Read SMS messages | on | Unread SMS sensor; message texts are not recorded in history |

## Privacy

Diagnostics redact credentials, IMEI/IMSI, serial number, phone number, MAC/IP
addresses, SSIDs and cell identifiers. They don't include the client list or
SMS contents.

## Development

```bash
uv sync            # expects ../python-id525 next to this repository
uv run pytest
uv run ruff check . && uv run mypy
```

## License

MIT
