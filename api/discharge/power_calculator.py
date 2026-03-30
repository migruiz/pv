"""Discharge power calculation logic.

Pure functions for computing the required discharge power
to reach a target SOC within a given time window.
"""

BATTERY_REAL_CAPACITY_KWH = 4.8  # Usable capacity (rated 5.0, real ~4.8)
MAX_DISCHARGE_POWER_KW = 2.5     # Inverter hard limit


def calc_discharge_power(
    soc: float,
    minutes_remaining: float,
    target_soc: float,
) -> float | None:
    """Calculate discharge power in kW, or None if not worthwhile.

    Returns None if SOC is already at or below target, or if no time remains.
    """
    if soc <= target_soc or minutes_remaining <= 0:
        return None
    remaining_kwh = ((soc - target_soc) / 100.0) * BATTERY_REAL_CAPACITY_KWH
    hours_remaining = minutes_remaining / 60.0
    return min(remaining_kwh / hours_remaining, MAX_DISCHARGE_POWER_KW)


def remaining_energy_kwh(soc: float, target_soc: float) -> float:
    """Energy (kWh) that needs to be discharged to go from soc to target_soc."""
    return max(0.0, ((soc - target_soc) / 100.0) * BATTERY_REAL_CAPACITY_KWH)
