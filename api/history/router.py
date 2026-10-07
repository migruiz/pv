"""GET /history: the stored minute-by-minute solar, home and battery readings, for the home's screens."""

import asyncio
import time

from fastapi import APIRouter, Depends, Request

from auth import require_read_access

router = APIRouter(dependencies=[Depends(require_read_access)])

DEFAULT_SECONDS = 12 * 3600
MAX_SECONDS = 48 * 3600  # an earlier `since` is cut to the last 48 hours


@router.get("/history")
async def get_history(request: Request, since: float | None = None):
    """Every stored minute from `since` (Unix seconds; default 12 hours ago, at most 48), oldest first.

    A minute's solar and home kW are the average of its readings, its battery % the latest one, and its
    `observed_at` (Unix seconds) the time of that latest reading. The minute still being read changes
    until it is over, so a client keeping a copy asks again from its last `observed_at`.
    """
    now = time.time()
    start = min(now, max(now - MAX_SECONDS, now - DEFAULT_SECONDS if since is None else since))
    rows = await asyncio.to_thread(request.app.state.history.samples, start)
    return {"minutes": [{"observed_at": at, "pv_kw": pv, "home_kw": home, "battery_soc": soc}
                        for at, pv, home, soc in rows]}
