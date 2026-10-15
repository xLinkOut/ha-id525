# General Mobile ID525 for Home Assistant

Custom integration (HACS) for the **General Mobile ID525** 5G FWA router
(sold in Italy by TIM as *FWA 5G*). Built on the
[`id525`](https://github.com/xLinkOut/python-id525) client library.

> Unofficial project, not affiliated with General Mobile or TIM.

## What you get

| Platform | Entities |
|---|---|
| Sensor | SIM state, signal level, network, data sent/received, connected clients, 5G and 4G RSRP / RSRQ / SINR / band, CPU and memory usage, download/upload rate, unread SMS (latest message as attributes), plus diagnostics: WAN IPs, bandwidth, PCI, ARFCN, cell ID, connected since, last boot, polling state, firewall level, VoIP line, SIM PIN / PUK attempts left, data counters reset date, data limit |
| Binary sensor | Cellular connection, roaming, Wi-Fi, plus diagnostics: VPN passthrough, port forwarding, DMZ, URL / IP / MAC filter (mode and rule count as attributes), SIM PIN lock |
| Event | **SMS**: fires for every message that arrives while Home Assistant runs (sender and text as attributes, not recorded in history) |
| Device tracker | One per LAN client (disabled by default) |
| Switch | **Polling**: turn it off to free the router's admin session |
| Button | **Restart** the router (only with *Allow commands*) |

The settings (firewall, filters, port forwarding, VoIP, SIM PIN, data usage)
are read every 10 minutes, not on every update.

By default the integration is **read-only**: it never sends a command to the
router and never marks SMS messages as read. The *Allow commands* option
enables the Restart button and the actions below; even then, the router's
configuration is never changed.

## Actions

Both need the *Allow commands* option and return the router's answer
(use *Developer tools → Actions*, or `response_variable` in a script).

| Action | Fields | Returns |
|---|---|---|
| `id525.ping` | `host`, `count` (1–100), `size`: the router's defaults if omitted | `lines`, one per reply, and `completed` |
| `id525.traceroute` | `host`: the router's default if omitted | `lines`, one per hop, and `completed`. Can take minutes. |

The router handles one request at a time, so updates wait while a ping or
traceroute runs. Commands are refused while polling is paused or backing off:
logging in then would take the session away from the web UI.

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

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=xLinkOut&repository=ha-id525&category=integration)

1. HACS → ⋮ → *Custom repositories* → add `https://github.com/xLinkOut/ha-id525`
   (category *Integration*), or use the button above, then install
   **General Mobile ID525**.
2. Restart Home Assistant.
3. *Settings → Devices & services → Add integration → General Mobile ID525*,
   then enter the router address (default `192.168.224.1`), username and password.

## Options

| Option | Default | |
|---|---|---|
| Update interval | 60 s | Time between two reads of the router |
| Pause after a web UI login | 15 min | Back-off after another login took the session |
| Read SMS messages | on | Unread SMS sensor; message texts are not recorded in history |
| Allow commands | off | Restart button and the ping / traceroute actions |

## Privacy

Diagnostics redact credentials, IMEI/IMSI, serial number, phone number, MAC/IP
addresses, SSIDs, cell identifiers and the session token. They don't include
the client list, SMS contents, filter / forwarding rules or VoIP credentials.

## Development

```bash
uv sync            # expects ../python-id525 next to this repository
uv run pytest
uv run ruff check . && uv run mypy
```

## License

MIT
