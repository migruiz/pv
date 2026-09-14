"""Register lists and the pure mapping from raw inverter readings to the /dashboard payload."""

# Read every round (every few seconds): live power flows and today's energy counters.
FAST_REGISTERS = [
    "input_power",                             # W, PV input
    "active_power",                            # W, inverter AC output
    "power_meter_active_power",                # W, positive = exporting to the grid
    "storage_charge_discharge_power",          # W, positive = charging
    "storage_state_of_capacity",               # %
    "daily_yield_energy",                      # kWh
    "storage_current_day_discharge_capacity",  # kWh
]

# Read every few rounds: settings changed through the FusionSolar cloud, and the lifetime total.
SLOW_REGISTERS = [
    "storage_working_mode_settings",      # same codes as FusionSolar signal 230320241 (2, 4, 5)
    "storage_charge_from_grid_function",  # FusionSolar signal 230320279
    "storage_maximum_charging_power",     # W, FusionSolar signal 10011
    "accumulated_yield_energy",           # kWh
]

# Used until the first settings read succeeds (the same defaults the cloud reader fell back to).
SLOW_DEFAULTS = {
    "storage_working_mode_settings": 5,
    "storage_charge_from_grid_function": 1,
    "storage_maximum_charging_power": 2500,
    "accumulated_yield_energy": 0.0,
}


def _number(value) -> float:
    """Enum registers come back as enum members (raw code in .value); bools convert directly."""
    return float(getattr(value, "value", value))


def _kw(watts: float) -> float:
    return round(watts / 1000, 3)


def to_dashboard(values: dict) -> dict:
    """Map raw register values to the /dashboard fields the Android app and Kindle expect."""
    v = {**SLOW_DEFAULTS, **values}
    battery_w = _number(v["storage_charge_discharge_power"])
    meter_w = _number(v["power_meter_active_power"])
    return {
        "pv_kw": _kw(_number(v["input_power"])),
        "battery_soc": _number(v["storage_state_of_capacity"]),
        "battery_charge_discharge_kw": _kw(abs(battery_w)),
        "battery_charging": battery_w > 0,
        "grid_kw": _kw(abs(meter_w)),
        "grid_importing": meter_w < 0,
        # The meter sits at the grid connection: home = inverter output - export (+ import)
        "home_kw": _kw(max(0.0, _number(v["active_power"]) - meter_w)),
        "energy_today_kwh": round(_number(v["daily_yield_energy"]), 2),
        "discharged_today_kwh": round(_number(v["storage_current_day_discharge_capacity"]), 2),
        "total_energy_kwh": round(_number(v["accumulated_yield_energy"]), 2),
        "operation_mode": int(_number(v["storage_working_mode_settings"])),
        "charge_from_ac": int(_number(v["storage_charge_from_grid_function"])),
        "max_charge_power": int(_number(v["storage_maximum_charging_power"])),
    }
