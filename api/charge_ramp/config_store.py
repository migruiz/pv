"""JSON file I/O for charge ramp configuration.

Reads/writes a single charge ramp config from a JSON file on the Docker volume
(/data/charge_ramp_config.json) or local dev fallback (./charge_ramp_config.json).
"""

import json
import logging
import os
from pathlib import Path

from .models import ChargeRampConfig, ChargeRampConfigUpdate

logger = logging.getLogger("pv.charge_ramp.config")

DOCKER_PATH = Path("/data/charge_ramp_config.json")
LOCAL_PATH = Path(__file__).parent.parent / "charge_ramp_config.json"

ACTIVE_DOCKER_PATH = Path("/data/charge_ramp_active.json")
ACTIVE_LOCAL_PATH = Path(__file__).parent.parent / "charge_ramp_active.json"

_cached_path: Path | None = None
_cached_active_path: Path | None = None


def _config_path() -> Path:
    """Return the path to the config file, preferring Docker volume."""
    global _cached_path
    if _cached_path is None:
        if DOCKER_PATH.parent.exists() and os.access(DOCKER_PATH.parent, os.W_OK):
            _cached_path = DOCKER_PATH
        else:
            _cached_path = LOCAL_PATH
    return _cached_path


def _active_path() -> Path:
    """Return the path to the active ramp state file."""
    global _cached_active_path
    if _cached_active_path is None:
        if ACTIVE_DOCKER_PATH.parent.exists() and os.access(ACTIVE_DOCKER_PATH.parent, os.W_OK):
            _cached_active_path = ACTIVE_DOCKER_PATH
        else:
            _cached_active_path = ACTIVE_LOCAL_PATH
    return _cached_active_path


def load_config() -> ChargeRampConfig:
    """Load config from JSON. Returns default if file missing."""
    path = _config_path()
    if not path.exists():
        return ChargeRampConfig()
    try:
        data = json.loads(path.read_text())
        return ChargeRampConfig(**data)
    except Exception as exc:
        logger.error("Failed to load charge ramp config: %s", exc)
        return ChargeRampConfig()


def save_config(config: ChargeRampConfig) -> None:
    """Atomically write config to JSON."""
    path = _config_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(config.model_dump(), indent=2))
    os.replace(tmp, path)
    logger.info("Saved charge ramp config to %s", path)


def update_config(update: ChargeRampConfigUpdate) -> ChargeRampConfig:
    """Merge partial update into existing config, save, and return."""
    config = load_config()
    merged = config.model_dump()
    for key, value in update.model_dump(exclude_unset=True).items():
        merged[key] = value
    updated = ChargeRampConfig(**merged)
    save_config(updated)
    return updated


def save_active(start_time_iso: str, config: ChargeRampConfig) -> None:
    """Persist active ramp state for restart recovery."""
    path = _active_path()
    data = {"start_time": start_time_iso, "config": config.model_dump()}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)


def load_active() -> tuple[str, ChargeRampConfig] | None:
    """Load persisted active ramp, or None if not running."""
    path = _active_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return data["start_time"], ChargeRampConfig(**data["config"])
    except Exception as exc:
        logger.error("Failed to load active ramp state: %s", exc)
        return None


def clear_active() -> None:
    """Remove the active ramp file."""
    path = _active_path()
    if path.exists():
        path.unlink()
