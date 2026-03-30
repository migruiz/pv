"""Background ramp loop for charge power adjustment.

Periodically recalculates the target max charge power along
a cosine bell curve and sends the updated signal to the inverter.
"""

import asyncio
import logging
from datetime import datetime

from config import BATTERY_DN, MOCK_MODE
from mock_clock import get_now

from .command_builder import build_power_update_command, build_restore_command, build_start_command
from .models import ChargeRampConfig, build_status_dict
from .ramp_calculator import calc_progress, calc_ramp_power

logger = logging.getLogger("pv.charge_ramp.loop")

RAMP_INTERVAL = 30 if MOCK_MODE else 300  # seconds


class RampLoop:
    """Adjusts max charge power along a bell curve for a single ramp session."""

    def __init__(
        self,
        app_state,
        session,
        battery_dn: str,
        config: ChargeRampConfig,
        start_time: datetime,
        end_time: datetime,
    ):
        self._app_state = app_state
        self._session = session
        self._battery_dn = battery_dn
        self._config = config
        self._start_time = start_time
        self._end_time = end_time

    async def run(self) -> None:
        """Main loop: adjusts power every RAMP_INTERVAL until done."""
        logger.info(
            "Ramp loop started (duration=%d min, %d→%d→%dW, end=%s)",
            self._config.duration_minutes,
            self._config.initial_power,
            self._config.top_power,
            self._config.final_power,
            self._end_time.isoformat(),
        )
        try:
            # Send initial start command (mode switch + initial power)
            initial_power = calc_ramp_power(
                0.0, self._config.initial_power, self._config.top_power, self._config.final_power,
            )
            await self._send_signals(build_start_command(initial_power))
            self._update_status(initial_power, 0.0)

            while True:
                await asyncio.sleep(RAMP_INTERVAL)

                elapsed = (get_now() - self._start_time).total_seconds() / 60
                progress = calc_progress(elapsed, self._config.duration_minutes)

                if progress >= 1.0:
                    logger.info("Ramp complete, restoring TOU mode")
                    await self._send_restore()
                    break

                power_w = calc_ramp_power(
                    progress, self._config.initial_power, self._config.top_power, self._config.final_power,
                )
                await self._send_signals(build_power_update_command(power_w))
                self._update_status(power_w, progress)
                logger.info("Ramp: progress=%.1f%%, power=%dW", progress * 100, power_w)

        except asyncio.CancelledError:
            logger.info("Ramp loop cancelled, restoring TOU mode")
            await self._send_restore()
            raise
        finally:
            self._cleanup()
            logger.info("Ramp loop ended")

    async def _send_signals(self, signals: list[dict]) -> None:
        """Send signals to the inverter."""
        try:
            await self._session.post_config_signals(self._battery_dn, signals)
        except Exception as exc:
            logger.error("Failed to send ramp signals: %s", exc)

    async def _send_restore(self) -> None:
        """Send restore command (TOU + AC charge + 2500W + TOU windows)."""
        try:
            await self._session.post_config_signals(self._battery_dn, build_restore_command())
        except Exception as exc:
            logger.error("Failed to restore TOU mode: %s", exc)

    def _update_status(self, power_w: int, progress: float) -> None:
        """Update the shared status dict."""
        elapsed = (get_now() - self._start_time).total_seconds() / 60
        self._app_state.charge_ramp_status = build_status_dict(
            power_w=power_w,
            progress=progress,
            elapsed_minutes=elapsed,
            total_minutes=self._config.duration_minutes,
            start_time_iso=self._start_time.isoformat(),
            end_time_iso=self._end_time.isoformat(),
            now_iso=get_now().isoformat(),
        )

    def _cleanup(self) -> None:
        """Remove status and task reference."""
        self._app_state.charge_ramp_status = None
        self._app_state.charge_ramp_task = None
