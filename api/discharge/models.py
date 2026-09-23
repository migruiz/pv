"""A discharge window's settings, and the live state shown next to them."""

import re

from pydantic import BaseModel, Field, field_validator

_HH_MM = re.compile(r"([01]\d|2[0-3]):[0-5]\d")


class WindowSettings(BaseModel):
    """What the app edits. A window runs every day from start_time for duration_minutes."""

    name: str = Field(min_length=1, max_length=60)
    start_time: str
    duration_minutes: int = Field(ge=1, le=1440)
    target_soc: float = Field(ge=0, le=100)
    notify: bool = True
    enabled: bool = True

    @field_validator("start_time")
    @classmethod
    def _valid_time(cls, value: str) -> str:
        if not _HH_MM.fullmatch(value):
            raise ValueError("must be HH:MM between 00:00 and 23:59")
        return value


class DischargeWindow(WindowSettings):
    id: str


class WindowState(BaseModel):
    """What the controller is doing with a window right now."""

    discharging: bool = False
    target_reached: bool = False  # reached its target during the current run: done until tomorrow
    power_kw: float | None = None
    soc: float | None = None  # battery % at the last power correction
    minutes_remaining: float | None = None
    ends_at: str | None = None


class WindowView(DischargeWindow):
    state: WindowState
    # Only on a save's reply: the window is saved, but the inverter did not respond yet (retried shortly)
    warning: str | None = None
