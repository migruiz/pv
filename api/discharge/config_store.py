"""JSON file I/O for discharge window configuration.

Reads/writes discharge windows from a JSON file on the Docker volume
(/data/discharge_windows.json) or local dev fallback (./discharge_windows.json).
"""

import json
import logging
import os
import uuid
from pathlib import Path

from .models import DischargeWindow, DischargeWindowCreate, DischargeWindowUpdate

logger = logging.getLogger("pv.discharge.config")

DOCKER_PATH = Path("/data/discharge_windows.json")
LOCAL_PATH = Path(__file__).parent.parent / "discharge_windows.json"

DEFAULT_WINDOW = DischargeWindow(
    id=uuid.uuid4().hex[:8],
    name="Night Export",
    start_time="22:00",
    duration_minutes=240,
    target_soc=0,
    notify=True,
    enabled=True,
)


def _config_path() -> Path:
    """Return the path to the config file, preferring Docker volume."""
    if DOCKER_PATH.parent.exists() and os.access(DOCKER_PATH.parent, os.W_OK):
        return DOCKER_PATH
    return LOCAL_PATH


def _parse_time_minutes(time_str: str) -> int:
    """Convert 'HH:MM' to minutes since midnight."""
    h, m = time_str.split(":")
    return int(h) * 60 + int(m)


def _window_minute_set(start_time: str, duration_minutes: int) -> set[int]:
    """Return the set of minutes-of-day (0-1439) covered by a window."""
    start = _parse_time_minutes(start_time)
    return {(start + i) % 1440 for i in range(duration_minutes)}


def load_windows() -> list[DischargeWindow]:
    """Load windows from JSON. Seeds default if file missing."""
    path = _config_path()
    if not path.exists():
        logger.info("Config file not found, seeding default window")
        windows = [DEFAULT_WINDOW]
        save_windows(windows)
        return windows

    try:
        data = json.loads(path.read_text())
        return [DischargeWindow(**w) for w in data.get("windows", [])]
    except Exception as exc:
        logger.error("Failed to load config: %s", exc)
        return []


def save_windows(windows: list[DischargeWindow]) -> None:
    """Atomically write windows to JSON (write tmp then rename)."""
    path = _config_path()
    data = {"windows": [w.model_dump() for w in windows]}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)
    logger.info("Saved %d windows to %s", len(windows), path)


def get_window(window_id: str) -> DischargeWindow | None:
    """Find a window by ID."""
    for w in load_windows():
        if w.id == window_id:
            return w
    return None


def add_window(create: DischargeWindowCreate) -> DischargeWindow:
    """Create a new window, append to config, and return it."""
    windows = load_windows()
    window = DischargeWindow(id=uuid.uuid4().hex[:8], **create.model_dump())
    windows.append(window)
    save_windows(windows)
    return window


def update_window(window_id: str, update: DischargeWindowUpdate) -> DischargeWindow | None:
    """Update a window by ID with partial data. Returns updated window or None."""
    windows = load_windows()
    for i, w in enumerate(windows):
        if w.id == window_id:
            merged = w.model_dump()
            for key, value in update.model_dump(exclude_unset=True).items():
                merged[key] = value
            windows[i] = DischargeWindow(**merged)
            save_windows(windows)
            return windows[i]
    return None


def delete_window(window_id: str) -> bool:
    """Delete a window by ID. Returns True if found and deleted."""
    windows = load_windows()
    filtered = [w for w in windows if w.id != window_id]
    if len(filtered) == len(windows):
        return False
    save_windows(filtered)
    return True


def check_overlap(
    candidate: DischargeWindow | DischargeWindowCreate,
    exclude_id: str | None = None,
) -> DischargeWindow | None:
    """Check if a candidate window overlaps with any existing enabled window.

    Returns the first conflicting window, or None if no overlap.
    Uses minute-of-day modulo 1440 to handle midnight crossing correctly.
    """
    candidate_minutes = _window_minute_set(candidate.start_time, candidate.duration_minutes)

    for w in load_windows():
        if not w.enabled:
            continue
        if exclude_id and w.id == exclude_id:
            continue
        existing_minutes = _window_minute_set(w.start_time, w.duration_minutes)
        if candidate_minutes & existing_minutes:
            return w

    return None
