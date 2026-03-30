"""Multi-window discharge scheduler.

Manages all configured discharge windows: computes next start times,
launches correction loops, handles config changes, and supports
mid-window resume on startup.
"""

import asyncio
import logging
from datetime import datetime, timedelta

import notifications
from mock_clock import get_now

from . import config_store
from .command_builder import build_discharge_command
from .correction_loop import CorrectionLoop
from .models import DischargeWindow, StartResponse, StopResponse, WindowStatus
from .power_calculator import (
    BATTERY_REAL_CAPACITY_KWH,
    calc_discharge_power,
    remaining_energy_kwh,
)

logger = logging.getLogger("pv.discharge.scheduler")


class WindowScheduler:
    """Schedules and manages discharge windows."""

    def __init__(self, app_state, session, battery_id: str):
        self._app_state = app_state
        self._session = session
        self._battery_id = battery_id

    # ------------------------------------------------------------------
    # Main scheduler loop
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Main loop: sleeps until next window, starts correction loops."""
        logger.info("Window scheduler started")

        # Check for mid-window resume on startup
        await self._check_mid_window_resume()

        while True:
            windows = config_store.load_windows()
            enabled = [w for w in windows if w.enabled]

            if not enabled:
                logger.info("No enabled windows, waiting for config change")
                await self._wait_for_change()
                continue

            # Find the earliest upcoming window
            now = get_now()
            next_window = None
            next_start = None
            next_end = None

            for w in enabled:
                start_dt, end_dt = self._compute_window_times(w, now)
                # Skip windows already running
                if w.id in self._app_state.discharge_tasks:
                    continue
                if next_start is None or start_dt < next_start:
                    next_window = w
                    next_start = start_dt
                    next_end = end_dt

            if next_window is None:
                logger.info("All enabled windows already running, waiting for config change")
                await self._wait_for_change()
                continue

            wait_seconds = (next_start - get_now()).total_seconds()
            if wait_seconds > 0:
                logger.info(
                    "Next window '%s' in %.0f min at %s",
                    next_window.name, wait_seconds / 60, next_start.isoformat(),
                )
                interrupted = await self._sleep_or_change(wait_seconds)
                if interrupted:
                    continue  # Config changed, re-evaluate

            # Time to start the window
            await self._launch_window(next_window, next_end)

    # ------------------------------------------------------------------
    # Window time computation
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_window_times(window: DischargeWindow, now: datetime) -> tuple[datetime, datetime]:
        """Compute the next (start_dt, end_dt) for a window relative to now."""
        h, m = window.start_time.split(":")
        start_dt = now.replace(hour=int(h), minute=int(m), second=0, microsecond=0)

        # If start time has already passed today, check if window is still active
        end_dt = start_dt + timedelta(minutes=window.duration_minutes)
        if end_dt <= now:
            # Window is fully past today, schedule for tomorrow
            start_dt += timedelta(days=1)
            end_dt = start_dt + timedelta(minutes=window.duration_minutes)

        return start_dt, end_dt

    # ------------------------------------------------------------------
    # Mid-window resume
    # ------------------------------------------------------------------

    async def _check_mid_window_resume(self) -> None:
        """On startup, resume any windows that should be active right now."""
        now = get_now()
        for w in config_store.load_windows():
            if not w.enabled:
                continue
            h, m = w.start_time.split(":")
            start_dt = now.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
            end_dt = start_dt + timedelta(minutes=w.duration_minutes)

            # Handle midnight crossing: if end is before start, it started yesterday
            if end_dt < start_dt:
                # Window crosses midnight — check if we're in the post-midnight portion
                if now.hour < int(h):
                    start_dt -= timedelta(days=1)
                    end_dt = start_dt + timedelta(minutes=w.duration_minutes)

            if start_dt <= now < end_dt:
                logger.info(
                    "Resuming mid-window '%s' (%.0f min remaining)",
                    w.name, (end_dt - now).total_seconds() / 60,
                )
                await self._launch_window(w, end_dt)

    # ------------------------------------------------------------------
    # Launch / start / stop
    # ------------------------------------------------------------------

    async def _launch_window(self, window: DischargeWindow, end_time: datetime) -> None:
        """Start the correction loop for a window."""
        if window.id in self._app_state.discharge_tasks:
            logger.info("Window '%s' already running, skipping", window.name)
            return

        # Read SOC and send initial discharge command
        try:
            b = await self._session.call("get_battery_basic_stats", self._battery_id)
            soc = b.state_of_charge
        except Exception as exc:
            logger.error("Failed to read SOC for window '%s': %s", window.name, exc)
            return

        minutes_left = (end_time - get_now()).total_seconds() / 60
        power_kw = calc_discharge_power(soc, minutes_left, window.target_soc)

        if power_kw is None:
            logger.info(
                "Window '%s' not worthwhile: SOC=%.1f%%, target=%.0f%%",
                window.name, soc, window.target_soc,
            )
            return

        duration_min = int(min(minutes_left, 1440))
        try:
            await self._session.post_config_signals(
                self._battery_id, build_discharge_command(power_kw, duration_min),
            )
        except Exception as exc:
            logger.error("Failed to start discharge for window '%s': %s", window.name, exc)
            return

        # Store initial status
        self._app_state.discharge_statuses[window.id] = {
            "window_id": window.id,
            "window_name": window.name,
            "active": True,
            "current_soc": soc,
            "discharge_power_kw": round(power_kw, 3),
            "remaining_energy_kwh": round(remaining_energy_kwh(soc, window.target_soc), 3),
            "target_time": end_time.isoformat(),
            "minutes_remaining": round(minutes_left, 1),
            "hours_remaining": round(minutes_left / 60, 2),
            "last_adjustment": get_now().isoformat(),
        }

        # Start correction loop
        loop = CorrectionLoop(self._app_state, self._session, self._battery_id, window, end_time)
        task = asyncio.create_task(loop.run())
        self._app_state.discharge_tasks[window.id] = task

        if window.notify:
            notifications.notify_discharge_started(
                soc, power_kw, minutes_left, window_name=window.name,
            )

        logger.info(
            "Window '%s' started: SOC=%.1f%%, power=%.3f kW, end=%s",
            window.name, soc, power_kw, end_time.isoformat(),
        )

    async def start_window(self, window_id: str) -> StartResponse:
        """Manually start a specific window now."""
        window = config_store.get_window(window_id)
        if window is None:
            raise ValueError(f"Window {window_id} not found")

        if window_id in self._app_state.discharge_tasks:
            task = self._app_state.discharge_tasks[window_id]
            if not task.done():
                raise ValueError(f"Window '{window.name}' is already running")

        # Compute end time from now
        now = get_now()
        end_time = now + timedelta(minutes=window.duration_minutes)

        # Read SOC
        b = await self._session.call("get_battery_basic_stats", self._battery_id)
        soc = b.state_of_charge

        minutes_left = window.duration_minutes
        power_kw = calc_discharge_power(soc, minutes_left, window.target_soc)

        if power_kw is None:
            raise ValueError(
                f"Not worthwhile: SOC={soc}%, target={window.target_soc}%"
            )

        await self._launch_window(window, end_time)

        return StartResponse(
            success=True,
            window_id=window.id,
            window_name=window.name,
            initial_soc=soc,
            discharge_power_kw=round(power_kw, 3),
            remaining_energy_kwh=round(remaining_energy_kwh(soc, window.target_soc), 3),
            duration_min=window.duration_minutes,
            target_time=end_time.isoformat(),
        )

    async def stop_window(self, window_id: str) -> StopResponse:
        """Stop a specific running window."""
        task = self._app_state.discharge_tasks.get(window_id)
        if task is None or task.done():
            raise ValueError(f"Window {window_id} is not running")

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        return StopResponse(success=True, detail="Window stopped")

    async def stop_all(self) -> None:
        """Stop all running discharge windows."""
        for window_id in list(self._app_state.discharge_tasks.keys()):
            try:
                await self.stop_window(window_id)
            except ValueError:
                pass

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self, window_id: str) -> WindowStatus:
        """Get the runtime status of a single window."""
        status = self._app_state.discharge_statuses.get(window_id)
        if status and status.get("active"):
            return WindowStatus(**status)

        window = config_store.get_window(window_id)
        name = window.name if window else "Unknown"
        return WindowStatus(window_id=window_id, window_name=name, active=False)

    def get_all_statuses(self) -> list[WindowStatus]:
        """Get runtime statuses for all configured windows."""
        statuses = []
        for w in config_store.load_windows():
            statuses.append(self.get_status(w.id))
        return statuses

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _wait_for_change(self) -> None:
        """Wait until the windows_changed event is set, then clear it."""
        await self._app_state.windows_changed.wait()
        self._app_state.windows_changed.clear()

    async def _sleep_or_change(self, seconds: float) -> bool:
        """Sleep for `seconds` or until config changes. Returns True if interrupted."""
        sleep_task = asyncio.create_task(asyncio.sleep(seconds))
        change_task = asyncio.create_task(self._app_state.windows_changed.wait())

        done, pending = await asyncio.wait(
            {sleep_task, change_task}, return_when=asyncio.FIRST_COMPLETED,
        )

        for t in pending:
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass

        if change_task in done:
            self._app_state.windows_changed.clear()
            return True

        return False
