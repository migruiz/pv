"""Background correction loop for a single discharge window.

Periodically re-reads battery SOC and adjusts discharge power
to hit the target SOC by the window's end time.
"""

import asyncio
import logging
from datetime import datetime

import notifications
from config import MOCK_MODE
from mock_clock import get_now

from .command_builder import build_discharge_command, build_stop_command
from .models import DischargeWindow, build_status_dict
from .power_calculator import calc_discharge_power, remaining_energy_kwh

logger = logging.getLogger("pv.discharge.loop")

CORRECTION_INTERVAL = 30 if MOCK_MODE else 300  # seconds


class CorrectionLoop:
    """Self-correcting discharge loop for a single window."""

    def __init__(self, app_state, session, battery_id: str, window: DischargeWindow, end_time: datetime):
        self._app_state = app_state
        self._session = session
        self._battery_id = battery_id
        self._window = window
        self._end_time = end_time

    async def run(self) -> None:
        """Main loop: adjusts power every CORRECTION_INTERVAL until done."""
        logger.info(
            "Correction loop started for window '%s' (target SOC=%.0f%%, end=%s)",
            self._window.name, self._window.target_soc, self._end_time.isoformat(),
        )
        try:
            while True:
                await asyncio.sleep(CORRECTION_INTERVAL)

                minutes_left = self._minutes_until_end()

                if minutes_left <= 1:
                    logger.info("Window '%s': end time reached, stopping", self._window.name)
                    await self._send_stop()
                    if self._window.notify:
                        notifications.notify_discharge_stopped(
                            "Window ended", window_name=self._window.name,
                        )
                    break

                soc = await self._read_soc()
                if soc is None:
                    continue

                power_kw = calc_discharge_power(soc, minutes_left, self._window.target_soc)

                if power_kw is None:
                    logger.info(
                        "Window '%s': SOC %.1f%% at or below target %.0f%%, stopping",
                        self._window.name, soc, self._window.target_soc,
                    )
                    await self._send_stop()
                    if self._window.notify:
                        notifications.notify_discharge_stopped(
                            f"Target SOC reached ({soc:.1f}%)",
                            window_name=self._window.name,
                        )
                    break

                await self._send_discharge(power_kw, minutes_left)
                self._update_status(soc, power_kw, minutes_left)

                if self._window.notify:
                    notifications.notify_discharge_update(
                        soc, power_kw, minutes_left, window_name=self._window.name,
                    )

        except asyncio.CancelledError:
            logger.info("Correction loop cancelled for window '%s'", self._window.name)
            await self._send_stop()
            if self._window.notify:
                notifications.notify_discharge_stopped(
                    "Manually stopped", window_name=self._window.name,
                )
            raise
        finally:
            self._cleanup()
            logger.info("Correction loop ended for window '%s'", self._window.name)

    def _minutes_until_end(self) -> float:
        """Minutes remaining until the window's end time."""
        return (self._end_time - get_now()).total_seconds() / 60

    async def _read_soc(self) -> float | None:
        """Read current SOC from the battery, or None on failure."""
        try:
            b = await self._session.call("get_battery_basic_stats", self._battery_id)
            return b.state_of_charge
        except Exception as exc:
            logger.error("Failed to read SOC: %s", exc)
            return None

    async def _send_discharge(self, power_kw: float, minutes_left: float) -> None:
        """Send adjusted discharge command to the inverter."""
        duration_min = int(min(minutes_left, 1440))
        try:
            await self._session.post_config_signals(
                self._battery_id, build_discharge_command(power_kw, duration_min),
            )
            logger.info(
                "Window '%s': SOC read, power=%.3f kW, duration=%d min, end in %.0f min",
                self._window.name, power_kw, duration_min, minutes_left,
            )
        except Exception as exc:
            logger.error("Failed to send discharge command: %s", exc)

    async def _send_stop(self) -> None:
        """Send stop command to the inverter."""
        try:
            await self._session.post_config_signals(
                self._battery_id, build_stop_command(),
            )
        except Exception as exc:
            logger.error("Failed to stop discharge: %s", exc)

    def _update_status(self, soc: float, power_kw: float, minutes_left: float) -> None:
        """Update the shared status dict for this window."""
        self._app_state.discharge_statuses[self._window.id] = build_status_dict(
            window_id=self._window.id,
            window_name=self._window.name,
            soc=soc,
            power_kw=power_kw,
            minutes_left=minutes_left,
            energy_kwh=remaining_energy_kwh(soc, self._window.target_soc),
            end_time_iso=self._end_time.isoformat(),
            now_iso=get_now().isoformat(),
        )

    def _cleanup(self) -> None:
        """Remove this window's status and task reference."""
        self._app_state.discharge_statuses.pop(self._window.id, None)
        self._app_state.discharge_tasks.pop(self._window.id, None)
