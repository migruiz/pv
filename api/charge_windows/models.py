"""Pydantic models for charge windows configuration and status."""

from typing import Optional

from pydantic import BaseModel, Field


def _parse_time_minutes(time_str: str) -> int:
    """Convert 'HH:MM' to minutes since midnight."""
    h, m = time_str.split(":")
    return int(h) * 60 + int(m)


class ChargeWindow(BaseModel):
    """A configured charge window with schedule and power curve parameters."""

    id: str
    name: str
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    start_power: int = Field(ge=200, le=2500)
    peak_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    peak_power: int = Field(ge=200, le=2500)
    end_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    end_power: int = Field(ge=200, le=2500)
    notify: bool = True
    enabled: bool = True

    @property
    def duration_minutes(self) -> int:
        """Total minutes from start_time to end_time (handles midnight crossing)."""
        start = _parse_time_minutes(self.start_time)
        end = _parse_time_minutes(self.end_time)
        diff = end - start
        if diff <= 0:
            diff += 1440
        return diff


class ChargeWindowCreate(BaseModel):
    """Request body for creating a new charge window."""

    name: str
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    start_power: int = Field(ge=200, le=2500)
    peak_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    peak_power: int = Field(ge=200, le=2500)
    end_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    end_power: int = Field(ge=200, le=2500)
    notify: bool = True
    enabled: bool = True

    @property
    def duration_minutes(self) -> int:
        start = _parse_time_minutes(self.start_time)
        end = _parse_time_minutes(self.end_time)
        diff = end - start
        if diff <= 0:
            diff += 1440
        return diff


class ChargeWindowUpdate(BaseModel):
    """Request body for partial update of a charge window."""

    name: Optional[str] = None
    start_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    start_power: Optional[int] = Field(default=None, ge=200, le=2500)
    peak_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    peak_power: Optional[int] = Field(default=None, ge=200, le=2500)
    end_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    end_power: Optional[int] = Field(default=None, ge=200, le=2500)
    notify: Optional[bool] = None
    enabled: Optional[bool] = None


class ChargeWindowStatus(BaseModel):
    """Runtime status of a charge window."""

    window_id: str
    window_name: str
    active: bool
    current_power_w: Optional[int] = None
    progress: Optional[float] = None
    elapsed_minutes: Optional[float] = None
    total_minutes: Optional[int] = None
    end_time: Optional[str] = None
    minutes_remaining: Optional[float] = None
    last_adjustment: Optional[str] = None


class StartResponse(BaseModel):
    """Response after starting a charge window."""

    success: bool
    window_id: str
    window_name: str
    initial_power_w: Optional[int] = None
    end_time: Optional[str] = None


class StopResponse(BaseModel):
    """Response after stopping a charge window."""

    success: bool
    detail: str


def build_status_dict(
    window_id: str,
    window_name: str,
    power_w: int,
    progress: float,
    elapsed_minutes: float,
    total_minutes: int,
    end_time_iso: str,
    now_iso: str,
) -> dict:
    """Build a status snapshot dict (shared by ramp loop and scheduler)."""
    return {
        "window_id": window_id,
        "window_name": window_name,
        "active": True,
        "current_power_w": power_w,
        "progress": round(progress, 4),
        "elapsed_minutes": round(elapsed_minutes, 1),
        "total_minutes": total_minutes,
        "end_time": end_time_iso,
        "minutes_remaining": round(max(0, total_minutes - elapsed_minutes), 1),
        "last_adjustment": now_iso,
    }
