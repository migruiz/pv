"""The electricity tariff the usage report prices by: Electric Ireland Home Electric+ Night Boost, from 13 Oct 2026.

Prices include VAT and the 5% direct debit discount. The 0.5% paperless billing discount is for variable tariffs
only: this is a fixed-term contract (to 13 Oct 2027), and the first bill gave it for 13-14 Oct 2026 alone. Change
this file when the supplier changes (expected March 2027).
"""

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo


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
    # The bill's 10.56c, 18c and 36.5c, less 5%, plus 9% VAT
    Band("boost", "Boost", "02:00-04:00", 10.93),
    Band("night", "Night", "23:00-08:00", 18.64),
    Band("day", "Day", "08:00-23:00", 37.80),
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
STANDING_CHARGE_EUR_PER_DAY = 0.9002  # €0.8259 + 9% VAT, urban (€328.58 a year)
PSO_LEVY_EUR_PER_MONTH = 0.5559  # €0.51 + 9% VAT, flat each month, set by the CRU from 1 Oct 2026 (yearly from October)

# The Huawei meter against ESB's billing meter, to bring its totals in line with the bill. Bought: 1.7% less over
# 5 Feb - 5 Oct 2026 (243 days, the same every month), and with x1.017 within 0.25% of ESB's half hours on the first
# Electric Ireland bill (13 Oct - 5 Nov). Sold depends on where the history's totals came from: before the API read
# the meter itself (13 Oct 2026 06:37) they are FusionSolar's, which read 1.0% more than ESB; since, the inverter's
# own register, which read 0.7% less on that bill (215.4 kWh against 217).
CORRECTION_BOUGHT = 1.017
CORRECTION_SOLD = 1.007
CORRECTION_SOLD_FUSIONSOLAR = 0.990
OWN_READINGS_FROM = datetime(2026, 10, 13, 6, 37, tzinfo=ZoneInfo("Europe/Dublin")).timestamp()
