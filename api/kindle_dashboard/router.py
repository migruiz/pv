"""GET /dashboard.png — the Kindle's read-only e-ink dashboard."""

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Response

import mock_clock
from auth import require_kindle_token
from dependencies import get_inverter
from inverter.reader import InverterUnavailable
from kindle_dashboard.renderer import render_png

logger = logging.getLogger("pv.kindle")

router = APIRouter(dependencies=[Depends(require_kindle_token)])

DUBLIN = ZoneInfo("Europe/Dublin")

# Last successful readings, re-drawn with a STALE DATA banner when the inverter stops answering
_last_good: tuple[dict, datetime] | None = None
# The Kindle asks every few seconds; only draw again when the reading (or staleness) changed
_cached: tuple[tuple, bytes] | None = None


def _reading_time(data: dict) -> datetime:
    """When the inverter was read, in Dublin time (the renderer prints it as-is)."""
    try:
        return datetime.fromisoformat(data["updated_at"]).astimezone(DUBLIN)
    except (KeyError, TypeError, ValueError):
        return mock_clock.get_now()


@router.get("/dashboard.png", response_class=Response)
async def get_dashboard_png(inverter=Depends(get_inverter)):
    """800x600 1-bit PNG. Always 200 so the Kindle keeps showing something useful."""
    global _last_good, _cached
    try:
        data = inverter.dashboard()
        updated_at, stale = _reading_time(data), False
        _last_good = (data, updated_at)
    except InverterUnavailable as exc:
        if _cached is None or not _cached[0][1]:
            logger.warning("Kindle dashboard serving stale data: %s", exc)
        (data, updated_at), stale = _last_good or ({}, mock_clock.get_now()), True

    key = (updated_at, stale)
    if _cached is None or _cached[0] != key:
        _cached = (key, await asyncio.to_thread(render_png, data, updated_at, stale))
    return Response(_cached[1], media_type="image/png", headers={"Cache-Control": "no-store"})
