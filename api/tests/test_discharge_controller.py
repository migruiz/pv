"""The one rule, case by case: what the inverter is told after each tick of the clock or change to the windows."""

import asyncio
import threading

import pytest

import discharge.controller as controller_module

from discharge.controller import CORRECTION_INTERVAL, MAX_SLEEP, RETRY_INTERVAL, DischargeController
from discharge.models import WindowSettings
from discharge.store import WindowStore
from tests.discharge_fakes import Clock, FakeInverter, dublin, notified  # noqa: F401 (fixture)

STOP = {"forcible_charge_discharge_write": 0}


@pytest.fixture()
def store(tmp_path):
    return WindowStore(tmp_path / "discharge_windows.json")


@pytest.fixture()
def clock():
    return Clock(dublin(hour=12))


@pytest.fixture()
def inverter():
    return FakeInverter(soc=80)


class SettledController(DischargeController):
    """Waits for the background pushes after each step, so a test can assert them straight away."""

    async def check(self):
        error = await super().check()
        await self.settle()
        return error

    async def refresh(self, changed_window_id=None):
        error = await super().refresh(changed_window_id)
        await self.settle()
        return error

    async def delete(self, window_id):
        error = await super().delete(window_id)
        await self.settle()
        return error


@pytest.fixture()
def controller(store, inverter, clock, notified):
    return SettledController(store, inverter, clock=clock)


def settings(name="Night", start="22:00", minutes=240, target=0, notify=True, enabled=True, **changes):
    return WindowSettings(name=name, start_time=start, duration_minutes=minutes, target_soc=target,
                          notify=notify, enabled=enabled, **changes)


def power_w(inverter):
    return inverter.last["storage_forcible_discharge_power"]


def period_min(inverter):
    return inverter.last["storage_forced_charging_and_discharging_period"]


class TestSchedule:
    async def test_nothing_happens_before_the_window(self, controller, store, inverter, clock):
        store.add(settings())
        clock.at(21, 59)
        await controller.check()
        assert not inverter.discharges()

    async def test_starts_at_the_window_start_with_power_to_reach_the_target_by_the_end(
        self, controller, store, inverter, clock, notified,
    ):
        store.add(settings())
        clock.at(22, 0)
        await controller.check()
        # 80% of 4.8 kWh over 4 hours
        assert inverter.discharging()
        assert power_w(inverter) == 960
        assert period_min(inverter) == 240
        assert notified == [("started", "Night")]

    async def test_corrects_the_power_as_the_battery_drains(self, controller, store, inverter, clock, notified):
        store.add(settings())
        clock.at(22, 0)
        await controller.check()
        clock.at(23, 0)
        inverter.soc = 50
        await controller.check()
        # 50% of 4.8 kWh over the 3 hours left
        assert power_w(inverter) == 800
        assert period_min(inverter) == 180
        assert notified == [("started", "Night"), ("update", "Night")]

    async def test_power_is_capped_at_the_inverter_limit(self, controller, store, inverter, clock):
        store.add(settings(start="22:00", minutes=30))
        clock.at(22, 0)
        await controller.check()
        assert power_w(inverter) == 2500

    async def test_stops_when_the_window_ends(self, controller, store, inverter, clock, notified):
        store.add(settings())
        clock.at(22, 0)
        await controller.check()
        clock.advance(240)
        await controller.check()
        assert inverter.last == {"forcible_charge_discharge_write": 0}
        assert notified[-1] == ("stopped", "Night")
        assert not controller.state_of(store.load()[0]).discharging

    async def test_a_window_crossing_midnight_runs_after_midnight(self, controller, store, inverter, clock):
        store.add(settings(start="23:35", minutes=145))
        clock.at(1, 0)
        await controller.check()
        assert inverter.discharging()
        assert period_min(inverter) == 60

    async def test_disabled_windows_never_run(self, controller, store, inverter, clock):
        store.add(settings(enabled=False))
        clock.at(23, 0)
        await controller.check()
        assert not inverter.discharges()


class TestTarget:
    async def test_reaching_the_target_stops_and_the_window_is_done_for_the_day(
        self, controller, store, inverter, clock, notified,
    ):
        window = store.add(settings(target=5))
        clock.at(22, 0)
        await controller.check()
        clock.at(23, 0)
        inverter.soc = 5
        await controller.check()
        assert inverter.last == {"forcible_charge_discharge_write": 0}
        assert controller.state_of(window).target_reached

        # The battery climbs back above the target: still done for today
        commands = len(inverter.commands)
        clock.at(23, 30)
        inverter.soc = 20
        await controller.check()
        assert len(inverter.commands) == commands

        # Tomorrow night it runs again
        clock.advance(24 * 60 - 90)
        await controller.check()
        assert inverter.discharging()
        assert not controller.state_of(window).target_reached

    async def test_battery_already_at_the_target_does_nothing(self, controller, store, inverter, clock, notified):
        window = store.add(settings(target=5))
        inverter.soc = 4
        clock.at(22, 0)
        await controller.check()
        assert not inverter.discharges()
        assert notified == []
        assert controller.state_of(window).target_reached


class TestChanges:
    async def test_a_new_window_starting_now_discharges_straight_away(self, controller, store, inverter, clock):
        clock.at(14, 7)
        window = store.add(settings(name="Manual", start="14:07", minutes=60, target=50))
        await controller.refresh(window.id)
        assert inverter.discharging()
        assert controller.state_of(window).discharging

    async def test_a_new_target_applies_to_the_running_discharge(self, controller, store, inverter, clock, notified):
        window = store.add(settings())
        clock.at(22, 0)
        await controller.check()
        clock.at(23, 0)
        inverter.soc = 60
        store.replace(window.id, settings(target=50))
        await controller.refresh(window.id)
        # 10% of 4.8 kWh over the 3 hours left
        assert power_w(inverter) == 160
        assert notified == [("started", "Night"), ("update", "Night")]

    async def test_a_later_end_applies_to_the_running_discharge(self, controller, store, inverter, clock):
        window = store.add(settings())
        clock.at(23, 0)
        await controller.check()
        store.replace(window.id, settings(minutes=300))
        await controller.refresh(window.id)
        assert period_min(inverter) == 240

    async def test_an_end_moved_before_now_stops_the_discharge(self, controller, store, inverter, clock, notified):
        window = store.add(settings())
        clock.at(23, 0)
        await controller.check()
        store.replace(window.id, settings(minutes=30))
        await controller.refresh(window.id)
        assert inverter.last == {"forcible_charge_discharge_write": 0}
        assert notified[-1] == ("stopped", "Night")

    async def test_switching_a_window_off_stops_it_straight_away(self, controller, store, inverter, clock):
        window = store.add(settings())
        clock.at(23, 0)
        await controller.check()
        store.replace(window.id, settings(enabled=False))
        await controller.refresh(window.id)
        assert inverter.last == {"forcible_charge_discharge_write": 0}

    async def test_deleting_a_window_stops_it_straight_away(self, controller, store, inverter, clock):
        window = store.add(settings())
        clock.at(23, 0)
        await controller.check()
        store.delete(window.id)
        await controller.refresh(window.id)
        assert inverter.last == {"forcible_charge_discharge_write": 0}

    async def test_moving_a_window_onto_now_starts_it_and_off_again_stops_it(self, controller, store, inverter, clock):
        window = store.add(settings(start="22:00"))
        clock.at(15, 0)
        await controller.check()
        assert not inverter.discharges()
        store.replace(window.id, settings(start="14:30", minutes=120))
        await controller.refresh(window.id)
        assert inverter.discharging()
        store.replace(window.id, settings(start="22:00"))
        await controller.refresh(window.id)
        assert inverter.last == {"forcible_charge_discharge_write": 0}

    async def test_saving_a_window_that_reached_its_target_gives_it_a_fresh_go(self, controller, store, inverter, clock):
        window = store.add(settings(target=20))
        inverter.soc = 20
        clock.at(23, 0)
        await controller.check()
        assert controller.state_of(window).target_reached
        store.replace(window.id, settings(target=5))
        await controller.refresh(window.id)
        assert inverter.discharging()

    async def test_saving_another_window_does_not_restart_a_finished_one(self, controller, store, inverter, clock):
        window = store.add(settings(target=20))
        other = store.add(settings(name="Morning", start="05:00", minutes=60, enabled=False))
        inverter.soc = 30
        clock.at(22, 0)
        await controller.check()
        inverter.soc = 20
        clock.at(23, 0)
        await controller.check()
        commands = len(inverter.commands)
        inverter.soc = 30
        store.replace(other.id, settings(name="Morning", start="05:00", minutes=60, enabled=True))
        await controller.refresh(other.id)
        assert len(inverter.commands) == commands
        assert controller.state_of(window).target_reached


class TestRestartsAndFailures:
    async def test_a_restart_sends_one_stop_in_case_a_discharge_carried_on(self, controller, inverter):
        await controller.check()
        await controller.check()
        assert inverter.commands == [STOP]

    async def test_a_restart_with_the_battery_at_its_target_stops_the_carried_on_discharge(
        self, controller, store, inverter, clock,
    ):
        # Before the restart the inverter was told to discharge until 02:00; the battery reached 5% since
        window = store.add(settings(target=5))
        inverter.soc = 5
        clock.at(23, 0)
        await controller.check()
        assert inverter.commands == [STOP]
        assert controller.state_of(window).target_reached

    async def test_a_start_whose_reply_was_lost_is_stopped_when_its_window_goes(
        self, controller, store, inverter, clock,
    ):
        window = store.add(settings())
        clock.at(23, 0)
        inverter.reply_lost = True
        await controller.check()
        assert inverter.discharging()  # the inverter took it...
        assert not controller.state_of(window).discharging  # ...but the API cannot know
        inverter.reply_lost = False
        assert await controller.delete(window.id) is None
        assert inverter.last == STOP

    async def test_a_start_whose_reply_was_lost_keeps_its_window_if_the_stop_fails(
        self, controller, store, inverter, clock,
    ):
        window = store.add(settings())
        clock.at(23, 0)
        inverter.reply_lost = True
        await controller.check()
        inverter.reply_lost, inverter.write_fails = False, True
        assert await controller.delete(window.id) == "write failed"
        assert store.get(window.id) is not None

    async def test_a_window_whose_stop_fails_is_not_deleted(self, controller, store, inverter, clock):
        window = store.add(settings())
        clock.at(23, 0)
        await controller.check()
        inverter.write_fails = True
        assert await controller.delete(window.id) == "write failed"
        assert store.get(window.id) is not None
        assert controller.state_of(window).discharging
        inverter.write_fails = False
        assert await controller.delete(window.id) is None
        assert store.load() == []
        assert inverter.last == STOP

    async def test_after_a_restart_mid_window_it_carries_on(self, store, inverter, clock, notified):
        store.add(settings())
        clock.at(23, 0)
        restarted = DischargeController(store, inverter, clock=clock)
        await restarted.check()
        assert inverter.discharging()
        assert period_min(inverter) == 180

    async def test_no_reading_postpones_the_start_and_retries_soon(self, controller, store, inverter, clock):
        store.add(settings())
        clock.at(22, 0)
        inverter.reading_fails = True
        await controller.check()
        assert not inverter.discharges()
        assert controller.seconds_to_next_check() == RETRY_INTERVAL
        inverter.reading_fails = False
        clock.advance(0.5)
        await controller.check()
        assert inverter.discharging()

    async def test_a_failed_command_is_not_shown_as_discharging(self, controller, store, inverter, clock, notified):
        window = store.add(settings())
        clock.at(22, 0)
        inverter.write_fails = True
        await controller.check()
        assert not controller.state_of(window).discharging
        assert notified == []
        assert controller.seconds_to_next_check() == RETRY_INTERVAL

    async def test_a_failed_stop_is_retried(self, controller, store, inverter, clock):
        window = store.add(settings())
        clock.at(23, 0)
        await controller.check()
        inverter.write_fails = True
        store.replace(window.id, settings(enabled=False))
        await controller.refresh(window.id)
        # The inverter is still discharging, and the app says so
        assert controller.state_of(window).discharging
        inverter.write_fails = False
        await controller.check()
        assert inverter.last == {"forcible_charge_discharge_write": 0}
        assert not controller.state_of(window).discharging


class TestNotifications:
    async def test_no_notifications_for_a_quiet_window(self, controller, store, inverter, clock, notified):
        store.add(settings(notify=False))
        clock.at(22, 0)
        await controller.check()
        clock.advance(240)
        await controller.check()
        assert inverter.last == {"forcible_charge_discharge_write": 0}
        assert notified == []

    async def test_switching_notifications_off_mid_discharge_clears_the_phone(
        self, controller, store, inverter, clock, notified,
    ):
        window = store.add(settings())
        clock.at(22, 0)
        await controller.check()
        store.replace(window.id, settings(notify=False))
        await controller.refresh(window.id)
        assert notified == [("started", "Night"), ("stopped", "Night")]
        clock.advance(5)
        await controller.check()
        assert notified == [("started", "Night"), ("stopped", "Night")]
        store.replace(window.id, settings(notify=True))
        await controller.refresh(window.id)
        assert notified[-1] == ("started", "Night")


class TestWhenToCheck:
    async def test_sleeps_until_the_next_window_starts(self, controller, store, clock):
        store.add(settings())
        clock.at(21, 0)
        assert controller.seconds_to_next_check() == 3600

    async def test_corrects_every_few_minutes_while_discharging(self, controller, store, clock):
        store.add(settings())
        clock.at(22, 0)
        await controller.check()
        assert controller.seconds_to_next_check() == CORRECTION_INTERVAL

    async def test_wakes_exactly_when_a_finished_window_ends(self, controller, store, inverter, clock):
        store.add(settings(target=50))
        inverter.soc = 40
        clock.at(22, 0)
        await controller.check()
        clock.advance(239)
        assert controller.seconds_to_next_check() == 60

    async def test_a_start_that_passes_while_a_check_is_held_up_is_not_skipped(self, controller, store, clock):
        store.add(settings(name="Early", start="21:00", minutes=60, target=100))
        store.add(settings(start="22:00", minutes=60))
        clock.at(21, 59)
        clock.advance(55 / 60)
        await controller.check()  # reads the clock at 21:59:55...
        clock.advance(10 / 60)  # ...and is held up until 22:00:05
        assert controller.seconds_to_next_check() == 0.5  # not 23:00: the 22:00 start is still due

    async def test_without_windows_it_still_checks_hourly(self, controller):
        assert controller.seconds_to_next_check() == MAX_SLEEP


class TestLoop:
    async def test_checks_again_each_time_the_sleep_ends(self, controller, monkeypatch):
        checks = []

        async def check():
            checks.append(1)

        monkeypatch.setattr(controller, "check", check)
        monkeypatch.setattr(controller, "seconds_to_next_check", lambda: 0.01)
        task = asyncio.create_task(controller.run())
        await asyncio.sleep(0.1)
        task.cancel()
        assert len(checks) >= 3

    async def test_a_change_plans_the_sleep_again(self, controller, monkeypatch):
        checks = []
        delays = iter([60.0])

        async def check():
            checks.append(1)

        monkeypatch.setattr(controller, "check", check)
        monkeypatch.setattr(controller, "seconds_to_next_check", lambda: next(delays, 0.01))
        task = asyncio.create_task(controller.run())
        await asyncio.sleep(0.02)
        assert len(checks) == 1  # sleeping for 60 s
        await controller.refresh()  # its own check, then a new plan: 0.01 s
        await asyncio.sleep(0.1)
        task.cancel()
        assert len(checks) >= 3


class TestPushes:
    async def test_a_stalled_push_never_holds_up_a_stop(self, store, inverter, clock, notified, monkeypatch):
        controller = DischargeController(store, inverter, clock=clock)
        release = threading.Event()
        monkeypatch.setattr("notifications.notify_discharge_started", lambda *a, window_name=None: release.wait(5))
        window = store.add(settings())
        clock.at(22, 0)
        await asyncio.wait_for(controller.check(), timeout=2)  # the reply never waits for the push
        assert inverter.discharging()
        store.replace(window.id, settings(enabled=False))
        await asyncio.wait_for(controller.refresh(window.id), timeout=2)
        assert inverter.last == STOP  # sent while the "started" push still hangs
        release.set()
        await controller.settle()

    async def test_pushes_arrive_in_order_even_when_one_is_slow(self, store, inverter, clock, monkeypatch):
        controller = DischargeController(store, inverter, clock=clock)
        sent = []

        def slow_started(*a, window_name=None):
            threading.Event().wait(0.2)
            sent.append("started")

        monkeypatch.setattr("notifications.notify_discharge_started", slow_started)
        monkeypatch.setattr("notifications.notify_discharge_stopped", lambda *a, window_name=None: sent.append("stopped"))
        window = store.add(settings())
        clock.at(22, 0)
        await controller.check()
        store.replace(window.id, settings(enabled=False))
        await controller.refresh(window.id)
        await controller.settle()
        assert sent == ["started", "stopped"]


async def until(condition, timeout=2.0):
    """Wait for a condition set by another task."""
    async def poll():
        while not condition():
            await asyncio.sleep(0.01)
    await asyncio.wait_for(poll(), timeout)
