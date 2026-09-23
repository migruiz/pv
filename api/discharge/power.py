"""Discharge power needed to reach a target battery % by the end of a window (pure functions)."""

BATTERY_REAL_CAPACITY_KWH = 4.8  # Usable capacity (rated 5.0, real ~4.8)
MAX_DISCHARGE_POWER_KW = 2.5     # Inverter hard limit


def calc_discharge_power(soc: float, minutes_remaining: float, target_soc: float) -> float | None:
    """Discharge power in kW, or None when the battery is already at or below the target or time is up."""
    if soc <= target_soc or minutes_remaining <= 0:
        return None
    return min(remaining_energy_kwh(soc, target_soc) / (minutes_remaining / 60.0), MAX_DISCHARGE_POWER_KW)


def remaining_energy_kwh(soc: float, target_soc: float) -> float:
    """Energy (kWh) to discharge to go from soc down to target_soc."""
    return max(0.0, ((soc - target_soc) / 100.0) * BATTERY_REAL_CAPACITY_KWH)
