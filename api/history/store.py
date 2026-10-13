"""Persistent minute history, fed by the existing inverter poller, for GET /history (the home's screens' charts)
and GET /usage. Kept for good: about 40 MB a year."""

import math
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

FIELDS = ("pv_kw", "home_kw", "battery_soc")
METER_FIELDS = ("grid_import_total_kwh", "grid_export_total_kwh")  # the grid meter's running totals, kWh


def finite(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and abs(result) < 1e100 else None


class HistoryStore:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False, timeout=10)
        self._lock = threading.Lock()
        self._db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;
            CREATE TABLE IF NOT EXISTS samples (
                minute INTEGER PRIMARY KEY, observed_at REAL NOT NULL,
                pv_sum REAL, home_sum REAL, battery_soc REAL,
                sample_count INTEGER NOT NULL, source TEXT NOT NULL,
                grid_import_kwh REAL, grid_export_kwh REAL
            );
        """)
        # The grid meter's totals came in October 2026: older databases get the columns, older minutes none
        columns = {row[1] for row in self._db.execute("PRAGMA table_info(samples)")}
        with self._db:
            for name in ("grid_import_kwh", "grid_export_kwh"):
                if name not in columns:
                    self._db.execute(f"ALTER TABLE samples ADD COLUMN {name} REAL")

    def close(self):
        with self._lock:
            self._db.close()

    def record(self, data):
        """Average every successful poll's power; keep the minute's latest SOC and grid meter totals.

        Duplicate/out-of-order reads do not count twice.
        """
        stamp = datetime.fromisoformat(data["updated_at"]).timestamp()
        values = [finite(data.get(key)) for key in FIELDS]
        if any(v is None for v in values) or not 0 <= values[2] <= 100:
            return
        pv, home, soc = values
        grid_import, grid_export = (finite(data.get(key)) for key in METER_FIELDS)
        minute = int(stamp // 60)
        with self._lock, self._db:
            old = self._db.execute("SELECT observed_at,pv_sum,home_sum,sample_count FROM samples WHERE minute=?", (minute,)).fetchone()
            count = 1
            if old:
                if stamp <= old[0]:
                    return
                pv += old[1]
                home += old[2]
                count += old[3]
            self._db.execute("INSERT OR REPLACE INTO samples (minute,observed_at,pv_sum,home_sum,battery_soc,"
                             "sample_count,source,grid_import_kwh,grid_export_kwh) VALUES (?,?,?,?,?,?,?,?,?)",
                             (minute, stamp, pv, home, soc, count, "inverter", grid_import, grid_export))

    def samples(self, since, step=1, until=None):
        """Every stored minute from the one holding `since` (Unix seconds) on, up to the one before the minute
        holding `until` if given, oldest first: (observed_at, average solar kW, average home kW, latest battery %,
        latest kWh bought and sold totals). The totals are None for minutes recorded before they were.

        With `step` > 1, one row per `step` minutes (counted from the epoch, from the step holding
        `since`) that has any: its minutes' average power, and the latest minute's battery %, totals and time."""
        first = int(since // 60)
        last = int(until // 60) if until is not None else 2**62
        with self._lock:
            if step <= 1:
                return self._db.execute(
                    "SELECT observed_at,pv_sum/sample_count,home_sum/sample_count,battery_soc,grid_import_kwh,grid_export_kwh "
                    "FROM samples WHERE minute >= ? AND minute < ? ORDER BY minute", (first, last)).fetchall()
            # SQLite takes the bare observed_at, battery_soc and totals from the row holding max(minute).
            rows = self._db.execute(
                "SELECT max(minute),observed_at,avg(pv_sum/sample_count),avg(home_sum/sample_count),battery_soc,"
                "grid_import_kwh,grid_export_kwh FROM samples WHERE minute >= ? AND minute < ? GROUP BY minute/? ORDER BY minute/?",
                (first - first % step, last, step, step)).fetchall()
            return [row[1:] for row in rows]

    def status(self):
        with self._lock:
            count, first, last = self._db.execute("SELECT count(*),min(observed_at),max(observed_at) FROM samples").fetchone()
        return {"minutes": count, "first_timestamp": first, "last_timestamp": last}
