"""The daytime target: the mode switch (self-consumption below the target, TOU at it), the discharge windows'
priority, TOU from 23:00 to 08:00 for the night charge."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from daytime_target.controller import DaytimeTargetController, spare_solar_to_battery
from daytime_target.router import router
from daytime_target.store import TargetStore
from discharge.models import WindowSettings
from discharge.store import WindowStore
from tests.discharge_fakes import Clock, FakeInverter, dublin

HEADERS = {"X-API-Key": "test-key"}
SELF_CONSUMPTION = 2
TO_BATTERY = {"storage_working_mode_settings": SELF_CONSUMPTION}
TO_GRID = {"storage_working_mode_settings": 5, "storage_excess_pv_energy_use_in_tou": 0}  # TOU, exporting
SETTING_TO_GRID = {"storage_excess_pv_energy_use_in_tou": 0}  # already in TOU, set to charge


@pytest.fixture()
def clock():
    return Clock(dublin(hour=8))


@pytest.fixture()
def inverter():
    return FakeInverter(soc=70)


@pytest.fixture()
def windows(tmp_path):
    return WindowStore(tmp_path / "windows.json")


@pytest.fixture()
def controller(tmp_path, windows, inverter, clock):
    return DaytimeTargetController(TargetStore(tmp_path / "target.json"), windows, inverter, clock=clock)


def add_window(windows, start="09:00", minutes=120, enabled=True):
    return windows.add(WindowSettings(name="Morning Export", start_time=start, duration_minutes=minutes,
                                      target_soc=50, enabled=enabled))


# ---------------------------------------------------------------------------
# The rule on its own
# ---------------------------------------------------------------------------

class TestRule:
    def test_zero_sends_all_spare_solar_to_the_grid(self):
        assert spare_solar_to_battery(soc=10, target=0, to_battery_now=True, fresh=True) is False

    def test_hundred_puts_all_spare_solar_into_the_battery(self):
        assert spare_solar_to_battery(soc=100, target=100, to_battery_now=False, fresh=False) is True

    def test_at_or_above_the_target_goes_to_the_grid(self):
        assert spare_solar_to_battery(soc=80, target=80, to_battery_now=True, fresh=False) is False
        assert spare_solar_to_battery(soc=95, target=80, to_battery_now=True, fresh=True) is False

    def test_five_below_the_target_goes_back_into_the_battery(self):
        assert spare_solar_to_battery(soc=75, target=80, to_battery_now=False, fresh=False) is True

    def test_within_the_gap_nothing_changes(self):
        for soc in (76, 79):
            assert spare_solar_to_battery(soc=soc, target=80, to_battery_now=False, fresh=False) is False
            assert spare_solar_to_battery(soc=soc, target=80, to_battery_now=True, fresh=False) is True

    def test_right_after_a_save_the_gap_is_ignored(self):
        assert spare_solar_to_battery(soc=79, target=80, to_battery_now=False, fresh=True) is True

    def test_a_target_below_the_gap_charges_again_only_when_empty(self):
        assert spare_solar_to_battery(soc=1, target=4, to_battery_now=False, fresh=False) is False
        assert spare_solar_to_battery(soc=0, target=4, to_battery_now=False, fresh=False) is True


# ---------------------------------------------------------------------------
# The controller
# ---------------------------------------------------------------------------

async def test_without_a_saved_target_spare_solar_stays_on_the_grid(controller, inverter):
    assert controller.store.load() == 0
    assert await controller.check() is None
    assert inverter.commands == []


async def test_target_zero_puts_self_consumption_back_to_tou(controller, inverter):
    inverter.operation_mode = SELF_CONSUMPTION
    await controller.check()
    assert inverter.commands == [TO_GRID]
    assert not inverter.spare_solar_to_battery


async def test_tou_s_own_charge_setting_is_put_back_to_the_grid(controller, inverter):
    inverter.tou_excess_to_battery = True  # how the API before this change left it
    await controller.check()
    assert inverter.commands == [SETTING_TO_GRID]


async def test_saving_a_target_above_the_battery_switches_to_self_consumption_before_the_reply(controller, inverter):
    assert await controller.save(80) is None
    assert inverter.commands == [TO_BATTERY]
    assert inverter.operation_mode == SELF_CONSUMPTION
    assert controller.store.load() == 80


async def test_below_the_target_tou_set_to_charge_still_switches_to_self_consumption(controller, inverter):
    inverter.tou_excess_to_battery = True  # 3 Nov 2026: the inverter ignored this
    await controller.save(80)
    assert inverter.commands == [TO_BATTERY]


async def test_a_day_with_the_target_at_80(controller, inverter):
    inverter.soc = 100  # after the night charge
    await controller.save(80)
    assert inverter.commands == []  # above the target: TOU, spare solar to the grid

    inverter.soc = 76
    await controller.check()
    assert inverter.commands == []  # within the gap: the battery runs the house

    inverter.soc = 75
    await controller.check()
    assert inverter.commands == [TO_BATTERY]

    inverter.soc = 79
    await controller.check()
    assert inverter.commands == [TO_BATTERY]  # still filling

    inverter.soc = 80
    await controller.check()
    assert inverter.commands == [TO_BATTERY, TO_GRID]
    assert inverter.operation_mode == 5


async def test_saving_within_the_gap_still_charges_to_the_new_target(controller, inverter):
    inverter.soc = 79
    await controller.save(80)
    assert inverter.commands == [TO_BATTERY]


async def test_another_mode_is_replaced(controller, inverter):
    inverter.operation_mode = 4  # fully fed to grid, set by hand
    await controller.save(80)
    assert inverter.commands == [TO_BATTERY]

    inverter.operation_mode = 4
    inverter.soc = 90
    await controller.check()
    assert inverter.commands[-1] == TO_GRID


async def test_a_running_window_keeps_spare_solar_on_the_grid(controller, inverter, windows, clock):
    add_window(windows, start="09:00", minutes=120)
    await controller.save(80)
    assert inverter.operation_mode == SELF_CONSUMPTION

    clock.at(9, 0)
    await controller.check()
    assert inverter.commands[-1] == TO_GRID

    # Even once the window has reached its own target, until its end
    inverter.soc = 50
    clock.at(10, 30)
    await controller.check()
    assert inverter.commands[-1] == TO_GRID

    clock.at(11, 0)
    await controller.check()
    assert inverter.commands[-1] == TO_BATTERY


async def test_a_mode_change_in_a_window_asks_the_discharge_controller_to_check(tmp_path, windows, inverter, clock):
    calls = []

    async def recheck():
        calls.append(inverter.operation_mode)

    controller = DaytimeTargetController(TargetStore(tmp_path / "target.json"), windows, inverter, clock=clock,
                                         on_mode_change_in_window=recheck)
    await controller.save(80)
    assert calls == []  # no window

    add_window(windows, start="09:00", minutes=120)
    clock.at(9, 0)
    await controller.check()
    assert calls == [5]  # after the switch to TOU

    clock.at(9, 30)
    await controller.check()
    assert calls == [5]  # nothing changed


async def test_a_switched_off_window_does_not_hold_the_target_back(controller, inverter, windows, clock):
    add_window(windows, start="07:00", enabled=False)
    await controller.save(80)
    assert inverter.commands == [TO_BATTERY]


async def test_an_evening_window_has_priority(controller, inverter, windows, clock):
    windows.add(WindowSettings(name="Evening Export", start_time="22:00", duration_minutes=180, target_soc=5))
    clock.at(22, 30)
    await controller.save(80)
    assert inverter.commands == []  # TOU already


# ---------------------------------------------------------------------------
# From 23:00 to 08:00: TOU, for the night charge
# ---------------------------------------------------------------------------

async def test_at_23_self_consumption_goes_back_to_tou_whatever_the_battery(controller, inverter, clock):
    await controller.save(80)
    assert inverter.operation_mode == SELF_CONSUMPTION

    clock.at(22, 59)
    await controller.check()
    assert inverter.operation_mode == SELF_CONSUMPTION

    clock.at(23, 0)
    await controller.check()
    assert inverter.commands[-1] == TO_GRID

    clock.at(23, 30)
    await controller.check()
    assert inverter.commands == [TO_BATTERY, TO_GRID]  # once is enough


async def test_a_mode_changed_by_hand_at_night_is_put_back(controller, inverter, clock):
    for hour, minute in ((1, 0), (2, 0), (7, 59)):
        inverter.operation_mode = SELF_CONSUMPTION
        clock.at(hour, minute)
        await controller.check()
        assert inverter.commands[-1] == TO_GRID


async def test_after_the_night_window_the_battery_is_not_charged_from_solar_before_8(controller, inverter, clock):
    inverter.soc = 5  # emptied by the night window
    clock.at(1, 59)
    await controller.save(80)
    assert inverter.commands == []

    clock.at(8, 0)
    await controller.check()
    assert inverter.commands == [TO_BATTERY]


async def test_at_8_the_full_battery_stays_in_tou(controller, inverter, clock):
    inverter.soc = 100
    clock.at(7, 59)
    await controller.save(98)
    clock.at(8, 0)
    await controller.check()
    assert inverter.commands == []


async def test_a_failed_tou_switch_is_retried(controller, inverter, clock):
    inverter.operation_mode = SELF_CONSUMPTION
    inverter.write_fails = True
    clock.at(3, 0)
    assert await controller.check() == "write failed"

    inverter.write_fails = False
    clock.advance(0.5)
    assert await controller.check() is None
    assert inverter.commands == [TO_GRID]


# ---------------------------------------------------------------------------
# Failures
# ---------------------------------------------------------------------------

async def test_no_reading_is_reported_not_raised(controller, inverter):
    inverter.reading_fails = True
    assert await controller.check() == "no reading in 30 s"
    assert inverter.commands == []


async def test_a_save_the_inverter_did_not_take_is_kept_and_retried(controller, inverter):
    inverter.write_fails = True
    assert await controller.save(80) == "write failed"
    assert controller.store.load() == 80

    inverter.write_fails = False
    await controller.check()
    assert inverter.commands == [TO_BATTERY]


# ---------------------------------------------------------------------------
# /daytime-target
# ---------------------------------------------------------------------------

@pytest.fixture()
async def api(controller):
    app = FastAPI()
    app.include_router(router)
    app.state.daytime_target = controller
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=HEADERS) as client:
        yield client


async def test_wrong_api_key_is_rejected(api):
    assert (await api.get("/daytime-target", headers={"X-API-Key": "wrong"})).status_code == 401


async def test_read_only_key_reads_the_target_but_cannot_change_it(api, monkeypatch, controller):
    monkeypatch.setenv("READ_API_KEY", "read-key")
    read_only = {"X-API-Key": "read-key"}
    assert (await api.get("/daytime-target", headers=read_only)).json()["target_soc"] == 0
    assert (await api.put("/daytime-target", json={"target_soc": 80}, headers=read_only)).status_code == 401
    assert controller.store.load() == 0


async def test_get_and_set(api, inverter):
    assert (await api.get("/daytime-target")).json() == {
        "target_soc": 0, "resume_below": 0, "window_running": False, "warning": None,
    }

    response = await api.put("/daytime-target", json={"target_soc": 80})
    assert response.status_code == 200
    assert response.json() == {"target_soc": 80, "resume_below": 75, "window_running": False, "warning": None}
    assert inverter.operation_mode == SELF_CONSUMPTION  # set before the reply
    assert (await api.get("/daytime-target")).json()["target_soc"] == 80


async def test_says_when_a_window_holds_the_target_back(api, windows, clock):
    add_window(windows, start="09:00")
    clock.at(9, 30)
    assert (await api.get("/daytime-target")).json()["window_running"] is True


@pytest.mark.parametrize("target", [-1, 101])
async def test_out_of_range_is_refused(api, target):
    assert (await api.put("/daytime-target", json={"target_soc": target})).status_code == 422


async def test_a_save_the_inverter_did_not_answer_says_so(api, inverter):
    inverter.write_fails = True
    body = (await api.put("/daytime-target", json={"target_soc": 80})).json()
    assert body["target_soc"] == 80
    assert "did not respond" in body["warning"]
