"""Multi-window discharge scheduler.

Manages all configured discharge windows: computes next start times,
launches correction loops, handles config changes, and supports
mid-window resume on startup.
"""

import asyncio
import logging
from datetime import datetime, timedelta

import notifications
from config import MOCK_MODE
from mock_clock import get_now

from . import config_store
from .command_builder import build_discharge_command
from .correction_loop import CorrectionLoop
from .models import DischargeWindow, StartResponse, StopResponse, WindowStatus, build_status_dict
from .power_calculator import calc_discharge_power, remaining_energy_kwh

logger = logging.getLogger("pv.discharge.scheduler")

RETRY_INTERVAL = 30 if MOCK_MODE else 300  # seconds between attempts when a window fails to start


class WindowScheduler:
    """Schedules and manages discharge windows."""

    def __init__(self, app_state, session, battery_id: str):
        self._app_state = app_state
        self._session = session
        self._battery_id = battery_id
        # Start time of the occurrence each window was last launched for, so a
        # finished or stopped occurrence is not launched again
        self._launched: dict[str, datetime] = {}

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
                # Once an occurrence is under way (running, or already
                # launched and since finished or stopped), plan the next day's
                if start_dt <= now and (
                    w.id in self._app_state.discharge_tasks
                    or self._launched.get(w.id) == start_dt
                ):
                    start_dt += timedelta(days=1)
                    end_dt += timedelta(days=1)
                if next_start is None or start_dt < next_start:
                    next_window = w
                    next_start = start_dt
                    next_end = end_dt

            wait_seconds = (next_start - get_now()).total_seconds()
            if wait_seconds > 0:
                logger.info(
                    "Next window '%s' in %.0f min at %s",
                    next_window.name, wait_seconds / 60, next_start.isoformat(),
                )
                # Re-evaluate on waking: config may have changed, or the
                # window may have been started by hand in the meantime
                await self._sleep_or_change(wait_seconds)
                continue

            # Time to start the window
            if await self._launch_window(next_window, next_end) is None:
                # SOC read or command failed, or SOC already at target: retry later
                await self._sleep_or_change(RETRY_INTERVAL)
            else:
                self._launched[next_window.id] = next_start

    # ------------------------------------------------------------------
    # Window time computation
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_window_times(window: DischargeWindow, now: datetime) -> tuple[datetime, datetime]:
        """Compute the current or next (start_dt, end_dt) for a window.

        Handles midnight-crossing windows: if now is in the post-midnight
        portion (e.g., 01:00 for a 22:00-02:00 window), returns yesterday's
        start and today's end so the window is recognised as active.
        """
        h, m = window.start_time.split(":")
        start_dt = now.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
        end_dt = start_dt + timedelta(minutes=window.duration_minutes)

        # Yesterday's instance may cross midnight and still be active now
        yesterday_start = start_dt - timedelta(days=1)
        yesterday_end = end_dt - timedelta(days=1)
        if yesterday_start <= now < yesterday_end:
            return yesterday_start, yesterday_end

        if end_dt <= now:
            # Window fully past today — schedule for tomorrow
            start_dt += timedelta(days=1)
            end_dt += timedelta(days=1)

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
            start_dt, end_dt = self._compute_window_times(w, now)
            if start_dt <= now < end_dt:
                logger.info(
                    "Resuming mid-window '%s' (%.0f min remaining)",
                    w.name, (end_dt - now).total_seconds() / 60,
                )
                if await self._launch_window(w, end_dt) is not None:
                    self._launched[w.id] = start_dt

    # ------------------------------------------------------------------
    # Launch / start / stop
    # ------------------------------------------------------------------

    async def _launch_window(
        self, window: DischargeWindow, end_time: datetime,
    ) -> tuple[float, float, float] | None:
        """Start the correction loop for a window.

        Returns (soc, power_kw, minutes_left) on success, None if skipped.
        """
        if window.id in self._app_state.discharge_tasks:
            logger.info("Window '%s' already running, skipping", window.name)
            return None

        try:
            b = await self._session.call("get_battery_basic_stats", self._battery_id)
            soc = b.state_of_charge
        except Exception as exc:
            logger.error("Failed to read SOC for window '%s': %s", window.name, exc)
            return None

        minutes_left = (end_time - get_now()).total_seconds() / 60
        power_kw = calc_discharge_power(soc, minutes_left, window.target_soc)

        if power_kw is None:
            logger.info(
                "Window '%s' not worthwhile: SOC=%.1f%%, target=%.0f%%",
                window.name, soc, window.target_soc,
            )
            return None

        duration_min = int(min(minutes_left, 1440))
        try:
            await self._session.post_config_signals(
                self._battery_id, build_discharge_command(power_kw, duration_min),
            )
        except Exception as exc:
            logger.error("Failed to start discharge for window '%s': %s", window.name, exc)
            return None

        self._app_state.discharge_statuses[window.id] = build_status_dict(
            window_id=window.id,
            window_name=window.name,
            soc=soc,
            power_kw=power_kw,
            minutes_left=minutes_left,
            energy_kwh=remaining_energy_kwh(soc, window.target_soc),
            end_time_iso=end_time.isoformat(),
            now_iso=get_now().isoformat(),
        )

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
        return soc, power_kw, minutes_left

    async def start_window(self, window_id: str) -> StartResponse:
        """Manually start a specific window now."""
        window = config_store.get_window(window_id)
        if window is None:
            raise ValueError(f"Window {window_id} not found")

        if window_id in self._app_state.discharge_tasks:
            task = self._app_state.discharge_tasks[window_id]
            if not task.done():
                raise ValueError(f"Window '{window.name}' is already running")

        end_time = get_now() + timedelta(minutes=window.duration_minutes)
        result = await self._launch_window(window, end_time)

        if result is None:
            raise ValueError(
                f"Not worthwhile: SOC at or below target {window.target_soc}%"
            )

        soc, power_kw, minutes_left = result
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

    def get_status(self, window_id: str, window_name: str | None = None) -> WindowStatus:
        """Get the runtime status of a single window."""
        status = self._app_state.discharge_statuses.get(window_id)
        if status and status.get("active"):
            return WindowStatus(**status)

        if window_name is None:
            window = config_store.get_window(window_id)
            window_name = window.name if window else "Unknown"
        return WindowStatus(window_id=window_id, window_name=window_name, active=False)

    def get_all_statuses(self) -> list[WindowStatus]:
        """Get runtime statuses for all configured windows (single file read)."""
        return [
            self.get_status(w.id, w.name)
            for w in config_store.load_windows()
        ]

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
