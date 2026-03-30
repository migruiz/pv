"""Charge ramp lifecycle manager.

Handles start/stop/status and restart recovery for the charge ramp feature.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from config import BATTERY_DN
from mock_clock import get_now

from . import config_store
from .command_builder import build_restore_command
from .models import ChargeRampConfig, ChargeRampStatus, StartResponse, StopResponse
from .ramp_calculator import calc_ramp_power
from .ramp_loop import RampLoop

logger = logging.getLogger("pv.charge_ramp.manager")


class ChargeRampManager:
    """Manages the charge ramp lifecycle."""

    def __init__(self, app_state, session, battery_dn: str):
        self._app_state = app_state
        self._session = session
        self._battery_dn = battery_dn

    def _is_running(self) -> bool:
        task = self._app_state.charge_ramp_task
        return task is not None and not task.done()

    async def start(self) -> StartResponse:
        """Start the charge ramp with current config."""
        if self._is_running():
            raise ValueError("Charge ramp is already running")

        # Conflict guard: don't run alongside discharge windows
        for task in self._app_state.discharge_tasks.values():
            if not task.done():
                raise ValueError("Cannot start charge ramp while a discharge window is running")

        config = config_store.load_config()
        start_time = get_now()
        end_time = start_time + timedelta(minutes=config.duration_minutes)

        initial_power = calc_ramp_power(
            0.0, config.initial_power, config.top_power, config.final_power,
        )

        loop = RampLoop(
            self._app_state, self._session, self._battery_dn,
            config, start_time, end_time,
        )
        task = asyncio.create_task(loop.run())
        self._app_state.charge_ramp_task = task

        # Persist for restart recovery
        config_store.save_active(start_time.isoformat(), config)

        return StartResponse(
            success=True,
            initial_power_w=initial_power,
            duration_minutes=config.duration_minutes,
            end_time=end_time.isoformat(),
        )

    async def stop(self) -> StopResponse:
        """Stop the running charge ramp."""
        task = self._app_state.charge_ramp_task
        if task is None or task.done():
            raise ValueError("Charge ramp is not running")

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        config_store.clear_active()
        return StopResponse(success=True, detail="Charge ramp stopped, TOU mode restored")

    def get_status(self) -> ChargeRampStatus:
        """Get current ramp status."""
        status = self._app_state.charge_ramp_status
        if status and status.get("active"):
            return ChargeRampStatus(**status)
        return ChargeRampStatus(active=False)

    async def check_resume(self) -> None:
        """On startup, resume a ramp that was active when API restarted."""
        active = config_store.load_active()
        if active is None:
            return

        start_time_iso, config = active
        start_time = datetime.fromisoformat(start_time_iso)
        end_time = start_time + timedelta(minutes=config.duration_minutes)

        if get_now() >= end_time:
            # Ramp would have completed — restore safe state
            logger.info("Ramp expired during downtime, restoring TOU mode")
            try:
                await self._session.post_config_signals(
                    self._battery_dn, build_restore_command(),
                )
            except Exception as exc:
                logger.error("Failed to restore TOU on resume: %s", exc)
            config_store.clear_active()
            return

        # Resume mid-ramp
        remaining = (end_time - get_now()).total_seconds() / 60
        logger.info("Resuming charge ramp (%.0f min remaining)", remaining)

        loop = RampLoop(
            self._app_state, self._session, self._battery_dn,
            config, start_time, end_time,
        )
        task = asyncio.create_task(loop.run())
        self._app_state.charge_ramp_task = task
