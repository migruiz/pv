"""Running daily energy (kWh since Dublin midnight) for the solar and home charts."""

from bisect import bisect_right
from datetime import datetime

from kindle_dashboard.estimate import DUBLIN
from kindle_dashboard.history import WINDOW_SECONDS, finite


def local_day(stamp):
    return datetime.fromtimestamp(stamp, DUBLIN).date()


def running_totals(points, today_kwh=None):
    """Add up (timestamp, kW) points into kWh since each point's Dublin midnight.

    Consecutive points are joined by trapezoids, so short gaps are bridged
    linearly, and the total restarts at the first point of each day. Given the
    inverter's daily counter, the last day's totals are scaled to end at it.
    """
    totals, previous = [], None
    for stamp, kw in sorted(points):
        same_day = previous is not None and local_day(stamp) == local_day(previous[0])
        total = totals[-1][1] + (previous[1] + kw) / 2 * (stamp - previous[0]) / 3600 if same_day else 0.0
        totals.append((stamp, total))
        previous = (stamp, kw)
    if totals and today_kwh is not None and totals[-1][1] > 0:
        last_day, factor = local_day(totals[-1][0]), today_kwh / totals[-1][1]
        totals = [(stamp, total * factor if local_day(stamp) == last_day else total)
                  for stamp, total in totals]
    return totals


def values_at(totals, stamps):
    """Totals at the given timestamps, interpolated within a day.

    None stamps and times before the first total stay None.
    """
    times = [stamp for stamp, _ in totals]
    values = []
    for stamp in stamps:
        index = 0 if stamp is None else bisect_right(times, stamp)
        if index == 0:
            values.append(None)
            continue
        left, total = totals[index - 1]
        if index < len(totals) and local_day(times[index]) == local_day(left):
            right, next_total = totals[index]
            total += (next_total - total) * (stamp - left) / (right - left)
        values.append(total)
    return values


def solar_today_kwh(reading):
    """Today's solar production from the inverter's own counters.

    The inverter's daily yield also counts battery discharge, so subtract it.
    On 15 September 2026 this matched FusionSolar's production figure.
    """
    yield_kwh = finite(reading.get("energy_today_kwh"))
    discharged = finite(reading.get("discharged_today_kwh"))
    return None if yield_kwh is None or discharged is None else max(0.0, yield_kwh - discharged)


def energy_history(store, end, current, history, positions, key, today_kwh=None):
    """Running daily kWh of one power reading ("pv_kw" or "home_kw") per chart sample.

    Adds up stored power from the Dublin midnight before the chart starts,
    plus the current reading. With `today_kwh`, today's line is scaled to end
    at that total. Gaps in the chart's samples stay gaps.
    """
    end_ts = end.timestamp()
    start = end_ts - WINDOW_SECONDS
    midnight = datetime.fromtimestamp(start, DUBLIN).replace(hour=0, minute=0, second=0, microsecond=0)
    points = [row for row in store.power(key, midnight.timestamp(), end_ts) if row[0] < end_ts]
    kw = finite(current.get(key))
    if kw is not None:
        points.append((end_ts, kw))
    totals = running_totals(points, today_kwh)
    stamps = [None if sample is None else start + position * WINDOW_SECONDS
              for sample, position in zip(history.get(key, ()), positions)]
    return values_at(totals, stamps)
