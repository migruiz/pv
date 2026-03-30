"""JSON file I/O for charge window configuration.

Reads/writes charge windows from a JSON file on the Docker volume
(/data/charge_windows.json) or local dev fallback (./charge_windows.json).
"""

import json
import logging
import os
import uuid
from pathlib import Path

from .models import ChargeWindow, ChargeWindowCreate, ChargeWindowUpdate

logger = logging.getLogger("pv.charge_windows.config")

DOCKER_PATH = Path("/data/charge_windows.json")
LOCAL_PATH = Path(__file__).parent.parent / "charge_windows.json"

ACTIVE_DOCKER_DIR = Path("/data")
ACTIVE_LOCAL_DIR = Path(__file__).parent.parent

_cached_path: Path | None = None


def _config_path() -> Path:
    """Return the path to the config file, preferring Docker volume. Cached after first call."""
    global _cached_path
    if _cached_path is None:
        if DOCKER_PATH.parent.exists() and os.access(DOCKER_PATH.parent, os.W_OK):
            _cached_path = DOCKER_PATH
        else:
            _cached_path = LOCAL_PATH
    return _cached_path


def _active_dir() -> Path:
    """Return the directory for active state files."""
    if ACTIVE_DOCKER_DIR.exists() and os.access(ACTIVE_DOCKER_DIR, os.W_OK):
        return ACTIVE_DOCKER_DIR
    return ACTIVE_LOCAL_DIR


def _active_path(window_id: str) -> Path:
    """Return the path to the active state file for a specific window."""
    return _active_dir() / f"charge_window_active_{window_id}.json"


def _parse_time_minutes(time_str: str) -> int:
    """Convert 'HH:MM' to minutes since midnight."""
    h, m = time_str.split(":")
    return int(h) * 60 + int(m)


def _window_minute_set(start_time: str, end_time: str) -> set[int]:
    """Return the set of minutes-of-day (0-1439) covered by a charge window."""
    start = _parse_time_minutes(start_time)
    end = _parse_time_minutes(end_time)
    duration = end - start
    if duration <= 0:
        duration += 1440
    return {(start + i) % 1440 for i in range(duration)}


def load_windows() -> list[ChargeWindow]:
    """Load windows from JSON. Returns empty list if file missing."""
    path = _config_path()
    if not path.exists():
        return []

    try:
        data = json.loads(path.read_text())
        return [ChargeWindow(**w) for w in data.get("windows", [])]
    except Exception as exc:
        logger.error("Failed to load config: %s", exc)
        return []


def save_windows(windows: list[ChargeWindow]) -> None:
    """Atomically write windows to JSON (write tmp then rename)."""
    path = _config_path()
    data = {"windows": [w.model_dump() for w in windows]}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)
    logger.info("Saved %d charge windows to %s", len(windows), path)


def get_window(window_id: str) -> ChargeWindow | None:
    """Find a window by ID."""
    for w in load_windows():
        if w.id == window_id:
            return w
    return None


def add_window(create: ChargeWindowCreate) -> ChargeWindow:
    """Create a new window, append to config, and return it."""
    windows = load_windows()
    window = ChargeWindow(id=uuid.uuid4().hex[:8], **create.model_dump())
    windows.append(window)
    save_windows(windows)
    return window


def update_window(window_id: str, update: ChargeWindowUpdate) -> ChargeWindow | None:
    """Update a window by ID with partial data. Returns updated window or None."""
    windows = load_windows()
    for i, w in enumerate(windows):
        if w.id == window_id:
            merged = w.model_dump()
            for key, value in update.model_dump(exclude_unset=True).items():
                merged[key] = value
            windows[i] = ChargeWindow(**merged)
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
    candidate: ChargeWindow | ChargeWindowCreate,
    exclude_id: str | None = None,
) -> object | None:
    """Check if a candidate window overlaps with any existing enabled window.

    Checks against both charge windows and discharge windows.
    Returns the first conflicting window, or None if no overlap.
    """
    candidate_minutes = _window_minute_set(candidate.start_time, candidate.end_time)

    # Check against other charge windows
    for w in load_windows():
        if not w.enabled:
            continue
        if exclude_id and w.id == exclude_id:
            continue
        existing_minutes = _window_minute_set(w.start_time, w.end_time)
        if candidate_minutes & existing_minutes:
            return w

    # Check against discharge windows (cross-type)
    from discharge import config_store as discharge_store
    from discharge.config_store import _window_minute_set as discharge_minute_set

    for w in discharge_store.load_windows():
        if not w.enabled:
            continue
        existing_minutes = discharge_minute_set(w.start_time, w.duration_minutes)
        if candidate_minutes & existing_minutes:
            return w

    return None


# ------------------------------------------------------------------
# Active state persistence (restart recovery)
# ------------------------------------------------------------------


def save_active(window_id: str, start_time_iso: str, window: ChargeWindow) -> None:
    """Persist active charge window state for restart recovery."""
    path = _active_path(window_id)
    data = {"start_time": start_time_iso, "window": window.model_dump()}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)


def load_active(window_id: str) -> tuple[str, ChargeWindow] | None:
    """Load persisted active state for a window, or None if not running."""
    path = _active_path(window_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return data["start_time"], ChargeWindow(**data["window"])
    except Exception as exc:
        logger.error("Failed to load active charge window state: %s", exc)
        return None


def load_all_active() -> list[tuple[str, str, ChargeWindow]]:
    """Load all persisted active windows. Returns list of (window_id, start_time_iso, window)."""
    results = []
    for w in load_windows():
        active = load_active(w.id)
        if active is not None:
            start_time_iso, window = active
            results.append((w.id, start_time_iso, window))
    return results


def clear_active(window_id: str) -> None:
    """Remove the active state file for a window."""
    path = _active_path(window_id)
    if path.exists():
        path.unlink()
