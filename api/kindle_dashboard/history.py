"""Persistent minute history, fed by the existing inverter poller."""

import math
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

FIELDS = ("pv_kw", "home_kw", "battery_soc")
WINDOW_SECONDS = 12 * 3600
RETENTION_SECONDS = 30 * 86400
MAX_GAP_SECONDS = 90  # a longer pause between readings is drawn as a gap


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
        self.revision = 0
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
            self.revision += 1

    def chart(self, end, current):
        """Return values and true X positions in [now-12h, now], with gaps.

        Break gaps longer than 90 seconds. The current reading anchors the
        right edge without requiring another inverter read.
        """
        end_ts = end.timestamp()
        start = end_ts - WINDOW_SECONDS
        with self._lock:
            records = self._db.execute(
                "SELECT observed_at,pv_sum/sample_count,home_sum/sample_count,battery_soc "
                "FROM samples WHERE minute BETWEEN ? AND ? ORDER BY minute",
                (int(start // 60), int(end_ts // 60))).fetchall()
        records = [row for row in records if start <= row[0] <= end_ts]
        latest = [finite(current.get(key)) for key in FIELDS]
        if all(value is not None for value in latest):
            if records and records[-1][0] == end_ts:
                records.pop()
            records.append((end_ts, *latest))
        history = {key: [] for key in FIELDS}
        positions = []
        previous = None
        for row in records:
            if previous:
                if row[0] - previous[0] > MAX_GAP_SECONDS:
                    positions.append(((previous[0] + row[0]) / 2 - start) / WINDOW_SECONDS)
                    for samples in history.values():
                        samples.append(None)
            positions.append((row[0] - start) / WINDOW_SECONDS)
            for key, reading in zip(FIELDS, row[1:4]):
                history[key].append(reading)
            previous = row
        return history, positions

    def status(self):
        with self._lock:
            count, first, last = self._db.execute("SELECT count(*),min(observed_at),max(observed_at) FROM samples").fetchone()
        return {"minutes": count, "first_timestamp": first, "last_timestamp": last}
