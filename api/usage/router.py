"""GET /usage and GET /usage/months: electricity bought in every price window and sold, in kWh and euro, by day
and by month."""

import asyncio
import logging
import time as clock
from datetime import date, time, timedelta

from fastapi import APIRouter, Depends, Query, Request

from auth import require_read_access
from mock_clock import get_now

from .report import GAP, at, months, report, tariff_info

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_read_access)])

SETTLED = 3600  # seconds after a day's end: its readings are all in, so its report is kept and not worked out again
WARM_MONTHS = 13  # the app's month view: this month and the 12 before
WARM_AFTER = 30  # seconds after startup, once the inverter link has settled


def day_reports(state, wanted: list[date]) -> dict[date, dict]:
    """Each of `wanted` days' report (days in order). A day that ended over an hour ago is kept in memory (in
    the app's `state`), so a month or an old week is worked out from the readings once."""
    if not hasattr(state, "usage_days"):
        state.usage_days = {}
    kept = state.usage_days
    result = {day: kept[day] for day in wanted if day in kept}
    missing = [day for day in wanted if day not in kept]
    if missing:
        since = at(missing[0], time(0, 0)) - GAP  # a reading from just before the first midnight
        until = at(missing[-1], None) + GAP  # and one from just after the last
        rows = state.history.samples(since, until=until)
        meter = [(t, bought, sold) for t, _, _, _, bought, sold in rows if bought is not None and sold is not None]
        home = [(t, home_kw) for t, _, home_kw, _, _, _ in rows]
        now = clock.time()
        for day, entry in zip(missing, report(meter, missing, home)):
            result[day] = entry
            if at(day, None) + SETTLED <= now:
                kept[day] = entry
    return result


def month_days(today: date, count: int) -> list[date]:
    """Every day from the 1st of the month `count` - 1 months before `today`'s to `today`."""
    first = today.replace(day=1)
    for _ in range(count - 1):
        first = (first - timedelta(days=1)).replace(day=1)
    return [first + timedelta(days=n) for n in range((today - first).days + 1)]


async def warm_up(state):
    """Work out the app's months in the background soon after startup: a restart forgets them, and a year of
    minutes takes the Pi several seconds, which the app's first request after a restart would otherwise wait for."""
    await asyncio.sleep(WARM_AFTER)
    started = clock.monotonic()
    try:
        days = await asyncio.to_thread(day_reports, state, month_days(get_now().date(), WARM_MONTHS))
        logger.info("Usage: %d days worked out in %.1f s", len(days), clock.monotonic() - started)
    except Exception:
        logger.exception("Usage: working out the months failed")


@router.get("/usage")
async def get_usage(request: Request, days: int = Query(7, ge=1, le=30), end: date | None = None):
    """The `days` days (1 to 30, default 7) ending on `end` (default today; a later date is cut to today),
    oldest first; today's is so far.

    Each day: kWh and euro bought in each of the tariff's bands, their total, kWh and euro sold, net_eur
    (bought less sold; the standing charge is not in it) and used_kwh, what the house used from the grid,
    the battery and solar; and the same for each half hour. The meter's readings are corrected to match
    ESB's billing meter (see usage/tariff.py); the house's use is as measured. `measured_hours` is how much
    of the day the meter readings cover; a past day is `complete` when it misses less than 15 minutes.
    """
    last = min(end or get_now().date(), get_now().date())
    span = [last - timedelta(days=n) for n in range(days - 1, -1, -1)]
    reports = await asyncio.to_thread(day_reports, request.app.state, span)
    return {"tariff": tariff_info(), "days": [reports[day] for day in span]}


@router.get("/usage/months")
async def get_usage_months(request: Request, months_back: int = Query(12, ge=1, le=36, alias="months")):
    """The last `months` calendar months (1 to 36, default 12), oldest first, ending with this one so far;
    months before the first readings are left out.

    Each month: the same totals as a day in GET /usage, summed over its days, and `days`, its days from the
    1st to its last (this month: to today) without their half hours. `complete` when it has ended and every
    day of it is complete.
    """
    span = month_days(get_now().date(), months_back)
    reports = await asyncio.to_thread(day_reports, request.app.state, span)
    return {"tariff": tariff_info(), "months": months([reports[day] for day in span])}
