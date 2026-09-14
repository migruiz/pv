"""Health check endpoint."""

from fastapi import APIRouter, Depends

from dependencies import get_inverter, get_session
from session import SolarSession

router = APIRouter()


@router.get("/health")
async def health(session: SolarSession = Depends(get_session), inverter=Depends(get_inverter)):
    """FusionSolar session (still used for battery control) and inverter link. No API key required."""
    try:
        alive = await session.call("is_session_active")
        status = "ok" if alive else "session_expired"
    except Exception:
        status = "error"
    age = inverter.age()
    return {"status": status, "inverter_reading_age_s": None if age is None else round(age, 1)}
