"""FusionSolar signal payload construction.

Builds the signal command lists sent to the inverter
for forced charge/discharge control.
"""

# FusionSolar signal IDs (reverse-engineered from web portal)
SIGNALS = {
    "charge_discharge_mode": "230320245",   # 0=Stop, 1=Charge, 2=Discharge
    "forced_power_kw": "230320259",         # 0.000~2.500 kW
    "setting_mode": "230320257",            # 0=Duration, 1=Energy
    "forced_period_min": "230320281",       # 0~1440 min
}


def build_discharge_command(power_kw: float, duration_min: int) -> list[dict]:
    """Build the FusionSolar signal payload for forced discharge."""
    return [
        {"id": SIGNALS["charge_discharge_mode"], "value": "2"},
        {"id": SIGNALS["setting_mode"], "value": "0"},
        {"id": SIGNALS["forced_power_kw"], "value": f"{power_kw:.3f}"},
        {"id": SIGNALS["forced_period_min"], "value": str(duration_min)},
    ]


def build_stop_command() -> list[dict]:
    """Build the FusionSolar signal payload to stop forced charge/discharge."""
    return [{"id": SIGNALS["charge_discharge_mode"], "value": "0"}]
