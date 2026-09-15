"""Local layout preview with mock readings/history; no inverter or API connection.

Run from the repo root: api/.venv/Scripts/python.exe kindle/preview.py
Open http://127.0.0.1:8765 (460x345 display, 800x600 source PNG).
"""

import argparse
import math
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from kindle_dashboard.renderer import HISTORY_HOURS, render_png


SAMPLE_MINUTES = 5
# All three mock traces share the exact same endpoints and sample times.
HISTORY_OFFSETS_MINUTES = tuple(range(-HISTORY_HOURS * 60, 1, SAMPLE_MINUTES))


def mock_history():
    """145 shared five-minute samples, from now minus 12 hours through now."""
    positions = [(offset + HISTORY_HOURS * 60) / HISTORY_HOURS for offset in HISTORY_OFFSETS_MINUTES]
    solar = [
        max(0, min(5.5, 3.3 + 1.3 * math.sin(i / 15)
                   - 2.2 * math.exp(-((i - 23) / 3.8) ** 2)
                   - 1.4 * math.exp(-((i - 43) / 2.8) ** 2)
                   + 0.12 * math.sin(i * 1.7)))
        for i in positions
    ]
    # Deliberately high production plateaus to verify clipping at the 5 kW guide.
    # Each plateau lasts an hour; the latest reading remains the normal sample.
    for index, offset in enumerate(HISTORY_OFFSETS_MINUTES):
        elapsed = offset + HISTORY_HOURS * 60
        for start, end, kw in ((180, 240, 7.0), (300, 360, 6.5),
                               (420, 480, 5.5), (540, 600, 6.0)):
            if start <= elapsed <= end:
                solar[index] = kw
                break
    home = [
        0.32 + 0.06 * math.sin(i * 1.3)
        + (2.4 if 9 <= i <= 15 else 0)
        + (1.3 if 29 <= i <= 43 else 0)
        + (2.0 if 35 <= i <= 39 else 0)
        + (0.6 if 49 <= i <= 53 else 0)
        for i in positions
    ]
    # Elapsed minutes within the same 12-hour window: discharge and recharge.
    charge_points = [(0, 84), (120, 28), (180, 12), (270, 100),
                     (330, 100), (510, 46), (600, 91), (660, 88), (720, 73)]
    battery = []
    for (start, first), (end, last) in zip(charge_points, charge_points[1:]):
        for i in range(start, end, SAMPLE_MINUTES):
            battery.append(first + (last - first) * (i - start) / (end - start))
    battery.append(charge_points[-1][1])
    return {"pv_kw": solar, "home_kw": home, "battery_soc": battery}


HISTORY = mock_history()
READINGS = {key: samples[-1] for key, samples in HISTORY.items()}


def battery_preview(state):
    """Keep the recent mock history consistent with the selected badge."""
    readings = {**READINGS, "battery_charging": state == "charging",
                "battery_charge_discharge_kw": 0 if state == "idle" else 0.9}
    history = {**HISTORY, "battery_soc": list(HISTORY["battery_soc"])}
    if state in ("charging", "idle"):
        soc = readings["battery_soc"]
        history["battery_soc"][-13:] = [soc - 18 + i * 1.5 for i in range(13)] if state == "charging" else [soc] * 13
    return readings, history


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        request = urlsplit(self.path)
        path = request.path
        if path == "/":
            data = Path(__file__).with_suffix(".html").read_bytes()
            content_type, status = "text/html; charset=utf-8", 200
        elif path == "/dashboard.png":
            state = parse_qs(request.query).get("battery", ["discharging"])[0]
            if state not in ("charging", "discharging", "idle"):
                state = "discharging"
            readings, history = battery_preview(state)
            data = render_png(readings, datetime.now(ZoneInfo("Europe/Dublin")), history=history)
            content_type, status = "image/png", 200
        elif path == "/favicon.ico":
            data, content_type, status = b"", "image/x-icon", 204
        else:
            data, content_type, status = b"Not found", "text/plain", 404
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Mock chart preview: http://127.0.0.1:{args.port}", flush=True)
    server.serve_forever()
