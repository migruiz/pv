"""Persistent minute history, fed by the existing inverter poller, for GET /history (the home's screens' charts)."""

import math
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

FIELDS = ("pv_kw", "home_kw", "battery_soc")
RETENTION_SECONDS = 30 * 86400


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
        self._last_prune = 0
        self._db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;
            CREATE TABLE IF NOT EXISTS samples (
                minute INTEGER PRIMARY KEY, observed_at REAL NOT NULL,
                pv_sum REAL, home_sum REAL, battery_soc REAL,
                sample_count INTEGER NOT NULL, source TEXT NOT NULL
            );
        """)

    def close(self):
        with self._lock:
            self._db.close()

    def record(self, data):
        """Average every successful poll's power; keep the latest minute SOC.

        Duplicate/out-of-order reads do not count twice.
        """
        stamp = datetime.fromisoformat(data["updated_at"]).timestamp()
        values = [finite(data.get(key)) for key in FIELDS]
        if any(v is None for v in values) or not 0 <= values[2] <= 100:
            return
        pv, home, soc = values
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
            self._db.execute("INSERT OR REPLACE INTO samples VALUES (?,?,?,?,?,?,?)",
                             (minute, stamp, pv, home, soc, count, "inverter"))
            if stamp - self._last_prune >= 3600:
                self._db.execute("DELETE FROM samples WHERE minute < ?", (int((stamp - RETENTION_SECONDS) // 60),))
                self._last_prune = stamp

    def samples(self, since):
        """Every stored minute from the one holding `since` (Unix seconds) on, oldest first:
        (observed_at, average solar kW, average home kW, latest battery %)."""
        with self._lock:
            return self._db.execute(
                "SELECT observed_at,pv_sum/sample_count,home_sum/sample_count,battery_soc "
                "FROM samples WHERE minute >= ? ORDER BY minute", (int(since // 60),)).fetchall()

    def status(self):
        with self._lock:
            count, first, last = self._db.execute("SELECT count(*),min(observed_at),max(observed_at) FROM samples").fetchone()
        return {"minutes": count, "first_timestamp": first, "last_timestamp": last}
