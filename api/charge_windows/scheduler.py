"""Charge window scheduler.

Manages all configured charge windows: computes next start times,
launches ramp loops, handles config changes, and supports
mid-window resume on startup.
"""

import asyncio
import logging
from datetime import datetime, timedelta

import notifications
from mock_clock import get_now

from . import config_store
from .command_builder import build_restore_command
from .models import ChargeWindow, ChargeWindowStatus, StartResponse, StopResponse, build_status_dict
from .ramp_calculator import calc_charge_power
from .ramp_loop import RampLoop

logger = logging.getLogger("pv.charge_windows.scheduler")


class ChargeWindowScheduler:
    """Schedules and manages charge windows."""

    def __init__(self, app_state, session, battery_dn: str):
        self._app_state = app_state
        self._session = session
        self._battery_dn = battery_dn

    # ------------------------------------------------------------------
    # Main scheduler loop
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Main loop: sleeps until next window, starts ramp loops."""
        logger.info("Charge window scheduler started")

        # Check for mid-window resume on startup
        await self._check_mid_window_resume()

        while True:
            windows = config_store.load_windows()
            enabled = [w for w in windows if w.enabled]

            if not enabled:
                logger.info("No enabled charge windows, waiting for config change")
                await self._wait_for_change()
                continue

            # Find the earliest upcoming window
            now = get_now()
            next_window = None
            next_start = None
            next_end = None
            next_peak = None

            for w in enabled:
                start_dt, peak_dt, end_dt = self._compute_window_times(w, now)
                # Skip windows already running
                if w.id in self._app_state.charge_tasks:
                    continue
                if next_start is None or start_dt < next_start:
                    next_window = w
                    next_start = start_dt
                    next_end = end_dt
                    next_peak = peak_dt

            if next_window is None:
                logger.info("All enabled charge windows already running, waiting for config change")
                await self._wait_for_change()
                continue

            wait_seconds = (next_start - get_now()).total_seconds()
            if wait_seconds > 0:
                logger.info(
                    "Next charge window '%s' in %.0f min at %s",
                    next_window.name, wait_seconds / 60, next_start.isoformat(),
                )
                interrupted = await self._sleep_or_change(wait_seconds)
                if interrupted:
                    continue  # Config changed, re-evaluate

            # Time to start the window
            await self._launch_window(next_window, next_start, next_peak, next_end)

    # ------------------------------------------------------------------
    # Window time computation
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_window_times(
        window: ChargeWindow, now: datetime,
    ) -> tuple[datetime, datetime, datetime]:
        """Compute the current or next (start_dt, peak_dt, end_dt) for a window.

        Handles midnight-crossing windows correctly.
        """
        sh, sm = window.start_time.split(":")
        start_dt = now.replace(hour=int(sh), minute=int(sm), second=0, microsecond=0)

        # Compute peak and end relative to start
        ph, pm = window.peak_time.split(":")
        peak_dt = now.replace(hour=int(ph), minute=int(pm), second=0, microsecond=0)
        while peak_dt < start_dt:
            peak_dt += timedelta(days=1)

        eh, em = window.end_time.split(":")
        end_dt = now.replace(hour=int(eh), minute=int(em), second=0, microsecond=0)
        while end_dt <= peak_dt:
            end_dt += timedelta(days=1)

        if end_dt <= now:
            # Window fully past today — check if yesterday's instance is active
            duration = end_dt - start_dt
            peak_offset = peak_dt - start_dt
            yesterday_start = start_dt - timedelta(days=1)
            yesterday_peak = yesterday_start + peak_offset
            yesterday_end = yesterday_start + duration
            if yesterday_start <= now < yesterday_end:
                return yesterday_start, yesterday_peak, yesterday_end
            # Otherwise schedule for tomorrow
            start_dt += timedelta(days=1)
            peak_dt = start_dt + peak_offset
            end_dt = start_dt + duration

        return start_dt, peak_dt, end_dt

    # ------------------------------------------------------------------
    # Mid-window resume
    # ------------------------------------------------------------------

    async def _check_mid_window_resume(self) -> None:
        """On startup, resume any windows that should be active right now."""
        now = get_now()

        # Check for persisted active state files
        for window_id, start_time_iso, window in config_store.load_all_active():
            start_dt_saved = datetime.fromisoformat(start_time_iso)
            # Reconstruct peak and end from the saved start and window config
            _, peak_dt, end_dt = self._compute_window_times(window, start_dt_saved)
            # Adjust to use the saved start time
            peak_offset = peak_dt - start_dt_saved.replace(
                hour=int(window.start_time.split(":")[0]),
                minute=int(window.start_time.split(":")[1]),
                second=0, microsecond=0,
            )
            duration = end_dt - start_dt_saved.replace(
                hour=int(window.start_time.split(":")[0]),
                minute=int(window.start_time.split(":")[1]),
                second=0, microsecond=0,
            )
            actual_end = start_dt_saved + duration
            actual_peak = start_dt_saved + peak_offset

            if now >= actual_end:
                # Window expired during downtime — restore TOU
                logger.info(
                    "Charge window '%s' expired during downtime, restoring TOU mode",
                    window.name,
                )
                try:
                    await self._session.post_config_signals(
                        self._battery_dn, build_restore_command(),
                    )
                except Exception as exc:
                    logger.error("Failed to restore TOU on resume: %s", exc)
                config_store.clear_active(window_id)
            else:
                # Resume mid-window
                remaining = (actual_end - now).total_seconds() / 60
                logger.info(
                    "Resuming charge window '%s' (%.0f min remaining)",
                    window.name, remaining,
                )
                await self._launch_window(
                    window, start_dt_saved, actual_peak, actual_end,
                )

        # Also check for windows that should be active based on schedule
        for w in config_store.load_windows():
            if not w.enabled:
                continue
            if w.id in self._app_state.charge_tasks:
                continue
            start_dt, peak_dt, end_dt = self._compute_window_times(w, now)
            if start_dt <= now < end_dt:
                logger.info(
                    "Resuming mid-window '%s' (%.0f min remaining)",
                    w.name, (end_dt - now).total_seconds() / 60,
                )
                await self._launch_window(w, start_dt, peak_dt, end_dt)

    # ------------------------------------------------------------------
    # Launch / start / stop
    # ------------------------------------------------------------------

    async def _launch_window(
        self,
        window: ChargeWindow,
        start_dt: datetime,
        peak_dt: datetime,
        end_dt: datetime,
    ) -> int | None:
        """Start the ramp loop for a charge window.

        Returns initial power on success, None if skipped.
        """
        if window.id in self._app_state.charge_tasks:
            logger.info("Charge window '%s' already running, skipping", window.name)
            return None

        initial_power = calc_charge_power(
            get_now(), start_dt, peak_dt, end_dt,
            window.start_power, window.peak_power, window.end_power,
        )

        loop = RampLoop(
            self._app_state, self._session, self._battery_dn,
            window, start_dt, peak_dt, end_dt,
        )
        task = asyncio.create_task(loop.run())
        self._app_state.charge_tasks[window.id] = task

        # Persist for restart recovery
        config_store.save_active(window.id, start_dt.isoformat(), window)

        logger.info(
            "Charge window '%s' started: power=%dW, end=%s",
            window.name, initial_power, end_dt.isoformat(),
        )
        return initial_power

    async def start_window(self, window_id: str) -> StartResponse:
        """Manually start a specific charge window now."""
        window = config_store.get_window(window_id)
        if window is None:
            raise ValueError(f"Charge window {window_id} not found")

        if window_id in self._app_state.charge_tasks:
            task = self._app_state.charge_tasks[window_id]
            if not task.done():
                raise ValueError(f"Charge window '{window.name}' is already running")

        now = get_now()
        start_dt, peak_dt, end_dt = self._compute_window_times(window, now)
        # For manual start, use now as start time
        duration = end_dt - start_dt
        peak_offset = peak_dt - start_dt
        start_dt = now
        peak_dt = start_dt + peak_offset
        end_dt = start_dt + duration

        result = await self._launch_window(window, start_dt, peak_dt, end_dt)
        if result is None:
            raise ValueError(f"Charge window '{window.name}' could not be started")

        return StartResponse(
            success=True,
            window_id=window.id,
            window_name=window.name,
            initial_power_w=result,
            end_time=end_dt.isoformat(),
        )

    async def stop_window(self, window_id: str) -> StopResponse:
        """Stop a specific running charge window."""
        task = self._app_state.charge_tasks.get(window_id)
        if task is None or task.done():
            raise ValueError(f"Charge window {window_id} is not running")

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        config_store.clear_active(window_id)
        return StopResponse(success=True, detail="Charge window stopped, TOU mode restored")

    async def stop_all(self) -> None:
        """Stop all running charge windows."""
        for window_id in list(self._app_state.charge_tasks.keys()):
            try:
                await self.stop_window(window_id)
            except ValueError:
                pass

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self, window_id: str, window_name: str | None = None) -> ChargeWindowStatus:
        """Get the runtime status of a single window."""
        status = self._app_state.charge_statuses.get(window_id)
        if status and status.get("active"):
            return ChargeWindowStatus(**status)

        if window_name is None:
            window = config_store.get_window(window_id)
            window_name = window.name if window else "Unknown"
        return ChargeWindowStatus(window_id=window_id, window_name=window_name, active=False)

    def get_all_statuses(self) -> list[ChargeWindowStatus]:
        """Get runtime statuses for all configured windows."""
        return [
            self.get_status(w.id, w.name)
            for w in config_store.load_windows()
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _wait_for_change(self) -> None:
        """Wait until the charge_windows_changed event is set, then clear it."""
        await self._app_state.charge_windows_changed.wait()
        self._app_state.charge_windows_changed.clear()

    async def _sleep_or_change(self, seconds: float) -> bool:
        """Sleep for `seconds` or until config changes. Returns True if interrupted."""
        sleep_task = asyncio.create_task(asyncio.sleep(seconds))
        change_task = asyncio.create_task(self._app_state.charge_windows_changed.wait())

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
            self._app_state.charge_windows_changed.clear()
            return True

        return False
