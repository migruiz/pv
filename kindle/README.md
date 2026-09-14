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
