"""Charge ramp power calculation logic.

Pure functions for computing the target max charge power
along a cosine-interpolated bell curve.
"""

import math

MIN_POWER = 200
MAX_POWER = 2500


def cosine_interpolate(a: float, b: float, t: float) -> float:
    """Smooth cosine interpolation from a to b as t goes from 0 to 1."""
    factor = (1 - math.cos(t * math.pi)) / 2
    return a + (b - a) * factor


def calc_ramp_power(
    progress: float,
    initial_power: int,
    top_power: int,
    final_power: int,
) -> int:
    """Calculate target charge power at a given progress (0.0-1.0).

    First half (0.0-0.5): cosine ease from initial_power to top_power
    Second half (0.5-1.0): cosine ease from top_power to final_power
    Result clamped to [200, 2500] and rounded to nearest integer.
    """
    if progress <= 0.0:
        power = float(initial_power)
    elif progress >= 1.0:
        power = float(final_power)
    elif progress <= 0.5:
        t = progress / 0.5
        power = cosine_interpolate(initial_power, top_power, t)
    else:
        t = (progress - 0.5) / 0.5
        power = cosine_interpolate(top_power, final_power, t)

    return max(MIN_POWER, min(MAX_POWER, round(power)))


def calc_progress(elapsed_minutes: float, total_minutes: int) -> float:
    """Calculate ramp progress (0.0-1.0) from elapsed time."""
    if total_minutes <= 0:
        return 1.0
    return min(1.0, max(0.0, elapsed_minutes / total_minutes))
