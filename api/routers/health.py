"""Health check endpoint."""

from fastapi import APIRouter, Depends

from dependencies import get_inverter

router = APIRouter()

STALE_AFTER_S = 30


@router.get("/health")
async def health(inverter=Depends(get_inverter)):
    """Age of the last inverter reading. No API key required."""
    age = inverter.age()
    return {
        "status": "ok" if age is not None and age <= STALE_AFTER_S else "no_recent_reading",
        "inverter_reading_age_s": None if age is None else round(age, 1),
    }
