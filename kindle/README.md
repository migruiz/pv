# Kindle solar dashboard

An old Kindle 4 (non-touch) repurposed as an always-on, mains-powered e-ink solar dashboard. The PV API draws the picture; the Kindle only downloads and shows it.

```
Inverter ──> pv-solar-api (Pi) ──GET /dashboard.png──> Kindle
  every 3 s   renders 800x600 1-bit PNG    Bearer KINDLE_TOKEN, LAN, plain HTTP, every 3 s
```

## What the screen shows

- Battery % and a battery bar
- Battery-empty time: `↓ 11:40p` is a **fixed placeholder**, not yet calculated
- Solar production kW (sun icon) and home consumption kW (bolt icon)
- `Updated HH:MM:SS` (Dublin time of the inverter reading), or a **STALE DATA** banner with the last good readings when the inverter stops answering

## How it works

**API side** (`api/kindle_dashboard/`): `GET /dashboard.png` reuses the `/dashboard` data, renders it with Pillow and the bundled DejaVu fonts, and always answers 200 with a PNG. It only accepts `Authorization: Bearer <KINDLE_TOKEN>`, a read-only token separate from `API_KEY`, so the Kindle cannot control the battery. It only re-draws when a new inverter reading arrives, so polling every few seconds is cheap.

**Kindle side** (this folder): a KOReader plugin started from the KUAL menu. The Kindle is always on mains power, so it stays awake with Wi-Fi on and every 3 seconds (`interval`) it:

1. downloads the PNG and displays it with a partial e-ink update,
2. does a full e-ink refresh every 100th picture (`full_refresh_every`) to clear ghosting.

Pictures are written to `/tmp` (RAM), not the Kindle's flash. If a download fails, the previous image stays on screen and the next tick tries again; if Wi-Fi drops, the plugin asks the Kindle to rejoin quietly. Failures are logged only occasionally so KOReader's log stays small.

The Kindle uses the LAN address `http://192.168.0.11:8100/dashboard.png`, not `pv.tenjo.ovh`: the K4 cannot do modern TLS, and the plugin only accepts `http://<IP>:<port>/dashboard.png`.

## Everyday use

- **Start**: KUAL → **Solar dashboard**
- **Exit**: press **Back**.
- Always exit KOReader before connecting USB.

## Files

| Repo path | Device path | Purpose |
|-----------|-------------|---------|
| `koreader/plugins/solardashboard.koplugin/main.lua` | `/mnt/us/koreader/plugins/solardashboard.koplugin/` | Refresh loop and display |
| `extensions/solar-dashboard/` | `/mnt/us/extensions/solar-dashboard/` | KUAL menu entry that launches KOReader with the plugin |
| `solar-dashboard-config.json` (gitignored) | `/mnt/us/koreader/settings/solar-dashboard.json` | URL, token, interval, full refresh cadence |
| `install.py` | — | USB installer (backs up replaced files to `backups/`) |

`.sh` and `.lua` files must keep LF line endings (enforced by `.gitattributes` and checked by `install.py`).

## Install or update

1. Create `kindle/solar-dashboard-config.json` from the example; `token` must equal `KINDLE_TOKEN` on the API.
2. Exit KOReader and connect the Kindle by USB (appears as `D:`).
3. `python kindle/install.py` (pass another drive if needed: `python kindle/install.py E:/`). It also removes device files this version no longer ships (such as the old `suspend.sh`), after backing them up.
4. Eject, unplug, then KUAL → Solar dashboard.

## Local chart layout preview

From `api/`, run `uv run python ../kindle/preview.py`, then open
`http://127.0.0.1:8765/`. This preview renders an 800x600 monochrome PNG at
460x345 browser pixels and refreshes every 2 seconds.
Use `--port 8766` to run a separate preview when the default port is occupied.

To view captured real readings, add `--history-csv <path>` pointing to a normalized
FusionSolar CSV with `timestamp_utc`, `pv_kw`, `home_kw`, `battery_soc`,
`battery_signed_kw` (positive charging), and `inverter_ac_kw` columns.
This mode replaces all mock readings and state icons. It uses a five-minute
grid covering twelve hours ending at the latest captured reading; missing slots
are left blank. The browser title and image tooltip identify the snapshot time.
The page still refreshes every two seconds, but a captured file is a fixed
snapshot loaded at startup, with `now` meaning its latest reading time.

For the exact live PNG served to the Kindle, use
`--live-config kindle/solar-dashboard-config.json` from the repo root.
The local server forwards authenticated requests to the configured Pi URL;
the token stays on the server and is never included in the browser page.
The browser title identifies live mode and refreshes every two seconds.

All preview readings and history are mock data. All three charts share a
12-hour horizontal axis: **now minus 12 hours at the left, now at the right**,
using 145 samples spaced five minutes apart. The production chart has guides at
5 and 2 kW. History is clipped to the chart bounds, keeping the number's area clear;
portions above 5 kW are hidden rather than flattened along the top guide.
Mock production includes hour-long plateaus at 7, 6.5, 5.5, and 6 kW to demonstrate
this clipping. The consumption chart uses 3 and 1 kW guides, likewise clipping
anything above 3 kW to keep its reading clear.
Each chart labels the start and midpoint below its baseline with Dublin hours
rounded to the nearest hour (for example, `11p` and `5a`), without minutes,
and labels the right endpoint `now`.
Inside the battery, 0–100% runs bottom to top;
the latest point ends at the positive terminal side at the displayed percentage.
The trace is white over the black charge fill and black over the unfilled area.
Charging at 0.1 kW or more adds a borderless lightning bolt above the battery
terminal; discharging at 0.1 kW or more adds a downward arrow below it.
Below 0.1 kW, neither battery icon is shown. Compare the mock states
at `http://127.0.0.1:8765/?battery=charging`, `?battery=discharging` (default),
or `?battery=idle`.
The estimated empty time has a small upright empty-battery icon before it.
A remaining-energy value (compact `3.5k` format) is left-aligned above the percent
symbol, using SOC times the configured 4.8 kWh usable capacity; the percentage
position stays fixed.
A grid pylon and export power appear to the left of the percentage only when
`grid_importing` is false and `grid_kw` is at least 0.1 kW. The preview defaults to a
mock 3.2 kW export; use `&grid=importing` or `&grid=idle` to hide the indicator.
The production endpoint uses this layout with stored history and live inverter
readings. The optional `history` argument also allows standalone previews.

### Simple sunset battery estimate

Both renderer layouts calculate the empty time from current SOC using
`SOC / 100 × 4.8 kWh / 0.25 kW`. During daylight, this runtime starts at
today's sunset; at night (including after midnight before sunrise), it starts
at the reading time. Zero charge means already empty; unavailable SOC shows
`--:--`. A small sunset icon and today's sunset time appear below the estimate.

Astral calculates sunrise/sunset locally for Dublin (53.3498, -6.2603), with
the Europe/Dublin timezone and daylight-saving changes. No web API or network
request is required. The estimate uses full-precision energy; the displayed
energy and clock are rounded. Elapsed runtime is calculated in UTC across
clock changes. When readings are stale, the estimate stays tied to those
readings and the existing STALE DATA banner remains visible.

This deliberately simple baseline scenario assumes solar covers the house
until sunset, then a constant 0.25 kW battery load until 0% SOC. It does not
forecast later solar/cheap-rate charging, scheduled export, extra appliance
loads, a reserve or conversion losses. The preview still uses mock SOC/history;
its sunset is real for the current date and its empty time is calculated.

### FusionSolar history verification (15 September 2026)

Read-only cloud requests using the existing saved session returned all three
series in five-minute samples. For the requested 00:41–12:41 Dublin window,
143 aligned samples were available from 00:45 through 12:35, without internal
gaps; the newest few minutes had not reached the cloud yet.

- PV: `/rest/pvms/web/device/v1/device-history-data`, inverter DN,
  signal `30017` (DC input kW, matching the local reader's `pv_kw`).
- Battery SOC: the same endpoint, battery DN, signal `30007` (%).
  Signal `30005` also supplies signed battery kW, positive when charging.
- Home: `/rest/pvms/web/station/v1/overview/energy-balance`, `usePower` (kW).
  The plant `soc` array was empty, so battery device history is required.

Device responses use `data[signal].pmDataList`, with Unix-second `startTime`
and `counterValue`. The request's `date` is milliseconds: use local noon on
the requested day, then validate returned dates. Dublin midnight during summer
selected the previous day in the device endpoint. Plant requests use `timeDim=2`,
local-midnight `queryTime` in milliseconds, `timeZoneStr=Europe/Dublin` and the
date's UTC offset in hours as `timeZone`. Its `xAxis` contains Dublin-local
date/time strings aligned with the value arrays. Across midnight, fetch both
days and filter the merged result by actual timestamps, in UTC.

Device history uses `1.7976931348623157e+308` for unavailable/future samples;
plant history uses `--`. Preserve those as missing, never zero. The plant's
`productPower` differed slightly from device DC power, so use device `30017`
for consistency with current solar readings. Plant `chargeAndDisChargePower`
uses the opposite sign to device `30005`.

### Persistent API history

The API stores history in `/data/history.sqlite3` on its existing Docker volume
(local default: `api/history.sqlite3`; override with `HISTORY_DB_PATH`). Each
successful inverter polling round updates a one-minute record: solar and home
power are averaged across the polls, while SOC is the latest percentage.
Thirty days are retained. SQLite uses WAL mode, and disk I/O runs off the async
event loop. Storage failures do not reconnect the inverter or hide live readings.

On first deployment, a background job seeds the preceding twelve hours from
FusionSolar using the existing serialized cloud session. It tries at most three
times per startup and records completion in the database. Once seeded, restarts
do not request cloud chart history again. Local records take precedence over
cloud samples. If initial backfill is unavailable, live collection continues.

`/dashboard.png` reads only the inverter cache and local database. It makes no
cloud or inverter requests itself. All charts use real timestamps, ending at
the current reading and starting twelve hours earlier; the renderer connects
adjacent five-minute cloud points and minute-level local points, leaving longer
outages blank. The cache is invalidated both by new readings and completed seed
imports. Existing Kindle authentication, polling and stale-data banner remain.

## Tests

```bash
# Plugin (runs main.lua in LuaJIT with a simulated KOReader)
uv run --no-project --with lupa python -m unittest discover -s kindle/tests -v

# API renderer and endpoint
cd api && uv run pytest tests/test_kindle_dashboard.py -v
```

## Device

- Kindle 4 non-touch (serial prefix D01100), firmware 4.1.4
- Jailbroken with NiLuJe's K4 jailbreak 1.8.N; MKK 20141129 plus 2025 developer certificates
- KUAL 2.7.37, KOReader v2026.07.1 (`kindle` build, not `legacy`/`kindlepw2`/`kindlehf`)
- References: [Kindle4NTHacking](https://wiki.mobileread.com/wiki/Kindle4NTHacking), [KOReader on Kindle](https://github.com/koreader/koreader/wiki/Installation-on-Kindle-devices)
