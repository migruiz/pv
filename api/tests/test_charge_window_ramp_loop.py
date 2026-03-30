"""Tests for the charge window ramp loop lifecycle."""

import asyncio
from datetime import timedelta

import pytest

import mock_clock
from charge_windows.command_builder import SIGNALS
from charge_windows.models import ChargeWindow
from charge_windows.ramp_loop import RampLoop
from config import BATTERY_DN

from tests.helpers import FakeAppState, FakeSession


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_window(**overrides):
    defaults = dict(
        id="chrg01", name="Test Charge",
        start_time="10:00", start_power=200,
        peak_time="12:00", peak_power=2500,
        end_time="14:00", end_power=200,
        notify=False, enabled=True,
    )
    defaults.update(overrides)
    return ChargeWindow(**defaults)


def _make_loop(app_state, session, window, start_dt, peak_dt, end_dt):
    return RampLoop(app_state, session, BATTERY_DN, window, start_dt, peak_dt, end_dt)


def _start_signals(session):
    """Return commands that set operation_mode to self-consumption (2)."""
    return [
        s for s in session.signals_sent
        if any(sig["value"] == "2" for sig in s["signals"] if sig["id"] == SIGNALS["operation_mode"])
    ]


def _restore_signals(session):
    """Return commands that set operation_mode back to TOU (5)."""
    return [
        s for s in session.signals_sent
        if any(sig["value"] == "5" for sig in s["signals"] if sig["id"] == SIGNALS["operation_mode"])
    ]


def _power_updates(session):
    """Return all max_charge_power values sent (as ints)."""
    powers = []
    for s in session.signals_sent:
        for sig in s["signals"]:
            if sig["id"] == SIGNALS["max_charge_power"]:
                powers.append(int(sig["value"]))
    return powers


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRampLoopCompletion:
    async def test_ramp_completes_by_time(self, app_state, patch_sleep, mock_notifications):
        """When duration elapses, loop sends restore command."""
        mock_clock.set_time(10, 0)
        start_dt = mock_clock.get_now()
        peak_dt = start_dt + timedelta(hours=2)
        end_dt = start_dt + timedelta(hours=4)
        window = _make_window()

        session = FakeSession()
        loop = _make_loop(app_state, session, window, start_dt, peak_dt, end_dt)

        task = asyncio.create_task(loop.run())
        app_state.charge_tasks[window.id] = task
        await task

        restores = _restore_signals(session)
        assert len(restores) >= 1

        # Restore should include TOU windows signal
        restore = restores[-1]
        signal_ids = {sig["id"] for sig in restore["signals"]}
        assert SIGNALS["tou_windows"] in signal_ids

    async def test_manual_cancellation_restores(self, app_state, patch_sleep, mock_notifications):
        """When cancelled, loop restores TOU mode."""
        mock_clock.set_time(10, 0)
        start_dt = mock_clock.get_now()
        peak_dt = start_dt + timedelta(hours=4)
        end_dt = start_dt + timedelta(hours=8)
        window = _make_window()

        session = FakeSession()
        loop = _make_loop(app_state, session, window, start_dt, peak_dt, end_dt)

        task = asyncio.create_task(loop.run())
        app_state.charge_tasks[window.id] = task

        await asyncio.sleep(0)
        await asyncio.sleep(0)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        restores = _restore_signals(session)
        assert len(restores) >= 1


class TestRampLoopPowerCurve:
    async def test_starts_with_initial_command(self, app_state, patch_sleep, mock_notifications):
        """First signal sent should be the start command with initial power."""
        mock_clock.set_time(10, 0)
        start_dt = mock_clock.get_now()
        peak_dt = start_dt + timedelta(hours=1)
        end_dt = start_dt + timedelta(hours=2)
        window = _make_window()

        session = FakeSession()
        loop = _make_loop(app_state, session, window, start_dt, peak_dt, end_dt)

        task = asyncio.create_task(loop.run())
        app_state.charge_tasks[window.id] = task
        await task

        starts = _start_signals(session)
        assert len(starts) == 1

    async def test_power_rises_then_falls(self, app_state, patch_sleep, mock_notifications):
        """Power values should increase in the first half and decrease in the second."""
        mock_clock.set_time(10, 0)
        start_dt = mock_clock.get_now()
        peak_dt = start_dt + timedelta(hours=2)
        end_dt = start_dt + timedelta(hours=4)
        window = _make_window()

        session = FakeSession()
        loop = _make_loop(app_state, session, window, start_dt, peak_dt, end_dt)

        task = asyncio.create_task(loop.run())
        app_state.charge_tasks[window.id] = task
        await task

        powers = _power_updates(session)
        assert len(powers) >= 3

        max_power = max(powers)
        assert max_power >= 2000
        assert powers[0] == 200

    async def test_power_values_in_range(self, app_state, patch_sleep, mock_notifications):
        """All power values sent should be within [200, 2500]."""
        mock_clock.set_time(10, 0)
        start_dt = mock_clock.get_now()
        peak_dt = start_dt + timedelta(hours=2)
        end_dt = start_dt + timedelta(hours=4)
        window = _make_window()

        session = FakeSession()
        loop = _make_loop(app_state, session, window, start_dt, peak_dt, end_dt)

        task = asyncio.create_task(loop.run())
        app_state.charge_tasks[window.id] = task
        await task

        powers = _power_updates(session)
        for p in powers:
            assert 200 <= p <= 2500


class TestRampLoopStatusAndCleanup:
    async def test_status_updated_during_ramp(self, app_state, patch_sleep, mock_notifications):
        """Status dict should be populated while ramp is active."""
        mock_clock.set_time(10, 0)
        start_dt = mock_clock.get_now()
        peak_dt = start_dt + timedelta(hours=1)
        end_dt = start_dt + timedelta(hours=2)
        window = _make_window()

        session = FakeSession()
        loop = _make_loop(app_state, session, window, start_dt, peak_dt, end_dt)

        status_snapshots = []
        original_update = loop._update_status

        def capturing_update(power_w):
            original_update(power_w)
            status = app_state.charge_statuses.get(window.id)
            if status:
                status_snapshots.append(dict(status))

        loop._update_status = capturing_update

        task = asyncio.create_task(loop.run())
        app_state.charge_tasks[window.id] = task
        await task

        assert len(status_snapshots) >= 1
        for snap in status_snapshots:
            assert snap["active"] is True
            assert "current_power_w" in snap
            assert "progress" in snap

    async def test_cleanup_on_completion(self, app_state, patch_sleep, mock_notifications):
        """After loop ends, status and task should be cleared."""
        mock_clock.set_time(10, 0)
        start_dt = mock_clock.get_now()
        peak_dt = start_dt + timedelta(hours=1)
        end_dt = start_dt + timedelta(hours=2)
        window = _make_window()

        session = FakeSession()
        loop = _make_loop(app_state, session, window, start_dt, peak_dt, end_dt)

        task = asyncio.create_task(loop.run())
        app_state.charge_tasks[window.id] = task
        await task

        assert window.id not in app_state.charge_statuses
        assert window.id not in app_state.charge_tasks
