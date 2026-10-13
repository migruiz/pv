"""GET /usage: each day's electricity bought in every price window and sold, in kWh and euro."""

import asyncio
from datetime import time, timedelta

from fastapi import APIRouter, Depends, Query, Request

from auth import require_read_access
from mock_clock import get_now

from .report import GAP, at, report, tariff_info

router = APIRouter(dependencies=[Depends(require_read_access)])


@router.get("/usage")
async def get_usage(request: Request, days: int = Query(7, ge=1, le=30)):
    """The last `days` days (1 to 30, default 7), oldest first, the last one today so far.

    Each day: kWh and euro bought in each of the tariff's bands, their total, kWh and euro sold, net_eur
    (bought less sold; the standing charge is not in it) and used_kwh, what the house used from the grid,
    the battery and solar; and the same for each half hour. The meter's readings are corrected to match
    ESB's billing meter (see usage/tariff.py); the house's use is as measured. `measured_hours` is how much
    of the day the meter readings cover; a past day is `complete` when it misses less than 15 minutes.
    """
    today = get_now().date()
    span = [today - timedelta(days=n) for n in range(days - 1, -1, -1)]
    since = at(span[0], time(0, 0)) - GAP  # a reading from just before the first midnight
    rows = await asyncio.to_thread(request.app.state.history.samples, since)
    meter = [(t, bought, sold) for t, _, _, _, bought, sold in rows if bought is not None and sold is not None]
    home = [(t, home_kw) for t, _, home_kw, _, _, _ in rows]
    return {"tariff": tariff_info(), "days": report(meter, span, home)}
