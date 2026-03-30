"""Background ramp loop for charge window power adjustment.

Periodically recalculates the target max charge power along
a cosine bell curve and sends the updated signal to the inverter.
"""

import asyncio
import logging
from datetime import datetime

from config import MOCK_MODE
from mock_clock import get_now

import notifications
from .command_builder import build_power_update_command, build_restore_command, build_start_command
from .models import ChargeWindow, build_status_dict
from .ramp_calculator import calc_charge_power, calc_progress

logger = logging.getLogger("pv.charge_windows.loop")

RAMP_INTERVAL = 30 if MOCK_MODE else 300  # seconds


class RampLoop:
    """Adjusts max charge power along a bell curve for a single charge window."""

    def __init__(
        self,
        app_state,
        session,
        battery_dn: str,
        window: ChargeWindow,
        start_dt: datetime,
        peak_dt: datetime,
        end_dt: datetime,
    ):
        self._app_state = app_state
        self._session = session
        self._battery_dn = battery_dn
        self._window = window
        self._start_dt = start_dt
        self._peak_dt = peak_dt
        self._end_dt = end_dt

    async def run(self) -> None:
        """Main loop: adjusts power every RAMP_INTERVAL until done."""
        w = self._window
        logger.info(
            "Charge window '%s' ramp started (%s→%s→%s, %dW→%dW→%dW)",
            w.name, w.start_time, w.peak_time, w.end_time,
            w.start_power, w.peak_power, w.end_power,
        )
        try:
            # Send initial start command (mode switch + initial power)
            initial_power = calc_charge_power(
                get_now(), self._start_dt, self._peak_dt, self._end_dt,
                w.start_power, w.peak_power, w.end_power,
            )
            await self._send_signals(build_start_command(initial_power))
            self._update_status(initial_power)

            if w.notify:
                notifications.notify_charge_started(initial_power, window_name=w.name)

            while True:
                await asyncio.sleep(RAMP_INTERVAL)

                now = get_now()
                progress = calc_progress(now, self._start_dt, self._end_dt)

                if progress >= 1.0:
                    logger.info("Charge window '%s' complete, restoring TOU mode", w.name)
                    await self._send_restore()
                    if w.notify:
                        notifications.notify_charge_stopped("completed", window_name=w.name)
                    break

                power_w = calc_charge_power(
                    now, self._start_dt, self._peak_dt, self._end_dt,
                    w.start_power, w.peak_power, w.end_power,
                )
                await self._send_signals(build_power_update_command(power_w))
                self._update_status(power_w)

                if w.notify:
                    remaining = (self._end_dt - now).total_seconds() / 60
                    notifications.notify_charge_update(power_w, remaining, window_name=w.name)

                logger.info(
                    "Charge '%s': progress=%.1f%%, power=%dW",
                    w.name, progress * 100, power_w,
                )

        except asyncio.CancelledError:
            logger.info("Charge window '%s' cancelled, restoring TOU mode", w.name)
            await self._send_restore()
            if w.notify:
                notifications.notify_charge_stopped("stopped", window_name=w.name)
            raise
        finally:
            self._cleanup()
            logger.info("Charge window '%s' ramp loop ended", w.name)

    async def _send_signals(self, signals: list[dict]) -> None:
        """Send signals to the inverter."""
        try:
            await self._session.post_config_signals(self._battery_dn, signals)
        except Exception as exc:
            logger.error("Failed to send charge signals: %s", exc)

    async def _send_restore(self) -> None:
        """Send restore command (TOU + AC charge + 2500W + TOU windows)."""
        try:
            await self._session.post_config_signals(self._battery_dn, build_restore_command())
        except Exception as exc:
            logger.error("Failed to restore TOU mode: %s", exc)

    def _update_status(self, power_w: int) -> None:
        """Update the shared status dict."""
        now = get_now()
        elapsed = (now - self._start_dt).total_seconds() / 60
        progress = calc_progress(now, self._start_dt, self._end_dt)
        self._app_state.charge_statuses[self._window.id] = build_status_dict(
            window_id=self._window.id,
            window_name=self._window.name,
            power_w=power_w,
            progress=progress,
            elapsed_minutes=elapsed,
            total_minutes=self._window.duration_minutes,
            end_time_iso=self._end_dt.isoformat(),
            now_iso=now.isoformat(),
        )

    def _cleanup(self) -> None:
        """Remove status and task reference."""
        self._app_state.charge_statuses.pop(self._window.id, None)
        self._app_state.charge_tasks.pop(self._window.id, None)
