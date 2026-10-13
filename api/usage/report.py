"""Each day's kWh bought in every price window and sold, by half hour, priced, from the grid meter's running totals;
and what the house used, whatever its source, from its minute averages.

The meter's totals are stored once a minute (history/store.py). What was bought or sold between two readings is
spread evenly over the time between them: a stretch that crosses the start of a half hour is split at it, and a
gap (the API or the hotspot link down) still counts in full, shared out by time, but not as measured time.
A day is its half hours from midnight to midnight (46 or 50 on a clock-change day); the windows start on the
hour, so each half hour sits in one window: the one its start is in. Pure functions: no clock, no I/O.
"""

import bisect
from datetime import date, datetime, time, timedelta

from mock_clock import TZ

from . import tariff

GAP = 300  # seconds: readings further apart than this are a gap in the readings, not measured time
COMPLETE_WITHIN = 900  # seconds: a past day missing less than this is complete
HALF_HOUR = 1800


def at(day: date, wall: time | None) -> float:
    """Unix seconds of a Dublin wall-clock time on `day`; None is the midnight that ends it."""
    if wall is None:
        day, wall = day + timedelta(days=1), time(0, 0)
    return datetime.combine(day, wall).replace(tzinfo=TZ).timestamp()


def band_at(wall: time) -> str:
    """The band of the window a Dublin wall-clock time is in."""
    for window in tariff.WINDOWS:
        if window.start <= wall and (window.end is None or wall < window.end):
            return window.band
    raise ValueError(f"No tariff window holds {wall}")


def tariff_info() -> dict:
    return {
        "name": tariff.NAME,
        "windows": [{"band": w.band, "start": w.start.strftime("%H:%M"),
                     "end": w.end.strftime("%H:%M") if w.end else "24:00"} for w in tariff.WINDOWS],
        "bands": [{"id": b.id, "name": b.name, "hours": b.hours, "cents_per_kwh": b.cents_per_kwh}
                  for b in tariff.BANDS],
        "export_cents_per_kwh": tariff.EXPORT_CENTS_PER_KWH,
        "standing_charge_eur_per_day": tariff.STANDING_CHARGE_EUR_PER_DAY,
        "correction": {"bought": tariff.CORRECTION_BOUGHT, "sold": tariff.CORRECTION_SOLD},
    }


def report(readings, days: list[date], home=()) -> list[dict]:
    """One entry per day of `days`, in their order.

    `readings`: (Unix seconds, kWh bought total, kWh sold total), oldest first, including one from before
    the first day's midnight when there is one. `home`: (Unix seconds, the house's average kW over the
    minute it ends), one per stored minute: a minute missing from it counts nothing.
    """
    # Every half hour of every day, in time order: [start, day index, kWh bought, kWh sold, measured seconds,
    # kWh the house used]
    slots = []
    for i, day in enumerate(days):
        start, end = at(day, time(0, 0)), at(day, None)
        slots += [[t, i, 0.0, 0.0, 0.0, 0.0] for t in range(int(start), int(end), HALF_HOUR)]
    starts = [s[0] for s in slots]

    for observed_at, kw in home:
        k = bisect.bisect_right(starts, observed_at) - 1
        if k >= 0 and observed_at < slots[k][0] + HALF_HOUR:
            slots[k][5] += kw / 60

    for (t0, bought0, sold0), (t1, bought1, sold1) in zip(readings, readings[1:]):
        more_bought, more_sold = bought1 - bought0, sold1 - sold0
        if t1 <= t0 or more_bought < 0 or more_sold < 0:  # out of order, or the meter was reset
            continue
        k = max(bisect.bisect_right(starts, t0) - 1, 0)
        while k < len(slots) and slots[k][0] < t1:
            slot = slots[k]
            overlap = min(slot[0] + HALF_HOUR, t1) - max(slot[0], t0)
            if overlap > 0:
                share = overlap / (t1 - t0)
                slot[2] += more_bought * share
                slot[3] += more_sold * share
                if t1 - t0 <= GAP:
                    slot[4] += overlap
            k += 1

    rates = {b.id: b.cents_per_kwh / 100 for b in tariff.BANDS}
    sell = tariff.EXPORT_CENTS_PER_KWH / 100
    result = []
    for i, day in enumerate(days):
        halves = []
        kwh = dict.fromkeys(rates, 0.0)
        sold_kwh = measured = used_kwh = 0.0
        for start, _, bought, sold, seconds, used in (s for s in slots if s[1] == i):
            wall = datetime.fromtimestamp(start, TZ).time()
            band = band_at(wall)
            bought *= tariff.CORRECTION_BOUGHT
            sold *= tariff.CORRECTION_SOLD
            kwh[band] += bought
            sold_kwh += sold
            measured += seconds
            used_kwh += used
            halves.append({"start": wall.strftime("%H:%M"), "band": band,
                           "bought_kwh": round(bought, 3), "bought_eur": round(bought * rates[band], 3),
                           "sold_kwh": round(sold, 3), "sold_eur": round(sold * sell, 3),
                           "used_kwh": round(used, 3)})
        eur = {band: value * rates[band] for band, value in kwh.items()}
        sold_eur = sold_kwh * sell
        length = at(day, None) - at(day, time(0, 0))  # 23 or 25 hours on a clock-change day
        result.append({
            "date": day.isoformat(),
            "complete": measured >= length - COMPLETE_WITHIN,
            "measured_hours": round(measured / 3600, 2),
            "bought": {band: {"kwh": round(kwh[band], 3), "eur": round(eur[band], 3)} for band in kwh},
            "bought_total": {"kwh": round(sum(kwh.values()), 3), "eur": round(sum(eur.values()), 3)},
            "sold": {"kwh": round(sold_kwh, 3), "eur": round(sold_eur, 3)},
            "net_eur": round(sum(eur.values()) - sold_eur, 3),
            "used_kwh": round(used_kwh, 3),
            "half_hours": halves,
        })
    return result
