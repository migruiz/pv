# PV Solar Manager

Home solar PV monitoring and battery discharge windows for a Huawei SUN2000 installation in Dublin, Ireland. Consists of a Python API backend and an Android mobile app.

## Architecture

```
┌─────────────┐     HTTPS      ┌────────────────┐   WiFi hotspot, Modbus TCP   ┌──────────────────┐
│  Android App │ ──────────────→│  FastAPI        │ ────────────────────────────→│  SUN2000 inverter │
│  (Compose)   │  pv.tenjo.ovh │  (Raspberry Pi) │  192.168.8.1:6607 installer  │  + LUNA2000       │
└─────────────┘                └────────────────┘                              └──────────────────┘
                               Cloudflare Tunnel
```

- **API** (`api/`): FastAPI service. Readings and battery commands go straight to the inverter over its WiFi hotspot (Modbus TCP, polled every 3 s). The API does not use the FusionSolar cloud; the FusionSolar app and portal keep working on their own
- **App** (`app/`): Android Kotlin/Jetpack Compose mobile app with live energy flow dashboard and discharge windows
- **Mock** (`mock/`): Node.js/TypeScript solar system simulator with React UI, standing in for the inverter in development
- **Kindle** (`kindle/`): KOReader plugin for a jailbroken Kindle 4 that shows an e-ink dashboard PNG rendered by the API (`GET /dashboard.png`)
- **Deployment**: Docker container on Raspberry Pi 4 (arm64), exposed via Cloudflare tunnel at `https://pv.tenjo.ovh`

## Plant Details

- **Owner**: Miguel Ruiz (account: soniablanco)
- **Location**: Dublin D24 XA48, Ireland
- **Capacity**: 7.650 kWp
- **Grid connection**: 2026-02-04
- **FusionSolar** (app and portal only, not used by the API): subdomain `uni003eu5`, plant `NE=239198726`
- **Devices**:
  - Inverter: SUN2000-5K-LB0, `NE=239198740` (5 kW rated, 2 MPPT strings, built-in WLAN, no Smart Dongle)
  - Battery: `NE=239198746` (5 kWh, LUNA2000)
  - Power Sensor: `NE=239198748`
- **TOU schedule** (set in the FusionSolar app, never written by the API): charge from the grid 02:05-04:55, discharge to load the rest of the day

## Project Structure

```
pv/
├── api/                          # Python FastAPI backend
│   ├── main.py                   # FastAPI app, lifespan, mock clock endpoints
│   ├── mock_clock.py             # Dublin clock; virtual in mock mode (set/advance/reset time)
│   ├── auth.py                   # API key (X-API-Key) and Kindle token (Bearer) authentication
│   ├── config.py                 # Shared constants (MOCK_MODE, inverter address, poll interval)
│   ├── notifications.py          # Firebase Cloud Messaging push notifications
│   ├── dependencies.py           # FastAPI dependency injection
│   ├── inverter/                 # The inverter's WiFi hotspot link
│   │   ├── mapping.py            # Register lists + pure mapping to the /dashboard payload
│   │   ├── reader.py             # Background Modbus poller + cache, and write() for battery commands
│   │   └── simulator.py          # Mock mode: a Modbus client stand-in backed by the mock simulator
│   ├── discharge/                # Discharge windows
│   │   ├── models.py             # Window settings, live state, list view
│   │   ├── store.py              # JSON file I/O (atomic writes, overlap check)
│   │   ├── schedule.py           # When windows run (wall clock, midnight, daylight saving): pure functions
│   │   ├── power.py              # Discharge power math (pure functions)
│   │   ├── commands.py           # Forced discharge / stop register writes
│   │   ├── controller.py         # The one rule, applied on a timer and after every change
│   │   └── router.py             # /discharge-windows endpoints
│   ├── routers/                  # Other API routers
│   │   ├── dashboard.py          # Dashboard endpoint
│   │   └── health.py             # Health check
│   ├── kindle_dashboard/         # Kindle e-ink dashboard
│   │   ├── renderer.py           # 800x600 1-bit PNG drawing (pure functions, bundled DejaVu fonts)
│   │   └── router.py             # GET /dashboard.png (Bearer KINDLE_TOKEN, stale-data fallback)
│   ├── tests/                    # Pytest test suite
│   │   ├── conftest.py           # Shared fixtures (mock clock reset)
│   │   ├── discharge_fakes.py    # Settable clock, fake inverter recording commands, notification capture
│   │   ├── test_discharge_controller.py  # The rule, case by case (start, correct, target, edits, failures)
│   │   ├── test_discharge_schedule.py    # Timing, daylight saving, power math, commands, store
│   │   ├── test_discharge_api.py         # /discharge-windows HTTP endpoints
│   │   ├── test_inverter.py              # Inverter reader, commands, register mapping, /dashboard
│   │   └── test_kindle_*.py              # Kindle PNG renderer, estimate and history
│   ├── Dockerfile                # Multi-arch image (amd64 + arm64)
│   ├── docker-compose.yml        # Local dev deployment
│   ├── pyproject.toml            # uv project dependencies
│   └── uv.lock                   # Locked dependencies
│
├── mock/                         # Solar system simulator
│   ├── server/
│   │   ├── index.ts              # Express server (port 3002)
│   │   ├── routes.ts             # UI state endpoints + inverter registers for the API
│   │   └── state.ts              # In-memory simulator (SOC, energy balance, command log)
│   └── src/                      # React UI (Vite, port 5173)
│
├── kindle/                       # Kindle 4 e-ink dashboard (see kindle/README.md)
│   ├── koreader/plugins/solardashboard.koplugin/  # KOReader plugin: fetch + display every 3 s (mains power)
│   ├── extensions/solar-dashboard/                # KUAL menu launcher
│   ├── install.py                # USB installer (config + token from gitignored JSON)
│   └── tests/                    # Plugin tests (LuaJIT via lupa)
│
└── app/                          # Android mobile app (Kotlin/Compose)
    ├── app/src/main/java/ovh/tenjo/pv/
    │   ├── MainActivity.kt       # Navigation (dashboard / window screen), API config
    │   ├── SolarViewModel.kt     # Dashboard + discharge window state, save/delete
    │   ├── api/SolarApi.kt       # Retrofit client, data models, API error reasons
    │   ├── AutoDischargeService.kt     # Ongoing "Discharging" notification
    │   ├── PvFirebaseMessagingService.kt # FCM message handler
    │   ├── NotificationDismissReceiver.kt # Re-post notification on swipe
    │   └── ui/
    │       ├── DashboardScreen.kt        # Energy flow diagram + discharge window list + inverter info
    │       ├── DischargeWindowScreen.kt  # New / edit window: name, start, end, duration, target, switches
    │       ├── TimePickers.kt            # Shared time/duration picker dialogs
    │       ├── TimeUtils.kt              # Shared time parsing/formatting
    │       └── theme/                    # Dark solar theme (Color, Theme, Type)
    └── gradle/libs.versions.toml # Version catalog
```

## API Endpoints

All endpoints except `/health` and `/docs` require `X-API-Key` header. `/dashboard.png` uses `Authorization: Bearer <KINDLE_TOKEN>` instead.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Age of the last inverter reading (no auth) |
| GET | `/docs` | Swagger UI |
| GET | `/dashboard` | Combined: PV, battery, grid, home power + flow directions + inverter settings, read from the inverter every 3 s (503 if no reading in 30 s) |
| GET | `/dashboard.png` | Kindle e-ink dashboard, 800x600 1-bit PNG (Bearer `KINDLE_TOKEN`, always 200) |
| GET | `/discharge-windows` | All windows by start time, each with its live `state` (discharging, power, battery %, time left, target reached) |
| POST | `/discharge-windows` | Create a window; applied before the reply (409 with the reason on overlap; `warning` if the inverter did not respond) |
| PUT | `/discharge-windows/{id}` | Replace a window's settings; applied before the reply, also to a running discharge (`warning` as for POST) |
| DELETE | `/discharge-windows/{id}` | Delete a window; a discharge it was running stops first (502, window kept, if the stop fails) |

### Mock-Only Endpoints (when MOCK_MODE=true)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/mock/time` | Get current virtual time |
| POST | `/mock/time` | Set virtual time `{"hour": 22, "minute": 0}` |
| POST | `/mock/time/advance` | Advance clock `{"minutes": 30}` |
| POST | `/mock/time/reset` | Return to real system time |

Each mock time change applies the discharge rule straight away.

## Discharge Windows

Windows are the only way the API controls the battery: there is no manual start or stop. For a one-off discharge, create a window starting now (the app's new window starts at the current time), set its end and target, and save.

Stored in `/data/discharge_windows.json` (Docker volume) or `api/discharge_windows.json` (local dev). Each window has:

- **name**
- **start_time**: "HH:MM" and **duration_minutes**: 1-1440 (the app shows start, end and duration, linked)
- **target_soc**: 0-100% (battery % to reach by the end)
- **notify**: send FCM push notifications
- **enabled**: switch off without deleting

Enabled windows cannot overlap (409 with the reason). Usually there are two: a night window, and a morning one switched off for part of the year.

### The one rule

`discharge/controller.py` keeps asking: **is an enabled window running now, and is the battery above its target?** If yes, it sends a forced discharge at the power needed to reach the target by the window's end (`(soc - target) × 4.8 kWh / hours left`, capped at 2.5 kW); if no, it stops a discharge it started. It checks:

- exactly when a window starts or ends,
- every 5 minutes while discharging, correcting the power from the latest battery % (30 s in mock mode),
- straight after every create, edit or delete (the reply already shows the result), and after a mock clock change,
- 30 s after a failed battery read or command, and at least hourly.

The next check is planned from the moment the last one read the clock, so a start or end that passes while a check is held up (a slow write) is caught at once, never skipped.

Consequences: edits to a running window (end, target, switched off, deleted, moved) take effect at once; a window moved onto the current time starts.

- **Target reached**: the window stops and is done for that day, even if solar pushes the battery back above the target. Saving the window again gives it a fresh go. Kept in memory only, so after an API restart mid-window a battery above the target is discharged again.
- **Wall-clock times**: a window runs from its start to its end on the Dublin wall clock, like the inverter's TOU schedule. On a daylight-saving night it is an hour longer or shorter in real time: 23:35 to 02:00 still ends at 02:00, before the TOU charge at 02:05.
- **Safety net**: every discharge command carries the minutes left, so the inverter stops by itself at the window's end if the API or the hotspot link dies. On shutdown a running discharge is left to that; the next start applies the rule again.
- **Maybe discharging**: the controller assumes the inverter may be force-discharging at startup and after any discharge write (even one whose reply was lost), and sends a stop whenever the rule says no until a stop is confirmed. So the first check after a start sends one stop, harmless when nothing is forced.
- **Failures are visible**: a window that is running (or may be, after a start whose reply was lost) is deleted only after its stop is confirmed (otherwise 502 and the window stays, still shown discharging); a save the inverter did not respond to replies with a `warning`, shown above the list in the app; either way the rule is retried every 30 s.
- **Notifications**: started, every correction, and stopped, only for windows with notifications on. Switching notifications off mid-discharge sends "stopped" to clear the phone. Pushes are sent in the background after the control lock is released, one at a time to completion and in order (Firebase's own HTTP timeout is 10 s), so a stalled push never delays a stop, a reply or the next check, and a late "started" can never overtake a "stopped". The app clears an ongoing notification only when a fresh, successful list (arriving over a minute after it went up) shows nothing discharging: a lost "stopped" push.

## Inverter Registers

Read and written with the `huawei-solar` library over the installer session. The battery command sequence was proven on the inverter on 2026-09-23; the FusionSolar cloud's own forced-discharge command writes these same registers.

| Register name | Use |
|---------------|-----|
| `storage_state_of_capacity` | Battery % (read every 3 s) |
| `storage_forcible_charge_discharge_setting_mode` | Written `TIME` (0): the forced discharge runs for a period |
| `storage_forced_charging_and_discharging_period` | Minutes left in the window (the inverter stops by itself after it) |
| `storage_forcible_discharge_power` | W (0-2500); about 8% less is measured at the battery |
| `forcible_charge_discharge_write` | 2 = discharge, 0 = stop; written last |

## Kindle Dashboard

A jailbroken Kindle 4 (non-touch) shows an e-ink dashboard: battery % with 12 hours of charge history inside the battery outline, battery-empty time (estimated from sunset and a 0.25 kW baseline load, `kindle_dashboard/estimate.py`) with today's sunset time, grid export kW while exporting, solar kW and home kW each with a 12-hour chart, and `Updated HH:MM:SS` (Dublin time of the inverter reading). Full device and install docs: `kindle/README.md`.

- **API** (`api/kindle_dashboard/`): `GET /dashboard.png` uses the inverter reader's cached dashboard, renders an 800x600 1-bit PNG with Pillow and bundled DejaVu fonts (in a thread, only when a new reading arrives), and always returns 200. When the inverter reading goes stale it redraws the last good readings with a **STALE DATA** banner
- **Auth**: `Authorization: Bearer <KINDLE_TOKEN>`, a read-only token separate from `API_KEY`. Unset `KINDLE_TOKEN` disables the endpoint (401)
- **Kindle** (`kindle/`): KOReader plugin started from KUAL. The Kindle stays on mains power with Wi-Fi on: every 3 s it downloads the PNG and shows it (partial e-ink update, full flash every 100 pictures). Pictures go to `/tmp` (RAM), not flash
- **Address**: the Kindle uses `http://192.168.0.11:8100/dashboard.png` on the LAN. The K4 cannot do modern TLS, and the plugin only accepts `http://<IP>:<port>/dashboard.png`

## Development

### Mock System + API (full local dev)

The simulator stands in for the inverter: it serves and accepts the same register names (`GET/POST /mock/registers`), so mock mode runs the real reader, mapping and discharge commands. Push notifications are off in mock mode, so a simulated discharge never reaches the real phone.

```bash
# Terminal 1: Start mock solar simulator (Express API on :3002, React UI on :5173)
cd mock
npm run dev

# Terminal 2: Start API in mock mode, connected to mock simulator
cd api
MOCK_MODE=1 uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

- Mock simulator UI: `http://localhost:5173` (change PV, battery SOC, home consumption; see the command log)
- Mock state: `http://localhost:3002/api/state`
- API Swagger docs: `http://localhost:8000/docs`

### Virtual Clock (mock mode only)

Control simulated time to test discharge window scheduling:

```bash
# Set time to 9:59 PM
curl -X POST -H "Content-Type: application/json" -d '{"hour":21,"minute":59}' http://localhost:8000/mock/time

# Advance 2 minutes (starts a 10 PM window)
curl -X POST -H "Content-Type: application/json" -d '{"minutes":2}' http://localhost:8000/mock/time/advance

# Reset to real time
curl -X POST http://localhost:8000/mock/time/reset
```

### Running Tests

```bash
cd api
uv run --with pytest --with pytest-asyncio --with httpx python -m pytest tests/ -q
```

Kindle plugin tests (from repo root): `uv run --no-project --with lupa python -m unittest discover -s kindle/tests -v`

Tests run in about 2 seconds with no external dependencies (no Node.js mock, no Firebase, no network). The discharge tests use:

- **Clock**: a settable Dublin clock passed to the controller, so each case sets the time it needs
- **FakeInverter**: serves a battery % and records every command written; reads or writes fail on demand
- **Captured notifications**: FCM functions are patched and the sends recorded as (kind, window) pairs
- **Isolated store**: each test gets a `tmp_path` windows file

### API (local, production mode)

Needs the inverter hotspot and `INVERTER_INSTALLER_PASS`; only one Modbus session is allowed, so not while the Pi's API is running.

```bash
cd api
uv run fastapi dev main.py
```

### API (Docker local)

```bash
cd api
docker compose up --build
```

### API (push to Docker Hub)

```bash
cd api
build-and-push.bat   # builds linux/amd64 + linux/arm64, pushes to migruiz/pv-solar-api:latest
```

### Android App

- Open `app/` in Android Studio
- API URL configured in `app/local.properties`:
  - Production: `pv.api.url=https://pv.tenjo.ovh/`
  - Local dev: `pv.api.url=http://localhost:8000/` (with `adb reverse tcp:8000 tcp:8000`)

### Install APK via ADB

```bash
# Set up port forwarding (phone localhost:8000 → PC localhost:8000)
adb reverse tcp:8000 tcp:8000

# Build and install
cd app && ./gradlew assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n ovh.tenjo.pv/.MainActivity
```

## Deployment

- **Docker Hub image**: `migruiz/pv-solar-api:latest` (multi-arch: amd64 + arm64)
- **Production host**: Raspberry Pi 4 running Docker via Portainer
- **Public URL**: `https://pv.tenjo.ovh` (Cloudflare tunnel)
- **Discharge windows config**: Persisted to `/data/discharge_windows.json` volume
- **Chart history**: `/data/history.sqlite3` volume (Kindle charts)
- **Portainer stack**: `pv` (compose at `/data/compose/68/docker-compose.yml` in the `portainer_data` volume); env vars are inline in the stack file
- **Inverter link**: the Pi's `wlan0` joins the inverter hotspot `SUN2000-TA2550448190` (NetworkManager connection `inverter-hotspot`: autoconnect with unlimited retries, `ipv4.never-default` so internet stays on `eth0`), and `wifi-radio-on.service` switches the radio on at boot. The inverter (SUN2000-5K-LB0, built-in WLAN, no Smart Dongle) answers one local Modbus session at a time, so the FusionSolar app's local screens cannot connect while the API is polling
- **Kindle dashboard**: Kindle polls `http://192.168.0.11:8100/dashboard.png` on the LAN every 3 s; install/update the plugin with `python kindle/install.py` over USB

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| API_KEY | Yes | API authentication key for X-API-Key header |
| INVERTER_INSTALLER_PASS | Yes | Installer password for the inverter's local Modbus login (provided by the installer) |
| INVERTER_HOST / INVERTER_PORT | No | Inverter hotspot address, default `192.168.8.1` / `6607` |
| INVERTER_POLL_INTERVAL | No | Seconds between inverter reads, default `3` |
| KINDLE_TOKEN | No | Read-only Bearer token for the Kindle's `/dashboard.png`; endpoint returns 401 when unset |
| HISTORY_DB_PATH | No | Chart history database, default `/data/history.sqlite3` |
| MOCK_MODE | No | Set to `1`/`true`/`yes` to use the mock simulator instead of the inverter |
| MOCK_URL | No | Mock simulator URL (default: `http://localhost:3002`) |

## Key Design Decisions

- **Everything local**: `inverter/reader.py` keeps one Modbus session to the inverter hotspot (`192.168.8.1:6607`, `installer` login via `huawei-solar`), polls every 3 s and caches the result; `/dashboard` and `/dashboard.png` only read the cache, so clients can poll as often as they like. Settings and the lifetime total are re-read every 10th round. Battery commands (`write()`) go over the same session between two reading rounds, under a lock. A rejected password stops polling (retries would lock logins for ~10 min), and failures are logged sparingly (first, then every 100th). The lifetime `total_energy_kwh` is the inverter's own counter, about 1,019 kWh above FusionSolar's plant total. Trade-off: if the hotspot link drops, both readings and control stop; the discharge command's own period is the safety net
- **Saved windows are the only instruction**: one controller applies one rule, with no per-window tasks, no "launched" bookkeeping and no state files. After a restart the next check applies the rule again
- **Discharge windows** use a JSON config file on the Docker volume, not a database, written atomically (write tmp + rename). An unreadable file raises instead of being treated as empty, so a save can never wipe the windows
- **TOU schedule is left alone**: the API never writes the operation mode or TOU windows; a forced discharge overrides TOU while it runs, and the inverter goes back to the schedule by itself
- **Mock clock**: in mock mode, time comes from `mock_clock.get_now()`, which the `/mock/time` endpoints move; the controller takes a clock argument so tests set the time directly
