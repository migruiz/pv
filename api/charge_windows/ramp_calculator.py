"""Charge window power calculation logic.

Pure functions for computing the target max charge power
along a cosine-interpolated bell curve with asymmetric timing.
"""

import math
from datetime import datetime

MIN_POWER = 200
MAX_POWER = 2500


def cosine_interpolate(a: float, b: float, t: float) -> float:
    """Smooth cosine interpolation from a to b as t goes from 0 to 1."""
    factor = (1 - math.cos(t * math.pi)) / 2
    return a + (b - a) * factor


def calc_charge_power(
    now: datetime,
    start_dt: datetime,
    peak_dt: datetime,
    end_dt: datetime,
    start_power: int,
    peak_power: int,
    end_power: int,
) -> int:
    """Calculate target charge power at a given time.

    Supports asymmetric curves where peak_dt doesn't have to be
    at the midpoint between start_dt and end_dt.

    First segment (start → peak): cosine ease from start_power to peak_power
    Second segment (peak → end):  cosine ease from peak_power to end_power
    Result clamped to [200, 2500] and rounded to nearest integer.
    """
    if now <= start_dt:
        power = float(start_power)
    elif now >= end_dt:
        power = float(end_power)
    elif now <= peak_dt:
        segment_total = (peak_dt - start_dt).total_seconds()
        if segment_total <= 0:
            power = float(peak_power)
        else:
            t = (now - start_dt).total_seconds() / segment_total
            power = cosine_interpolate(start_power, peak_power, t)
    else:
        segment_total = (end_dt - peak_dt).total_seconds()
        if segment_total <= 0:
            power = float(end_power)
        else:
            t = (now - peak_dt).total_seconds() / segment_total
            power = cosine_interpolate(peak_power, end_power, t)

    return max(MIN_POWER, min(MAX_POWER, round(power)))


def calc_progress(now: datetime, start_dt: datetime, end_dt: datetime) -> float:
    """Calculate overall progress (0.0-1.0) from elapsed time."""
    total = (end_dt - start_dt).total_seconds()
    if total <= 0:
        return 1.0
    elapsed = (now - start_dt).total_seconds()
    return min(1.0, max(0.0, elapsed / total))
