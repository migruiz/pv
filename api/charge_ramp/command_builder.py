"""FusionSolar signal payload construction for charge ramp.

Builds the signal command lists sent to the inverter
for operation mode switching and max charge power control.
"""

import json

# FusionSolar signal IDs
SIGNALS = {
    "max_charge_power": "10011",        # 200~2500 W
    "operation_mode": "230320241",      # 2=Max self-consumption, 5=TOU
    "charge_from_ac": "230320279",      # 0=Disabled, 1=Enabled
    "tou_windows": "230320283",         # JSON-encoded TOU time windows
}

# TOU time window schedule (charge 02:05-04:55, discharge rest of day)
TOU_WINDOWS_VALUE = json.dumps([
    {
        "endTime": "04:55",
        "onOff": 0,
        "repeatPeriod": [7, 1, 2, 3, 4, 5, 6],
        "startTime": "02:05",
    },
    {
        "endTime": "02:05",
        "onOff": 1,
        "repeatPeriod": [7, 1, 2, 3, 4, 5, 6],
        "startTime": "04:55",
    },
])


def build_start_command(power_w: int) -> list[dict]:
    """Signals to begin ramp: self-consumption + AC charge off + initial power."""
    return [
        {"id": SIGNALS["max_charge_power"], "value": str(power_w)},
        {"id": SIGNALS["operation_mode"], "value": "2"},
        {"id": SIGNALS["charge_from_ac"], "value": "0"},
    ]


def build_power_update_command(power_w: int) -> list[dict]:
    """Signal to adjust charge power during ramp."""
    return [
        {"id": SIGNALS["max_charge_power"], "value": str(power_w)},
    ]


def build_restore_command() -> list[dict]:
    """Restore signals: TOU mode + AC charge on + 2500W + TOU windows."""
    return [
        {"id": SIGNALS["max_charge_power"], "value": "2500"},
        {"id": SIGNALS["operation_mode"], "value": "5"},
        {"id": SIGNALS["charge_from_ac"], "value": "1"},
        {"id": SIGNALS["tou_windows"], "value": TOU_WINDOWS_VALUE},
    ]
