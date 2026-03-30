"""Pydantic models for discharge windows configuration and status."""

from typing import Optional

from pydantic import BaseModel, Field


class DischargeWindow(BaseModel):
    """A configured discharge window with schedule and target parameters."""

    id: str
    name: str
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$")  # "HH:MM"
    duration_minutes: int = Field(ge=1, le=1440)
    target_soc: float = Field(ge=0, le=100)
    notify: bool = True
    enabled: bool = True


class DischargeWindowCreate(BaseModel):
    """Request body for creating a new discharge window."""

    name: str
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    duration_minutes: int = Field(ge=1, le=1440)
    target_soc: float = Field(ge=0, le=100)
    notify: bool = True
    enabled: bool = True


class DischargeWindowUpdate(BaseModel):
    """Request body for partial update of a discharge window."""

    name: Optional[str] = None
    start_time: Optional[str] = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    duration_minutes: Optional[int] = Field(default=None, ge=1, le=1440)
    target_soc: Optional[float] = Field(default=None, ge=0, le=100)
    notify: Optional[bool] = None
    enabled: Optional[bool] = None


class WindowStatus(BaseModel):
    """Runtime status of a discharge window."""

    window_id: str
    window_name: str
    active: bool
    current_soc: Optional[float] = None
    discharge_power_kw: Optional[float] = None
    target_time: Optional[str] = None
    minutes_remaining: Optional[float] = None
    hours_remaining: Optional[float] = None
    last_adjustment: Optional[str] = None


class StartResponse(BaseModel):
    """Response after manually starting a discharge window."""

    success: bool
    window_id: str
    window_name: str
    initial_soc: Optional[float] = None
    discharge_power_kw: Optional[float] = None
    remaining_energy_kwh: Optional[float] = None
    duration_min: Optional[int] = None
    target_time: Optional[str] = None


class StopResponse(BaseModel):
    """Response after stopping a discharge window."""

    success: bool
    detail: str
