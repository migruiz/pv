"""Tests for the discharge window scheduler.

Covers window time computation, mid-window resume, manual start/stop,
and config change interrupts.
"""

import asyncio
from datetime import timedelta

import pytest

import mock_clock
from config import BATTERY_DN
from discharge import config_store
from discharge.models import DischargeWindow
from discharge.scheduler import WindowScheduler

from tests.helpers import FakeAppState, FakeSession


# ---------------------------------------------------------------------------
# Window time computation (static method, no async needed)
# ---------------------------------------------------------------------------

class TestComputeWindowTimes:
    def test_future_today(self):
        """Window at 22:00, now=20:00 → starts today 22:00."""
        mock_clock.set_time(20, 0)
        now = mock_clock.get_now()
        window = DischargeWindow(
            id="t1", name="T", start_time="22:00", duration_minutes=240, target_soc=0,
        )
        start, end = WindowScheduler._compute_window_times(window, now)
        assert start.hour == 22
        assert start.minute == 0
        assert start.day == now.day
        assert end == start + timedelta(minutes=240)

    def test_past_today_schedules_tomorrow(self):
        """Window at 14:00, now=16:00 → schedules for tomorrow 14:00."""
        mock_clock.set_time(16, 0)
        now = mock_clock.get_now()
        window = DischargeWindow(
            id="t2", name="T", start_time="14:00", duration_minutes=60, target_soc=0,
        )
        start, end = WindowScheduler._compute_window_times(window, now)
        assert start.hour == 14
        assert start.day == now.day + 1

    def test_midnight_crossing_active_pre_midnight(self):
        """Window 22:00-02:00, now=23:00 → today start, recognized as active."""
        mock_clock.set_time(23, 0)
        now = mock_clock.get_now()
        window = DischargeWindow(
            id="t3", name="T", start_time="22:00", duration_minutes=240, target_soc=0,
        )
        start, end = WindowScheduler._compute_window_times(window, now)
        assert start.hour == 22
        assert start.day == now.day
        assert end == start + timedelta(minutes=240)
        # Now should be within the window
        assert start <= now < end

    def test_same_day_window(self):
        """Window at 08:00 for 120min, now=06:00 → today 08:00-10:00."""
        mock_clock.set_time(6, 0)
        now = mock_clock.get_now()
        window = DischargeWindow(
            id="t4", name="T", start_time="08:00", duration_minutes=120, target_soc=0,
        )
        start, end = WindowScheduler._compute_window_times(window, now)
        assert start.hour == 8
        assert start.day == now.day
        assert end.hour == 10

    def test_window_just_ended(self):
        """Window 08:00-10:00, now=10:30 → tomorrow 08:00."""
        mock_clock.set_time(10, 30)
        now = mock_clock.get_now()
        window = DischargeWindow(
            id="t5", name="T", start_time="08:00", duration_minutes=120, target_soc=0,
        )
        start, end = WindowScheduler._compute_window_times(window, now)
        assert start.hour == 8
        assert start.day == now.day + 1


# ---------------------------------------------------------------------------
# Manual start / stop
# ---------------------------------------------------------------------------

class TestManualStartStop:
    async def test_start_window(self, app_state, config_path, mock_notifications, patch_sleep):
        """Manual start returns StartResponse with correct fields."""
        mock_clock.set_time(12, 0)
        session = FakeSession(soc_sequence=[80])
        scheduler = WindowScheduler(app_state, session, BATTERY_DN)

        # Create a window via config store
        from discharge.models import DischargeWindowCreate
        create = DischargeWindowCreate(
            name="Manual Test", start_time="22:00", duration_minutes=60, target_soc=10,
        )
        window = config_store.add_window(create)

        response = await scheduler.start_window(window.id)
        assert response.success is True
        assert response.window_id == window.id
        assert response.window_name == "Manual Test"
        assert response.initial_soc == 80
        assert response.discharge_power_kw > 0
        assert response.duration_min == 60

        # Clean up the running task
        task = app_state.discharge_tasks.get(window.id)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def test_start_already_running_raises(self, app_state, config_path, mock_notifications, patch_sleep):
        """Starting an already-running window raises ValueError."""
        mock_clock.set_time(12, 0)
        session = FakeSession(soc_sequence=[80, 79, 78])
        scheduler = WindowScheduler(app_state, session, BATTERY_DN)

        from discharge.models import DischargeWindowCreate
        create = DischargeWindowCreate(
            name="Dup Test", start_time="22:00", duration_minutes=60, target_soc=10,
        )
        window = config_store.add_window(create)

        await scheduler.start_window(window.id)

        with pytest.raises(ValueError, match="already running"):
            await scheduler.start_window(window.id)

        # Clean up
        task = app_state.discharge_tasks.get(window.id)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def test_start_soc_at_target_raises(self, app_state, config_path, mock_notifications, patch_sleep):
        """Starting when SOC is already at target raises ValueError."""
        mock_clock.set_time(12, 0)
        session = FakeSession(soc_sequence=[10])  # SOC at target
        scheduler = WindowScheduler(app_state, session, BATTERY_DN)

        from discharge.models import DischargeWindowCreate
        create = DischargeWindowCreate(
            name="Low SOC", start_time="22:00", duration_minutes=60, target_soc=10,
        )
        window = config_store.add_window(create)

        with pytest.raises(ValueError, match="Not worthwhile"):
            await scheduler.start_window(window.id)

    async def test_stop_window(self, app_state, config_path, mock_notifications, patch_sleep):
        """Stopping a running window returns StopResponse."""
        mock_clock.set_time(12, 0)
        session = FakeSession(soc_sequence=[80, 79, 78, 77])
        scheduler = WindowScheduler(app_state, session, BATTERY_DN)

        from discharge.models import DischargeWindowCreate
        create = DischargeWindowCreate(
            name="Stop Test", start_time="22:00", duration_minutes=60, target_soc=0,
        )
        window = config_store.add_window(create)
        await scheduler.start_window(window.id)

        response = await scheduler.stop_window(window.id)
        assert response.success is True
        assert "stopped" in response.detail.lower()

    async def test_stop_not_running_raises(self, app_state, config_path, mock_notifications, patch_sleep):
        """Stopping a window that isn't running raises ValueError."""
        session = FakeSession()
        scheduler = WindowScheduler(app_state, session, BATTERY_DN)

        with pytest.raises(ValueError, match="is not running"):
            await scheduler.stop_window("nonexistent")


# ---------------------------------------------------------------------------
# Mid-window resume
# ---------------------------------------------------------------------------

class TestMidWindowResume:
    async def test_resume_active_window(self, app_state, config_path, mock_notifications, patch_sleep):
        """On startup during an active window, the scheduler should resume it."""
        # Set time to 23:00 — inside the default Night Export window (22:00-02:00)
        mock_clock.set_time(23, 0)
        session = FakeSession(soc_sequence=[60, 50, 40, 30, 20, 10, 0])

        # Save a window that should be active now
        config_store.save_windows([
            DischargeWindow(
                id="resume1", name="Night Export", start_time="22:00",
                duration_minutes=240, target_soc=0, notify=True, enabled=True,
            ),
        ])

        scheduler = WindowScheduler(app_state, session, BATTERY_DN)
        await scheduler._check_mid_window_resume()

        # Should have launched the window
        assert "resume1" in app_state.discharge_tasks

        # Clean up
        task = app_state.discharge_tasks["resume1"]
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def test_no_resume_outside_window(self, app_state, config_path, mock_notifications, patch_sleep):
        """Outside all windows, mid-window resume should not launch anything."""
        mock_clock.set_time(12, 0)  # Noon — outside 22:00-02:00
        session = FakeSession(soc_sequence=[80])

        config_store.save_windows([
            DischargeWindow(
                id="noresume", name="Night Export", start_time="22:00",
                duration_minutes=240, target_soc=0, notify=True, enabled=True,
            ),
        ])

        scheduler = WindowScheduler(app_state, session, BATTERY_DN)
        await scheduler._check_mid_window_resume()

        assert "noresume" not in app_state.discharge_tasks


# ---------------------------------------------------------------------------
# Status queries
# ---------------------------------------------------------------------------

class TestSchedulerStatus:
    async def test_get_status_active(self, app_state, config_path, mock_notifications, patch_sleep):
        """get_status for an active window returns active=True with data."""
        mock_clock.set_time(12, 0)
        session = FakeSession(soc_sequence=[80, 79])
        scheduler = WindowScheduler(app_state, session, BATTERY_DN)

        from discharge.models import DischargeWindowCreate
        create = DischargeWindowCreate(
            name="Status Test", start_time="22:00", duration_minutes=60, target_soc=0,
        )
        window = config_store.add_window(create)
        await scheduler.start_window(window.id)

        status = scheduler.get_status(window.id)
        assert status.active is True
        assert status.current_soc is not None
        assert status.discharge_power_kw > 0

        # Clean up
        task = app_state.discharge_tasks.get(window.id)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    def test_get_status_inactive(self, app_state, config_path):
        """get_status for a non-running window returns active=False."""
        session = FakeSession()
        scheduler = WindowScheduler(app_state, session, BATTERY_DN)

        config_store.save_windows([
            DischargeWindow(
                id="inactive1", name="Inactive", start_time="08:00",
                duration_minutes=60, target_soc=10,
            ),
        ])

        status = scheduler.get_status("inactive1")
        assert status.active is False
        assert status.window_id == "inactive1"


# ---------------------------------------------------------------------------
# Sleep-or-change interrupt
# ---------------------------------------------------------------------------

class TestSleepOrChange:
    async def test_config_change_interrupts_sleep(self, app_state):
        """Setting windows_changed event should interrupt _sleep_or_change."""
        session = FakeSession()
        scheduler = WindowScheduler(app_state, session, BATTERY_DN)

        # Schedule the event to fire soon
        async def fire_event():
            await asyncio.sleep(0.01)
            app_state.windows_changed.set()

        asyncio.create_task(fire_event())
        interrupted = await scheduler._sleep_or_change(10)
        assert interrupted is True
