"""GET /history: the stored minute-by-minute solar, home, battery and grid meter readings, for the home's screens."""

import asyncio
import time

from fastapi import APIRouter, Depends, Query, Request

from auth import require_read_access

router = APIRouter(dependencies=[Depends(require_read_access)])

DEFAULT_SECONDS = 12 * 3600
MAX_SECONDS = 8 * 86400  # an earlier `since` is cut to the last 8 days (the kitchen screens' week)


@router.get("/history")
async def get_history(request: Request, since: float | None = None, step: int = Query(1, ge=1, le=60)):
    """Every stored minute from `since` (Unix seconds; default 12 hours ago, at most 8 days), oldest first.

    A minute's solar and home kW are the average of its readings, its battery % and the grid meter's
    kWh bought and sold totals the latest ones (null before 13 Oct 2026), and its `observed_at` (Unix
    seconds) the time of that latest reading. The difference between two totals is what was bought or
    sold in between. The minute still being read changes until it is over, so a client keeping a copy
    asks again from its last `observed_at`.

    With `step` (minutes, 1 to 60) each entry is that many minutes instead, counted from the Unix epoch
    (so 5 gives :00, :05, ...): solar and home kW averaged over its stored minutes, the latest battery %,
    totals and `observed_at`. A week is about 2,000 entries in 5-minute steps against 10,000 minutes.
    """
    now = time.time()
    start = min(now, max(now - MAX_SECONDS, now - DEFAULT_SECONDS if since is None else since))
    rows = await asyncio.to_thread(request.app.state.history.samples, start, step)
    return {"minutes": [{"observed_at": at, "pv_kw": pv, "home_kw": home, "battery_soc": soc,
                         "grid_import_total_kwh": bought, "grid_export_total_kwh": sold}
                        for at, pv, home, soc, bought, sold in rows]}
