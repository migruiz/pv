"""Pydantic models for charge ramp configuration and status."""

from typing import Optional

from pydantic import BaseModel, Field


class ChargeRampConfig(BaseModel):
    """Persisted charge ramp configuration."""

    duration_minutes: int = Field(ge=10, le=1440, default=240)
    initial_power: int = Field(ge=200, le=2500, default=200)
    top_power: int = Field(ge=200, le=2500, default=2500)
    final_power: int = Field(ge=200, le=2500, default=200)


class ChargeRampConfigUpdate(BaseModel):
    """Request body for partial config update."""

    duration_minutes: Optional[int] = Field(default=None, ge=10, le=1440)
    initial_power: Optional[int] = Field(default=None, ge=200, le=2500)
    top_power: Optional[int] = Field(default=None, ge=200, le=2500)
    final_power: Optional[int] = Field(default=None, ge=200, le=2500)


class ChargeRampStatus(BaseModel):
    """Runtime status of the charge ramp."""

    active: bool
    current_power_w: Optional[int] = None
    elapsed_minutes: Optional[float] = None
    total_minutes: Optional[int] = None
    progress: Optional[float] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    last_adjustment: Optional[str] = None


class StartResponse(BaseModel):
    """Response after starting a charge ramp."""

    success: bool
    initial_power_w: Optional[int] = None
    duration_minutes: Optional[int] = None
    end_time: Optional[str] = None


class StopResponse(BaseModel):
    """Response after stopping a charge ramp."""

    success: bool
    detail: str


def build_status_dict(
    power_w: int,
    progress: float,
    elapsed_minutes: float,
    total_minutes: int,
    start_time_iso: str,
    end_time_iso: str,
    now_iso: str,
) -> dict:
    """Build a status snapshot dict (shared by ramp loop and manager)."""
    return {
        "active": True,
        "current_power_w": power_w,
        "elapsed_minutes": round(elapsed_minutes, 1),
        "total_minutes": total_minutes,
        "progress": round(progress, 4),
        "start_time": start_time_iso,
        "end_time": end_time_iso,
        "last_adjustment": now_iso,
    }
