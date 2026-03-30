# PV Solar Manager

Home solar PV monitoring and control system for a Huawei FusionSolar installation in Dublin, Ireland. Consists of a Python API backend and an Android mobile app.

## Architecture

```
┌─────────────┐     HTTPS      ┌──────────────┐     FusionSolar    ┌─────────────────┐
│  Android App │ ──────────────→│  FastAPI      │ ──────────────────→│  Huawei Cloud   │
│  (Compose)   │  pv.tenjo.ovh │  (Raspberry Pi)│  uni003eu5        │  FusionSolar API │
└─────────────┘                └──────────────┘                    └─────────────────┘
                               Cloudflare Tunnel
```

- **API** (`api/`): FastAPI middleware that maintains a persistent FusionSolar session and exposes REST endpoints
- **App** (`app/`): Android Kotlin/Jetpack Compose mobile app with live energy flow dashboard and battery controls
- **Mock** (`mock/`): Node.js/TypeScript solar system simulator with React UI for development and testing
- **Deployment**: Docker container on Raspberry Pi 4 (arm64), exposed via Cloudflare tunnel at `https://pv.tenjo.ovh`

## Plant Details

- **Owner**: Miguel Ruiz (account: soniablanco)
- **Location**: Dublin D24 XA48, Ireland
- **Capacity**: 7.650 kWp
- **Grid connection**: 2026-02-04
- **FusionSolar subdomain**: `uni003eu5`
- **Plant ID**: `NE=239198726`
- **Devices**:
  - Inverter: `NE=239198740` (5 kW rated, 2 MPPT strings)
  - Battery: `NE=239198746` (5 kWh, LUNA2000)
  - Power Sensor: `NE=239198748`

## Project Structure

```
pv/
├── api/                          # Python FastAPI backend
│   ├── main.py                   # FastAPI app, lifespan, mock clock endpoints
│   ├── session.py                # FusionSolar session manager (cookie persistence, keep-alive)
│   ├── mock_session.py           # Drop-in session replacement for mock mode
│   ├── mock_clock.py             # Virtual clock for testing (set/advance/reset time)
│   ├── auth.py                   # API key authentication (X-API-Key header)
│   ├── config.py                 # Shared constants (BATTERY_DN, MOCK_MODE, etc.)
│   ├── notifications.py          # Firebase Cloud Messaging push notifications
│   ├── dependencies.py           # FastAPI dependency injection
│   ├── discharge/                # Discharge windows package
│   │   ├── models.py             # Pydantic models (window config, status, API responses)
│   │   ├── config_store.py       # JSON file I/O (load/save/CRUD, overlap detection)
│   │   ├── power_calculator.py   # Discharge power math (pure functions)
│   │   ├── command_builder.py    # FusionSolar signal payload construction
│   │   ├── correction_loop.py    # Background loop that adjusts power every 5 min
│   │   ├── scheduler.py          # Multi-window scheduler (auto-start, mid-window resume)
│   │   ├── router_windows.py     # CRUD endpoints for /discharge-windows
│   │   └── router_control.py     # Start/stop/status endpoints + backward compat
│   ├── routers/                  # Other API routers
│   │   ├── dashboard.py          # Dashboard endpoint
│   │   └── health.py             # Health check
│   ├── tests/                    # Pytest test suite
│   │   ├── conftest.py           # Shared fixtures (FakeSession, app_state, clock, sleep patching)
│   │   ├── helpers.py            # FakeSession and FakeAppState classes
│   │   ├── test_power_calculator.py    # Pure function tests
│   │   ├── test_command_builder.py     # Signal payload tests
│   │   ├── test_config_store.py        # CRUD, overlap detection
│   │   ├── test_correction_loop.py     # Full loop lifecycle
│   │   ├── test_scheduler.py           # Window scheduling, resume, start/stop
│   │   └── test_api_endpoints.py       # HTTP-level CRUD and control
│   ├── Dockerfile                # Multi-arch image (amd64 + arm64)
│   ├── docker-compose.yml        # Local dev deployment
│   ├── pyproject.toml            # uv project dependencies
│   └── uv.lock                   # Locked dependencies
│
├── mock/                         # Solar system simulator
│   ├── server/
│   │   ├── index.ts              # Express server (port 3002)
│   │   ├── routes.ts             # Mock API + simulator UI endpoints
│   │   └── state.ts              # In-memory simulator (SOC, energy balance, command log)
│   └── src/                      # React UI (Vite, port 5173)
│
└── app/                          # Android mobile app (Kotlin/Compose)
    ├── app/src/main/java/ovh/tenjo/pv/
    │   ├── MainActivity.kt       # Navigation, API config
    │   ├── SolarViewModel.kt     # Dashboard + discharge window state
    │   ├── api/SolarApi.kt       # Retrofit client, data models
    │   ├── AutoDischargeService.kt     # Foreground notification service
    │   ├── PvFirebaseMessagingService.kt # FCM message handler
    │   ├── NotificationDismissReceiver.kt # Re-post notification on swipe
    │   ├── StopDischargeBroadcastReceiver.kt # Stop from notification action
    │   └── ui/
    │       ├── DashboardScreen.kt              # Energy flow diagram + window list
    │       ├── DischargeWindowDetailScreen.kt  # Window detail/edit/control
    │       ├── CreateWindowDialog.kt           # New window creation dialog
    │       ├── TimePickers.kt                  # Shared time/duration picker dialogs
    │       ├── TimeUtils.kt                    # Shared time parsing/formatting
    │       └── theme/                          # Dark solar theme (Color, Theme, Type)
    └── gradle/libs.versions.toml # Version catalog
```

## API Endpoints

All endpoints except `/health` and `/docs` require `X-API-Key` header.

### Dashboard & Devices

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (no auth) |
| GET | `/docs` | Swagger UI |
| GET | `/dashboard` | Combined: PV, battery, grid, home power + flow directions |
| GET | `/status` | PV power, today's energy, total yield |
| GET | `/plants` | List stations |
| GET | `/plants/{id}` | Real-time plant KPIs |
| GET | `/plants/{id}/stats` | Daily energy timeseries |
| GET | `/plants/{id}/flow` | Raw energy flow data |
| GET | `/plants/{id}/batteries` | List battery IDs |
| GET | `/batteries/{id}` | Battery SOC, charge/discharge, today's totals |
| GET | `/batteries/{id}/config` | All configurable battery parameters |
| GET | `/devices` | List all devices |
| GET | `/devices/{dn}/realtime` | Real-time device signals |

### Battery Control

| Method | Path | Description |
|--------|------|-------------|
| POST | `/batteries/{id}/forced-charge` | Force charge/discharge/stop |
| POST | `/batteries/{id}/operation-mode` | Change TOU/self-consumption mode |
| POST | `/batteries/{id}/params` | Update SOC limits, charge power limits |

### Discharge Windows

| Method | Path | Description |
|--------|------|-------------|
| GET | `/discharge-windows` | List all configured windows |
| GET | `/discharge-windows/{id}` | Get single window |
| POST | `/discharge-windows` | Create window (validates overlap) |
| PUT | `/discharge-windows/{id}` | Update window (partial, validates overlap) |
| DELETE | `/discharge-windows/{id}` | Delete window (stops if running) |
| GET | `/discharge-windows/status` | Runtime status for all windows |
| GET | `/discharge-windows/{id}/status` | Status for single window |
| POST | `/discharge-windows/{id}/start` | Manually start a window now |
| POST | `/discharge-windows/{id}/stop` | Stop a running window |

### Backward-Compatible (legacy auto-discharge)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/batteries/{id}/auto-discharge/status` | First active window status |
| POST | `/batteries/{id}/auto-discharge/stop` | Stop all running windows |

### Mock-Only Endpoints (when MOCK_MODE=true)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/mock/time` | Get current virtual time |
| POST | `/mock/time` | Set virtual time `{"hour": 22, "minute": 0}` |
| POST | `/mock/time/advance` | Advance clock `{"minutes": 30}` |
| POST | `/mock/time/reset` | Return to real system time |

## Discharge Windows

Configurable battery discharge windows stored in `/data/discharge_windows.json` (Docker volume) or `./discharge_windows.json` (local dev). Each window defines:

- **start_time**: "HH:MM" format
- **duration_minutes**: 1-1440
- **target_soc**: 0-100% (SOC to reach by end of window)
- **notify**: send FCM push notifications
- **enabled**: toggle without deleting

The scheduler auto-starts windows at their configured time and uses a self-correcting loop (every 5 min) to adjust discharge power. Windows cannot overlap (enforced on create/update). On API restart, active windows are automatically resumed (mid-window resume).

A default "Night Export" window (22:00-02:00, target 0%) is seeded on first startup.

## FusionSolar Signal IDs

These were reverse-engineered from the FusionSolar web portal's `set-config-signals` endpoint:

| Signal ID | Name | Values |
|-----------|------|--------|
| 230320245 | Charge/Discharge mode | 0=Stop, 1=Charge, 2=Discharge |
| 230320259 | Forced charge/discharge power (kW) | 0.000~2.500 |
| 230320257 | Setting mode | 0=Duration, 1=Energy |
| 230320281 | Period (min) | 0~1440 |
| 230320241 | Operation Mode | 2=Max self-consumption, 4=Fully fed to grid, 5=TOU |
| 230320264 | Priority of excess PV energy | 0=Fed-to-grid, 1=Charge preference |
| 230320255 | Allowed AC charge power (kW) | 0.000~5.000 |
| 10011 | Max charge power (W) | 200~2500 |
| 10012 | Max discharge power (W) | 200~2500 |
| 230320277 | End-of-charge SOC (%) | 90.0~100.0 |
| 230320278 | End-of-discharge SOC (%) | 0.0~20.0 |
| 230320279 | Charge from AC | 0=Disabled, 1=Enable |
| 230320280 | AC charge cutoff SOC (%) | 20.0~100.0 |

## Development

### Mock System + API (full local dev)

Start the mock simulator and API together for local development:

```bash
# Terminal 1: Start mock solar simulator (Express API on :3002, React UI on :5173)
cd mock
npm run dev

# Terminal 2: Start API in mock mode, connected to mock simulator
cd api
MOCK_MODE=1 uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

- Mock simulator UI: `http://localhost:5173` (change PV, battery SOC, home consumption)
- Mock API: `http://localhost:3002/api/state`
- API Swagger docs: `http://localhost:8000/docs`

### Virtual Clock (mock mode only)

Control simulated time to test discharge window scheduling:

```bash
# Set time to 9:59 PM
curl -X POST -H "Content-Type: application/json" -d '{"hour":21,"minute":59}' http://localhost:8000/mock/time

# Advance 2 minutes (triggers 10 PM window)
curl -X POST -H "Content-Type: application/json" -d '{"minutes":2}' http://localhost:8000/mock/time/advance

# Reset to real time
curl -X POST http://localhost:8000/mock/time/reset
```

### Running Tests

```bash
cd api
uv run pytest tests/ -v          # Run all tests
uv run pytest tests/ -v -x       # Stop on first failure
uv run pytest tests/test_correction_loop.py -v  # Run specific file
```

Tests run in ~1 second with no external dependencies (no Node.js mock, no Firebase, no network). The test suite uses:

- **FakeSession**: In-process mock that returns configurable SOC values and records all signals sent to the inverter. No HTTP calls.
- **Mock clock** (`mock_clock.set_time/advance/reset`): Controls virtual time for discharge window scheduling.
- **Patched `asyncio.sleep`**: Advances the virtual clock instantly instead of waiting — a 4-hour discharge window completes in milliseconds.
- **Patched notifications**: All FCM notification functions are mocked. Tests verify correct calls (started/update/stopped) without touching Firebase.
- **Isolated config store**: Each test gets a `tmp_path`-based config file via the `config_path` fixture, preventing interference with dev `discharge_windows.json`.

### API (local, production mode)

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
- **Session management**: Cookies persisted to `/data/cookies.json` volume — survives container restarts without re-login
- **Discharge windows config**: Persisted to `/data/discharge_windows.json` volume

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| FUSIONSOLAR_USER | Yes | FusionSolar portal username |
| FUSIONSOLAR_PASS | Yes | FusionSolar portal password |
| HUAWEI_SUBDOMAIN | No | Default: `uni003eu5` |
| API_KEY | Yes | API authentication key for X-API-Key header |
| MOCK_MODE | No | Set to `1`/`true`/`yes` to use mock simulator instead of FusionSolar |
| MOCK_URL | No | Mock simulator URL (default: `http://localhost:3002`) |

## Key Design Decisions

- **FusionSolarPy library** is synchronous — all calls wrapped in `asyncio.to_thread()` with an `asyncio.Lock` to prevent concurrent session corruption
- **Keep-alive loop** runs every 120 seconds mimicking the web browser to maintain the session
- **Cookie persistence** via symlink (`/app/cookies.json` → `/data/cookies.json`) so the Docker volume stores session state without modifying application code
- **Grid direction**: FusionSolar's "buy.power" label means the grid buys from you (exporting), not that you're buying from the grid
- **Discharge windows** use a JSON config file on the Docker volume, not a database. The scheduler reads from file, and CRUD endpoints write atomically (write tmp + rename). Overlap between windows is prevented on create/update
- **Self-correcting discharge loop** runs every 5 min in production (30s in mock mode), reads current SOC, and recalculates the exact power needed to hit the target SOC by the window's end time. Constants: `BATTERY_REAL_CAPACITY_KWH` (4.8), `MAX_DISCHARGE_POWER_KW` (2.5)
- **Mid-window resume**: on API restart, the scheduler detects windows that should be active and resumes them for the remaining time
- **Mock clock**: in mock mode, all time-dependent scheduling uses `mock_clock.get_now()` instead of `datetime.now()`, allowing time manipulation via API for testing
- **Component-based architecture**: code is organized into small, single-responsibility files. The `discharge/` package separates models, config I/O, power math, signal commands, correction loop, scheduler, and routers into individual modules
