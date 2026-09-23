"""When windows run: pure functions over timezone-aware datetimes.

A window runs every day from its start to its end on the Dublin wall clock, as the app shows them, like
the inverter's own TOU schedule. On a daylight-saving night it is an hour longer or shorter in real
time: a 23:35 to 02:00 window still ends at 02:00, before the TOU charge at 02:05. Run times are in UTC.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone

from mock_clock import TZ

from .models import DischargeWindow


@dataclass(frozen=True)
class Run:
    """One day's run of a window."""

    window: DischargeWindow
    start: datetime
    end: datetime


def _runs_around(window: DischargeWindow, now: datetime) -> Iterator[Run]:
    """Yesterday's, today's and tomorrow's runs: enough to cover a window that crosses midnight."""
    hour, minute = (int(part) for part in window.start_time.split(":"))
    today = now.astimezone(TZ).date()
    for offset in (-1, 0, 1):
        local_start = datetime.combine(today + timedelta(days=offset), time(hour, minute), tzinfo=TZ)
        # Adding to a zoneinfo datetime moves the wall clock; the UTC offset follows the new wall time
        local_end = local_start + timedelta(minutes=window.duration_minutes)
        yield Run(window, local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc))


def current_run(windows: list[DischargeWindow], now: datetime) -> Run | None:
    """The run of an enabled window that covers now. Windows never overlap, so there is at most one."""
    for window in windows:
        if window.enabled:
            for run in _runs_around(window, now):
                if run.start <= now < run.end:
                    return run
    return None


def next_change(windows: list[DischargeWindow], now: datetime) -> datetime | None:
    """The next moment an enabled window starts or ends."""
    moments = [
        moment
        for window in windows if window.enabled
        for run in _runs_around(window, now)
        for moment in (run.start, run.end)
        if moment > now
    ]
    return min(moments, default=None)


def minutes_of_day(window: DischargeWindow) -> set[int]:
    """Minutes of the day (0-1439) a window covers, wrapping past midnight. Used to refuse overlaps."""
    hour, minute = (int(part) for part in window.start_time.split(":"))
    start = hour * 60 + minute
    return {(start + i) % 1440 for i in range(window.duration_minutes)}


def end_time(window: DischargeWindow) -> str:
    """The window's end as HH:MM."""
    hour, minute = (int(part) for part in window.start_time.split(":"))
    end = (hour * 60 + minute + window.duration_minutes) % 1440
    return f"{end // 60:02d}:{end % 60:02d}"
