"""Simple sunset-based battery runtime; no network or inverter access."""

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

from astral import Observer
from astral.sun import sunrise, sunset

from discharge.power_calculator import remaining_energy_kwh

DUBLIN = ZoneInfo("Europe/Dublin")
DUBLIN_OBSERVER = Observer(latitude=53.3498, longitude=-6.2603)
BASELINE_KW = 0.25


@lru_cache(maxsize=32)
def daylight(day: date) -> tuple[datetime, datetime]:
    """Dublin sunrise and sunset, including the local daylight-saving offset."""
    return (sunrise(DUBLIN_OBSERVER, date=day, tzinfo=DUBLIN),
            sunset(DUBLIN_OBSERVER, date=day, tzinfo=DUBLIN))


@dataclass(frozen=True)
class BatteryEstimate:
    sunset: datetime
    empty_at: datetime | None


def estimate_battery(soc: object, now: datetime) -> BatteryEstimate:
    """Use sunset during daylight, otherwise now (also after midnight).

    This is a baseline scenario to 0% SOC. It deliberately excludes future
    charging, scheduled export, extra household load, reserves and losses.
    Naive input times are treated as Dublin-local, matching the renderer.
    """
    now = now.replace(tzinfo=DUBLIN) if now.tzinfo is None else now.astimezone(DUBLIN)
    rise, setting = daylight(now.date())
    try:
        charge = float(soc)
    except (TypeError, ValueError):
        return BatteryEstimate(setting, None)
    if not math.isfinite(charge) or not 0 <= charge <= 100:
        return BatteryEstimate(setting, None)
    hours = remaining_energy_kwh(charge, 0) / BASELINE_KW
    start = setting if rise <= now < setting and hours > 0 else now
    # Add elapsed hours in UTC so an overnight DST change preserves runtime.
    empty = (start.astimezone(timezone.utc) + timedelta(hours=hours)).astimezone(DUBLIN)
    return BatteryEstimate(setting, empty)


def clock_text(at: datetime) -> tuple[str, str]:
    """Compact 12-hour clock, rounded to the nearest minute."""
    at = (at.astimezone(timezone.utc) + timedelta(seconds=30)).astimezone(DUBLIN)
    return f"{at.hour % 12 or 12}:{at.minute:02}", "a" if at.hour < 12 else "p"
