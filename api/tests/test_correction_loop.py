"""Tests for the discharge correction loop lifecycle.

These are the highest-value tests: they validate the full loop from
start to stop, including power adjustments, notifications, and cleanup.
"""

import asyncio

import pytest

import mock_clock
from config import BATTERY_DN
from discharge.correction_loop import CorrectionLoop
from discharge.models import DischargeWindow

from tests.helpers import FakeAppState, FakeSession


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_loop(app_state, session, window, end_time):
    """Create a CorrectionLoop and register it in app_state (as the real scheduler does)."""
    loop = CorrectionLoop(app_state, session, BATTERY_DN, window, end_time)
    return loop


def _discharge_signals(session):
    """Return only discharge commands (mode=2) from the session's signal log."""
    return [
        s for s in session.signals_sent
        if any(sig["value"] == "2" for sig in s["signals"] if sig["id"] == "230320245")
    ]


def _stop_signals(session):
    """Return only stop commands (mode=0) from the session's signal log."""
    return [
        s for s in session.signals_sent
        if any(sig["value"] == "0" for sig in s["signals"] if sig["id"] == "230320245")
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCorrectionLoopCompletion:
    async def test_window_completes_by_time(self, app_state, mock_notifications, patch_sleep, sample_window):
        """When clock passes end_time, loop sends stop command and notifies."""
        mock_clock.set_time(22, 0)
        end_time = mock_clock.get_now().replace(hour=2, minute=0)
        # end_time is tomorrow 02:00
        from datetime import timedelta
        if end_time <= mock_clock.get_now():
            end_time += timedelta(days=1)

        session = FakeSession(soc_sequence=[80, 70, 60, 50, 40, 30, 20, 15, 10, 5])
        loop = _make_loop(app_state, session, sample_window, end_time)

        # Register in app_state as the scheduler would
        task = asyncio.create_task(loop.run())
        app_state.discharge_tasks[sample_window.id] = task

        await task

        # Should have sent a stop command
        stops = _stop_signals(session)
        assert len(stops) >= 1

        # Should have notified "Window ended"
        mock_notifications["stopped"].assert_called()
        call_args = mock_notifications["stopped"].call_args
        assert "Window ended" in str(call_args)

    async def test_target_soc_reached_early(self, app_state, mock_notifications, patch_sleep, sample_window):
        """When SOC drops to target, loop stops early with appropriate notification."""
        mock_clock.set_time(22, 0)
        from datetime import timedelta
        end_time = mock_clock.get_now() + timedelta(hours=4)

        # SOC drops to 0 (target) quickly
        session = FakeSession(soc_sequence=[80, 50, 20, 0])
        loop = _make_loop(app_state, session, sample_window, end_time)

        task = asyncio.create_task(loop.run())
        app_state.discharge_tasks[sample_window.id] = task

        await task

        stops = _stop_signals(session)
        assert len(stops) >= 1

        mock_notifications["stopped"].assert_called()
        call_args = mock_notifications["stopped"].call_args
        assert "Target SOC reached" in str(call_args)

    async def test_manual_cancellation(self, app_state, mock_notifications, patch_sleep, sample_window):
        """When task is cancelled, loop sends stop command and notifies 'Manually stopped'."""
        mock_clock.set_time(22, 0)
        from datetime import timedelta
        end_time = mock_clock.get_now() + timedelta(hours=4)

        # SOC stays high so the loop won't exit by target
        session = FakeSession(soc_sequence=[80, 79, 78, 77, 76, 75])
        loop = _make_loop(app_state, session, sample_window, end_time)

        task = asyncio.create_task(loop.run())
        app_state.discharge_tasks[sample_window.id] = task

        # Let it run a couple of iterations then cancel
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        stops = _stop_signals(session)
        assert len(stops) >= 1

        mock_notifications["stopped"].assert_called()
        call_args = mock_notifications["stopped"].call_args
        assert "Manually stopped" in str(call_args)


class TestCorrectionLoopPowerAdjustment:
    async def test_power_decreases_as_soc_drops(self, app_state, mock_notifications, patch_sleep, sample_window):
        """As SOC decreases, the discharge power sent to inverter should decrease."""
        mock_clock.set_time(22, 0)
        from datetime import timedelta
        end_time = mock_clock.get_now() + timedelta(hours=4)

        # SOC decreases: 80→60→40→20→0 (target reached)
        session = FakeSession(soc_sequence=[80, 60, 40, 20, 0])
        loop = _make_loop(app_state, session, sample_window, end_time)

        task = asyncio.create_task(loop.run())
        app_state.discharge_tasks[sample_window.id] = task
        await task

        discharges = _discharge_signals(session)
        # Extract power values from the signals
        powers = []
        for d in discharges:
            for sig in d["signals"]:
                if sig["id"] == "230320259":  # forced_power_kw
                    powers.append(float(sig["value"]))

        # With decreasing SOC, the required power should generally decrease
        # (less energy to discharge over remaining time)
        assert len(powers) >= 2
        # The first power should be >= last power (since SOC is dropping)
        assert powers[0] >= powers[-1]


class TestCorrectionLoopErrorHandling:
    async def test_soc_read_failure_continues(self, app_state, mock_notifications, patch_sleep, sample_window):
        """If SOC read fails, the loop should continue to next iteration."""
        mock_clock.set_time(22, 0)
        from datetime import timedelta
        end_time = mock_clock.get_now() + timedelta(minutes=5)  # Short window

        session = FakeSession(soc_sequence=[80])
        # Make call raise an exception after first read
        original_call = session.call
        call_count = 0

        async def failing_call(method, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Mock connection failure")
            return await original_call(method, *args, **kwargs)

        session.call = failing_call

        loop = _make_loop(app_state, session, sample_window, end_time)
        task = asyncio.create_task(loop.run())
        app_state.discharge_tasks[sample_window.id] = task
        await task

        # Loop should have completed (either by time or normally) despite the error
        assert task.done()


class TestCorrectionLoopStatusAndCleanup:
    async def test_status_updated_in_app_state(self, app_state, mock_notifications, patch_sleep, sample_window):
        """After each iteration, the status dict should be updated."""
        mock_clock.set_time(22, 0)
        from datetime import timedelta
        end_time = mock_clock.get_now() + timedelta(hours=4)

        # SOC goes to 0 after a few reads
        session = FakeSession(soc_sequence=[80, 60, 0])
        loop = _make_loop(app_state, session, sample_window, end_time)

        status_snapshots = []

        # Monkey-patch _update_status to capture intermediate states
        original_update = loop._update_status

        def capturing_update(soc, power_kw, minutes_left):
            original_update(soc, power_kw, minutes_left)
            status = app_state.discharge_statuses.get(sample_window.id)
            if status:
                status_snapshots.append(dict(status))

        loop._update_status = capturing_update

        task = asyncio.create_task(loop.run())
        app_state.discharge_tasks[sample_window.id] = task
        await task

        # Should have captured at least one status update
        assert len(status_snapshots) >= 1
        for snap in status_snapshots:
            assert snap["active"] is True
            assert snap["window_id"] == sample_window.id
            assert "current_soc" in snap

    async def test_cleanup_removes_from_app_state(self, app_state, mock_notifications, patch_sleep, sample_window):
        """After loop ends, window should be removed from statuses and tasks."""
        mock_clock.set_time(22, 0)
        from datetime import timedelta
        end_time = mock_clock.get_now() + timedelta(minutes=5)

        session = FakeSession(soc_sequence=[80, 0])
        loop = _make_loop(app_state, session, sample_window, end_time)

        task = asyncio.create_task(loop.run())
        app_state.discharge_tasks[sample_window.id] = task
        await task

        assert sample_window.id not in app_state.discharge_statuses
        assert sample_window.id not in app_state.discharge_tasks


class TestCorrectionLoopNotifications:
    async def test_notifications_sent_when_enabled(self, app_state, mock_notifications, patch_sleep):
        """With notify=True, update and stopped notifications are fired."""
        mock_clock.set_time(22, 0)
        from datetime import timedelta

        window = DischargeWindow(
            id="notif01", name="Notif Test", start_time="22:00",
            duration_minutes=240, target_soc=0, notify=True, enabled=True,
        )
        end_time = mock_clock.get_now() + timedelta(minutes=5)

        session = FakeSession(soc_sequence=[80, 0])
        loop = _make_loop(app_state, session, window, end_time)

        task = asyncio.create_task(loop.run())
        app_state.discharge_tasks[window.id] = task
        await task

        # At least one update or stopped notification
        total_calls = (
            mock_notifications["updated"].call_count
            + mock_notifications["stopped"].call_count
        )
        assert total_calls >= 1

    async def test_notifications_disabled(self, app_state, mock_notifications, patch_sleep):
        """With notify=False, no notification functions should be called."""
        mock_clock.set_time(22, 0)
        from datetime import timedelta

        window = DischargeWindow(
            id="quiet01", name="Quiet Window", start_time="22:00",
            duration_minutes=240, target_soc=0, notify=False, enabled=True,
        )
        end_time = mock_clock.get_now() + timedelta(minutes=5)

        session = FakeSession(soc_sequence=[80, 0])
        loop = _make_loop(app_state, session, window, end_time)

        task = asyncio.create_task(loop.run())
        app_state.discharge_tasks[window.id] = task
        await task

        mock_notifications["started"].assert_not_called()
        mock_notifications["updated"].assert_not_called()
        mock_notifications["stopped"].assert_not_called()
