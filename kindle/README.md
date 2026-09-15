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
Charging adds a borderless lightning bolt above the battery terminal; discharging
adds a downward arrow below it. Idle shows neither. Compare the mock states
at `http://127.0.0.1:8765/?battery=charging`, `?battery=discharging` (default),
or `?battery=idle`.
The placeholder empty time has a small upright empty-battery icon before it.
A remaining-energy value (compact `3.5k` format) is left-aligned above the percent
symbol, using SOC times the configured 4.8 kWh usable capacity; the percentage
position stays fixed.
The renderer's optional `history` argument enables this layout; the production
endpoint retains its existing layout until real history is implemented.

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
