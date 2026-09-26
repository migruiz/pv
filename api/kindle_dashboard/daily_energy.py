"""Today's running energy (kWh since Dublin midnight) for the solar and home charts."""

from bisect import bisect_right
from datetime import datetime, time, timedelta

from kindle_dashboard.estimate import DUBLIN, daylight
from kindle_dashboard.history import finite
from kindle_dashboard.renderer import EnergyChart

# The solar and home charts take turns: power for 10 s, then today's running totals for 10 s
SWITCH_SECONDS = 10
# The very cheap night rate ends; the home chart marks its total at this time
NIGHT_RATE_END = time(5)
# The production chart leaves out the night: it runs from an hour before sunrise to an hour after sunset
DAYLIGHT_MARGIN = timedelta(hours=1)


def charts_at(seconds):
    """Which charts to draw at this Unix time, "power" or "energy", switching every SWITCH_SECONDS.

    Real time, not the mock clock (which stands still once set): the switching is only for the eye.
    """
    return "energy" if int(seconds // SWITCH_SECONDS) % 2 else "power"


def running_totals(points, today_kwh=None):
    """Add up one day's (timestamp, kW) points into kWh since the first point.

    Consecutive points are joined by trapezoids, so gaps are bridged linearly.
    Given the inverter's daily counter, the totals are scaled to end at it.
    """
    totals, previous = [], None
    for stamp, kw in sorted(points):
        total = totals[-1][1] + (previous[1] + kw) / 2 * (stamp - previous[0]) / 3600 if previous else 0.0
        totals.append((stamp, total))
        previous = (stamp, kw)
    if totals and today_kwh is not None and totals[-1][1] > 0:
        factor = today_kwh / totals[-1][1]
        totals = [(stamp, total * factor) for stamp, total in totals]
    return totals


def values_at(totals, stamps):
    """Totals at the given timestamps, interpolated between points.

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
        if index < len(totals):
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


def hour_label(at):
    """The nearest whole hour, as on the other chart axes: 6a, 12p, 8p."""
    hour = (at + timedelta(minutes=30)).hour
    return f"{hour % 12 or 12}{'a' if hour < 12 else 'p'}"


def energy_chart(store, end, current, key, today_kwh=None, mark=None, daylight_only=False):
    """Today's running kWh of one power reading ("pv_kw" or "home_kw"), midnight to midnight.

    Adds up stored power from today's Dublin midnight, plus the current reading. Positions
    are real fractions of the chart's span, so a daylight-saving day of 23 or 25 hours keeps
    its hours in place. `daylight_only` spans today's sunrise to sunset instead, an hour more
    on each side (calculated for Dublin, see estimate.daylight); the running total still starts
    at midnight, and the line is cut off at the chart's edges. With `today_kwh` the line is
    scaled to end at that total. With `mark` (a clock time) the chart marks the total then,
    once that time has passed.
    """
    end_ts = end.timestamp()
    day = datetime.fromtimestamp(end_ts, DUBLIN).date()
    midnight = datetime.combine(day, time(), tzinfo=DUBLIN)
    if daylight_only:
        rise, setting = daylight(day)
        first, last = rise - DAYLIGHT_MARGIN, setting + DAYLIGHT_MARGIN
        edges = hour_label(first), hour_label(last)
    else:
        first, last = midnight, datetime.combine(day + timedelta(days=1), time(), tzinfo=DUBLIN)
        edges = "12a", "12a"

    def at(clock):
        return datetime.combine(day, clock, tzinfo=DUBLIN).timestamp()

    def position(stamp):
        return (stamp - first.timestamp()) / (last.timestamp() - first.timestamp())

    points = [row for row in store.power(key, midnight.timestamp(), end_ts) if row[0] < end_ts]
    kw = finite(current.get(key))
    if kw is not None:
        points.append((end_ts, kw))
    totals = running_totals(points, today_kwh)
    marked = None
    if mark is not None:
        value = values_at(totals, [at(mark)])[0] if at(mark) <= end_ts else None
        marked = (position(at(mark)), hour_label(datetime.combine(day, mark)), value)
    return EnergyChart(samples=[total for _, total in totals],
                       positions=[position(stamp) for stamp, _ in totals],
                       hours=[(0, edges[0]), (position(at(time(12))), "12p"), (1, edges[1])],
                       mark=marked)


def chart_history(store, end, current, charts):
    """The stored 12-hour history and positions, and today's energy charts when the charts show energy."""
    history, positions = store.chart(end, current)
    if charts != "energy":
        return history, positions, None
    return history, positions, {
        "pv_kw": energy_chart(store, end, current, "pv_kw", today_kwh=solar_today_kwh(current), daylight_only=True),
        "home_kw": energy_chart(store, end, current, "home_kw", mark=NIGHT_RATE_END),
    }
