"""Dashboard endpoint — live energy flow + stats for the Android app, read from the inverter."""

from fastapi import APIRouter, Depends, HTTPException

from auth import require_api_key
from dependencies import get_inverter
from inverter.reader import InverterUnavailable

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/dashboard")
async def get_dashboard(inverter=Depends(get_inverter)):
    """Latest inverter readings, refreshed in the background every few seconds."""
    try:
        return inverter.dashboard()
    except InverterUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
