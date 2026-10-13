"""The electricity tariff the usage report prices by: Electric Ireland Home Electric+ Night Boost, from 13 Oct 2026.

Prices include VAT and the 5.5% direct debit and online billing discount. Change this file when the supplier
changes (expected March 2027).
"""

from dataclasses import dataclass
from datetime import time


@dataclass(frozen=True)
class Band:
    id: str
    name: str
    hours: str
    cents_per_kwh: float


@dataclass(frozen=True)
class Window:
    """A stretch of the Dublin wall clock priced at one band. `end` None is midnight at the end of the day."""
    band: str
    start: time
    end: time | None


NAME = "Electric Ireland Night Boost"
BANDS = [
    Band("boost", "Boost", "02:00-04:00", 10.88),
    Band("night", "Night", "23:00-08:00", 18.54),
    Band("day", "Day", "08:00-23:00", 37.60),
]
# In order through the day, each minute in exactly one
WINDOWS = [
    Window("night", time(0, 0), time(2, 0)),
    Window("boost", time(2, 0), time(4, 0)),
    Window("night", time(4, 0), time(8, 0)),
    Window("day", time(8, 0), time(23, 0)),
    Window("night", time(23, 0), None),
]
EXPORT_CENTS_PER_KWH = 19.5
STANDING_CHARGE_EUR_PER_DAY = 0.90  # €328.58 a year, urban

# The Huawei meter against ESB's billing meter over 5 Feb - 5 Oct 2026 (243 days): it read 1.7% less bought and
# 1.0% more sold, the same every month. These bring its totals in line with the bill.
CORRECTION_BOUGHT = 1.017
CORRECTION_SOLD = 0.990
