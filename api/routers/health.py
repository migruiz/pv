"""Health check endpoint."""

from fastapi import APIRouter, Depends

from dependencies import get_session
from session import SolarSession

router = APIRouter()


@router.get("/health")
async def health(session: SolarSession = Depends(get_session)):
    """Check if the FusionSolar session is alive (no API key required)."""
    try:
        alive = await session.call("is_session_active")
        return {"status": "ok" if alive else "session_expired"}
    except Exception:
        return {"status": "error"}
