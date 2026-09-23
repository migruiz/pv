"""Inverter register writes that start and stop a forced discharge.

Proven on the SUN2000-5K-LB0 on 2026-09-23: the FusionSolar cloud's own forced-discharge command sets
these same registers.
"""

import math

from huawei_solar.register_values import (
    StorageForcibleChargeDischarge,
    StorageForcibleChargeDischargeTargetMode,
)

Settings = list[tuple[str, object]]


def discharge(power_kw: float, minutes_remaining: float) -> Settings:
    """Discharge at power_kw until the window ends: the inverter stops by itself when the period is up."""
    return [
        ("storage_forcible_charge_discharge_setting_mode", StorageForcibleChargeDischargeTargetMode.TIME),
        ("storage_forced_charging_and_discharging_period", min(max(math.ceil(minutes_remaining), 1), 1440)),
        ("storage_forcible_discharge_power", round(power_kw * 1000)),
        ("forcible_charge_discharge_write", StorageForcibleChargeDischarge.DISCHARGE),
    ]


def stop() -> Settings:
    return [("forcible_charge_discharge_write", StorageForcibleChargeDischarge.STOP)]
