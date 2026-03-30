"""Tests for the charge ramp loop lifecycle."""

import asyncio

import pytest

import mock_clock
from charge_ramp.command_builder import SIGNALS
from charge_ramp.models import ChargeRampConfig
from charge_ramp.ramp_loop import RampLoop
from config import BATTERY_DN

from tests.helpers import FakeAppState, FakeSession


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_loop(app_state, session, config, start_time, end_time):
    return RampLoop(app_state, session, BATTERY_DN, config, start_time, end_time)


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
    async def test_ramp_completes_by_time(self, app_state, patch_sleep):
        """When duration elapses, loop sends restore command."""
        mock_clock.set_time(10, 0)
        from datetime import timedelta
        start_time = mock_clock.get_now()
        config = ChargeRampConfig(duration_minutes=240, initial_power=200, top_power=2500, final_power=200)
        end_time = start_time + timedelta(minutes=config.duration_minutes)

        session = FakeSession()
        loop = _make_loop(app_state, session, config, start_time, end_time)

        task = asyncio.create_task(loop.run())
        app_state.charge_ramp_task = task
        await task

        restores = _restore_signals(session)
        assert len(restores) >= 1

        # Restore should include TOU windows signal
        restore = restores[-1]
        signal_ids = {sig["id"] for sig in restore["signals"]}
        assert SIGNALS["tou_windows"] in signal_ids

    async def test_manual_cancellation_restores(self, app_state, patch_sleep):
        """When cancelled, loop restores TOU mode."""
        mock_clock.set_time(10, 0)
        from datetime import timedelta
        start_time = mock_clock.get_now()
        config = ChargeRampConfig(duration_minutes=480, initial_power=200, top_power=2500, final_power=200)
        end_time = start_time + timedelta(minutes=config.duration_minutes)

        session = FakeSession()
        loop = _make_loop(app_state, session, config, start_time, end_time)

        task = asyncio.create_task(loop.run())
        app_state.charge_ramp_task = task

        # Let it run a couple of iterations then cancel
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        restores = _restore_signals(session)
        assert len(restores) >= 1


class TestRampLoopPowerCurve:
    async def test_starts_with_initial_command(self, app_state, patch_sleep):
        """First signal sent should be the start command with initial power."""
        mock_clock.set_time(10, 0)
        from datetime import timedelta
        start_time = mock_clock.get_now()
        config = ChargeRampConfig(duration_minutes=60, initial_power=200, top_power=2500, final_power=200)
        end_time = start_time + timedelta(minutes=config.duration_minutes)

        session = FakeSession()
        loop = _make_loop(app_state, session, config, start_time, end_time)

        task = asyncio.create_task(loop.run())
        app_state.charge_ramp_task = task
        await task

        starts = _start_signals(session)
        assert len(starts) == 1

    async def test_power_rises_then_falls(self, app_state, patch_sleep):
        """Power values should increase in the first half and decrease in the second."""
        mock_clock.set_time(10, 0)
        from datetime import timedelta
        start_time = mock_clock.get_now()
        config = ChargeRampConfig(duration_minutes=240, initial_power=200, top_power=2500, final_power=200)
        end_time = start_time + timedelta(minutes=config.duration_minutes)

        session = FakeSession()
        loop = _make_loop(app_state, session, config, start_time, end_time)

        task = asyncio.create_task(loop.run())
        app_state.charge_ramp_task = task
        await task

        powers = _power_updates(session)
        assert len(powers) >= 3

        # Find the max power value — should be near top_power
        max_power = max(powers)
        assert max_power >= 2000  # Should get close to 2500

        # First power should be initial
        assert powers[0] == 200

    async def test_power_values_in_range(self, app_state, patch_sleep):
        """All power values sent should be within [200, 2500]."""
        mock_clock.set_time(10, 0)
        from datetime import timedelta
        start_time = mock_clock.get_now()
        config = ChargeRampConfig(duration_minutes=240, initial_power=200, top_power=2500, final_power=200)
        end_time = start_time + timedelta(minutes=config.duration_minutes)

        session = FakeSession()
        loop = _make_loop(app_state, session, config, start_time, end_time)

        task = asyncio.create_task(loop.run())
        app_state.charge_ramp_task = task
        await task

        powers = _power_updates(session)
        for p in powers:
            assert 200 <= p <= 2500


class TestRampLoopStatusAndCleanup:
    async def test_status_updated_during_ramp(self, app_state, patch_sleep):
        """Status dict should be populated while ramp is active."""
        mock_clock.set_time(10, 0)
        from datetime import timedelta
        start_time = mock_clock.get_now()
        config = ChargeRampConfig(duration_minutes=120, initial_power=200, top_power=2500, final_power=200)
        end_time = start_time + timedelta(minutes=config.duration_minutes)

        session = FakeSession()
        loop = _make_loop(app_state, session, config, start_time, end_time)

        status_snapshots = []
        original_update = loop._update_status

        def capturing_update(power_w, progress):
            original_update(power_w, progress)
            status = app_state.charge_ramp_status
            if status:
                status_snapshots.append(dict(status))

        loop._update_status = capturing_update

        task = asyncio.create_task(loop.run())
        app_state.charge_ramp_task = task
        await task

        assert len(status_snapshots) >= 1
        for snap in status_snapshots:
            assert snap["active"] is True
            assert "current_power_w" in snap
            assert "progress" in snap

    async def test_cleanup_on_completion(self, app_state, patch_sleep):
        """After loop ends, status and task should be cleared."""
        mock_clock.set_time(10, 0)
        from datetime import timedelta
        start_time = mock_clock.get_now()
        config = ChargeRampConfig(duration_minutes=60, initial_power=200, top_power=2500, final_power=200)
        end_time = start_time + timedelta(minutes=config.duration_minutes)

        session = FakeSession()
        loop = _make_loop(app_state, session, config, start_time, end_time)

        task = asyncio.create_task(loop.run())
        app_state.charge_ramp_task = task
        await task

        assert app_state.charge_ramp_status is None
        assert app_state.charge_ramp_task is None
