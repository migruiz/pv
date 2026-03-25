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
│   ├── main.py                   # FastAPI app, all route handlers, lifespan
│   ├── session.py                # FusionSolar session manager (cookie persistence, keep-alive)
│   ├── auth.py                   # API key authentication (X-API-Key header)
│   ├── pyproject.toml            # uv project dependencies
│   ├── uv.lock                   # Locked dependencies
│   ├── Dockerfile                # Multi-arch image (amd64 + arm64)
│   ├── docker-compose.yml        # Local dev deployment
│   ├── build-and-push.bat        # Build multi-arch + push to Docker Hub
│   ├── build-and-run.bat         # Build + run locally
│   └── test_connection.py        # Original connectivity test script
│
└── app/                          # Android mobile app (Kotlin/Compose)
    ├── app/src/main/java/ovh/tenjo/pv/
    │   ├── MainActivity.kt       # Navigation, bottom bar, API config
    │   ├── SolarViewModel.kt     # Dashboard + battery control state
    │   ├── api/SolarApi.kt       # Retrofit client, data models
    │   └── ui/
    │       ├── DashboardScreen.kt      # Energy flow diagram, stats, battery card
    │       ├── BatteryControlScreen.kt # Forced charge/discharge controls
    │       └── theme/                  # Dark solar theme (Color, Theme, Type)
    └── gradle/libs.versions.toml # Version catalog
```

## API Endpoints

All endpoints except `/health` and `/docs` require `X-API-Key` header.

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
| POST | `/batteries/{id}/forced-charge` | Force charge/discharge/stop |
| POST | `/batteries/{id}/operation-mode` | Change TOU/self-consumption mode |
| POST | `/batteries/{id}/params` | Update SOC limits, charge power limits |

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

### API (local)
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
- API URL configured in `MainActivity.kt` → `SolarApiClient.baseUrl`
- Production: `https://pv.tenjo.ovh/`
- Local dev: `http://10.0.2.2:8000/` (emulator) or `http://localhost:8000/` (adb reverse)

### Install APK via ADB
```bash
cd app && ./gradlew assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n ovh.tenjo.pv/.MainActivity
```

## Deployment

- **Docker Hub image**: `migruiz/pv-solar-api:latest` (multi-arch: amd64 + arm64)
- **Production host**: Raspberry Pi 4 running Docker via Portainer
- **Public URL**: `https://pv.tenjo.ovh` (Cloudflare tunnel)
- **Session management**: Cookies persisted to `/data/cookies.json` volume — survives container restarts without re-login

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| FUSIONSOLAR_USER | Yes | FusionSolar portal username |
| FUSIONSOLAR_PASS | Yes | FusionSolar portal password |
| HUAWEI_SUBDOMAIN | No | Default: `uni003eu5` |
| API_KEY | Yes | API authentication key for X-API-Key header |

## Key Design Decisions

- **FusionSolarPy library** is synchronous — all calls wrapped in `asyncio.to_thread()` with an `asyncio.Lock` to prevent concurrent session corruption
- **Keep-alive loop** runs every 120 seconds mimicking the web browser to maintain the session
- **Cookie persistence** via symlink (`/app/cookies.json` → `/data/cookies.json`) so the Docker volume stores session state without modifying application code
- **Grid direction**: FusionSolar's "buy.power" label means the grid buys from you (exporting), not that you're buying from the grid
