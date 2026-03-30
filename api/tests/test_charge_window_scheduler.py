"""Tests for charge window scheduler."""

from datetime import timedelta

import pytest

import mock_clock
from charge_windows import config_store
from charge_windows.models import ChargeWindow, ChargeWindowCreate
from charge_windows.scheduler import ChargeWindowScheduler
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


# ---------------------------------------------------------------------------
# Window Time Computation
# ---------------------------------------------------------------------------

class TestComputeWindowTimes:
    def test_future_today(self):
        mock_clock.set_time(8, 0)
        now = mock_clock.get_now()
        window = _make_window(start_time="10:00", peak_time="12:00", end_time="14:00")

        start_dt, peak_dt, end_dt = ChargeWindowScheduler._compute_window_times(window, now)

        assert start_dt.hour == 10
        assert peak_dt.hour == 12
        assert end_dt.hour == 14
        assert start_dt.day == now.day

    def test_past_today_schedules_tomorrow(self):
        mock_clock.set_time(16, 0)
        now = mock_clock.get_now()
        window = _make_window(start_time="10:00", peak_time="12:00", end_time="14:00")

        start_dt, peak_dt, end_dt = ChargeWindowScheduler._compute_window_times(window, now)

        assert start_dt.day == now.day + 1
        assert start_dt.hour == 10

    def test_midnight_crossing(self):
        mock_clock.set_time(20, 0)
        now = mock_clock.get_now()
        window = _make_window(start_time="22:00", peak_time="00:00", end_time="02:00")

        start_dt, peak_dt, end_dt = ChargeWindowScheduler._compute_window_times(window, now)

        assert start_dt.hour == 22
        assert start_dt.day == now.day
        assert peak_dt.hour == 0
        assert peak_dt.day == now.day + 1
        assert end_dt.hour == 2
        assert end_dt.day == now.day + 1


# ---------------------------------------------------------------------------
# Manual Start / Stop
# ---------------------------------------------------------------------------

class TestManualStartStop:
    async def test_start_window(self, app_state, charge_config_path, patch_sleep, mock_notifications):
        mock_clock.set_time(10, 0)
        session = FakeSession()
        scheduler = ChargeWindowScheduler(app_state, session, BATTERY_DN)

        window = _make_window()
        config_store.save_windows([window])

        result = await scheduler.start_window(window.id)
        assert result.success is True
        assert result.initial_power_w is not None
        assert window.id in app_state.charge_tasks

    async def test_start_already_running_raises(self, app_state, charge_config_path, patch_sleep, mock_notifications):
        mock_clock.set_time(10, 0)
        session = FakeSession()
        scheduler = ChargeWindowScheduler(app_state, session, BATTERY_DN)

        window = _make_window()
        config_store.save_windows([window])

        await scheduler.start_window(window.id)
        with pytest.raises(ValueError, match="already running"):
            await scheduler.start_window(window.id)

    async def test_stop_window(self, app_state, charge_config_path, patch_sleep, mock_notifications):
        mock_clock.set_time(10, 0)
        session = FakeSession()
        scheduler = ChargeWindowScheduler(app_state, session, BATTERY_DN)

        window = _make_window()
        config_store.save_windows([window])

        await scheduler.start_window(window.id)
        result = await scheduler.stop_window(window.id)
        assert result.success is True

    async def test_stop_not_running_raises(self, app_state, charge_config_path, mock_notifications):
        session = FakeSession()
        scheduler = ChargeWindowScheduler(app_state, session, BATTERY_DN)

        with pytest.raises(ValueError, match="not running"):
            await scheduler.stop_window("nonexist")


# ---------------------------------------------------------------------------
# Mid-Window Resume
# ---------------------------------------------------------------------------

class TestMidWindowResume:
    async def test_resume_active_window(self, app_state, charge_config_path, patch_sleep, mock_notifications):
        mock_clock.set_time(12, 0)
        session = FakeSession()
        scheduler = ChargeWindowScheduler(app_state, session, BATTERY_DN)

        window = _make_window()
        config_store.save_windows([window])

        # Scheduler should detect that the window is mid-flight (10:00-14:00, now is 12:00)
        await scheduler._check_mid_window_resume()

        assert window.id in app_state.charge_tasks

    async def test_no_resume_outside_window(self, app_state, charge_config_path, mock_notifications):
        mock_clock.set_time(16, 0)
        session = FakeSession()
        scheduler = ChargeWindowScheduler(app_state, session, BATTERY_DN)

        window = _make_window()
        config_store.save_windows([window])

        await scheduler._check_mid_window_resume()

        assert window.id not in app_state.charge_tasks


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

class TestSchedulerStatus:
    async def test_get_status_inactive(self, app_state, charge_config_path):
        session = FakeSession()
        scheduler = ChargeWindowScheduler(app_state, session, BATTERY_DN)

        window = _make_window()
        config_store.save_windows([window])

        status = scheduler.get_status(window.id)
        assert status.active is False
        assert status.window_name == "Test Charge"

    async def test_get_all_statuses(self, app_state, charge_config_path):
        session = FakeSession()
        scheduler = ChargeWindowScheduler(app_state, session, BATTERY_DN)

        w1 = _make_window(id="c1", name="First")
        w2 = _make_window(id="c2", name="Second", start_time="15:00", peak_time="16:00", end_time="17:00")
        config_store.save_windows([w1, w2])

        statuses = scheduler.get_all_statuses()
        assert len(statuses) == 2
        names = {s.window_name for s in statuses}
        assert names == {"First", "Second"}
