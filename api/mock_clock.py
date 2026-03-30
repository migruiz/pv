"""Virtual clock for mock mode testing.

In production: get_now() returns the real current time.
In mock mode: get_now() returns a controllable virtual time,
settable via API endpoints for testing discharge window scheduling.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Dublin")

_virtual_time: datetime | None = None


def get_now() -> datetime:
    """Return current time — virtual if set, real otherwise."""
    if _virtual_time is not None:
        return _virtual_time
    return datetime.now(TZ)


def set_time(hour: int, minute: int = 0) -> datetime:
    """Set virtual clock to a specific hour:minute today (Dublin time)."""
    global _virtual_time
    now = datetime.now(TZ)
    _virtual_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return _virtual_time


def advance(minutes: int) -> datetime:
    """Advance virtual clock by N minutes. Initialises from real time if not set."""
    global _virtual_time
    if _virtual_time is None:
        _virtual_time = datetime.now(TZ)
    _virtual_time += timedelta(minutes=minutes)
    return _virtual_time


def reset() -> datetime:
    """Reset to real system time."""
    global _virtual_time
    _virtual_time = None
    return datetime.now(TZ)


def is_virtual() -> bool:
    """Return True if the virtual clock is active."""
    return _virtual_time is not None
