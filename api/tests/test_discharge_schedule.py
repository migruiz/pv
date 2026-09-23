"""Window timing (midnight, daylight saving), the power maths, the inverter commands and the saved file."""

import json
from datetime import timedelta

import pytest

from discharge import commands
from discharge.models import DischargeWindow, WindowSettings
from discharge.power import calc_discharge_power
from discharge.schedule import current_run, end_time, next_change
from discharge.store import WindowStore
from tests.discharge_fakes import dublin


def window(start="23:35", minutes=145, enabled=True, **changes):
    return DischargeWindow(id="w1", name="Night", start_time=start, duration_minutes=minutes,
                           target_soc=5, enabled=enabled, **changes)


def settings(start="22:00", minutes=60, enabled=True, name="New"):
    return WindowSettings(name=name, start_time=start, duration_minutes=minutes, target_soc=0, enabled=enabled)


class TestSchedule:
    def test_run_covers_its_start_but_not_its_end(self):
        w = window(start="22:00", minutes=60)
        assert current_run([w], dublin(hour=21, minute=59)) is None
        assert current_run([w], dublin(hour=22)) is not None
        assert current_run([w], dublin(hour=23)) is None

    def test_a_run_crossing_midnight_is_found_on_both_sides(self):
        w = window()
        before = current_run([w], dublin(day=23, hour=23, minute=50))
        after = current_run([w], dublin(day=24, hour=1, minute=30))
        assert before == after
        assert before.end - before.start == timedelta(minutes=145)

    def test_disabled_windows_never_run(self):
        assert current_run([window(enabled=False)], dublin(hour=23, minute=50)) is None

    def test_next_change_is_the_next_start_or_end(self):
        w = window(start="22:00", minutes=240)
        assert next_change([w], dublin(hour=12)) == dublin(hour=22)
        assert next_change([w], dublin(hour=23)) == dublin(day=24, hour=2)
        assert next_change([w], dublin(day=24, hour=2)) == dublin(day=24, hour=22)
        assert next_change([window(enabled=False)], dublin(hour=12)) is None

    @pytest.mark.parametrize("night, real_minutes", [
        (dublin(month=10, day=24), 205),  # clocks go back at 02:00: an hour longer
        (dublin(year=2027, month=3, day=27), 85),  # clocks go forward at 01:00: an hour shorter
    ])
    def test_daylight_saving_nights_still_end_at_the_wall_clock_end(self, night, real_minutes):
        run = current_run([window()], night.replace(hour=23, minute=40))
        assert run.end.astimezone(night.tzinfo).strftime("%H:%M") == "02:00"
        assert run.end - run.start == timedelta(minutes=real_minutes)

    def test_end_time(self):
        assert end_time(window()) == "02:00"
        assert end_time(window(start="00:00", minutes=1440)) == "00:00"


class TestPowerAndCommands:
    def test_power_spreads_the_energy_over_the_time_left(self):
        assert calc_discharge_power(soc=80, minutes_remaining=240, target_soc=0) == pytest.approx(0.96)

    def test_no_power_at_or_below_target_or_when_time_is_up(self):
        assert calc_discharge_power(soc=5, minutes_remaining=60, target_soc=5) is None
        assert calc_discharge_power(soc=80, minutes_remaining=0, target_soc=5) is None

    def test_discharge_command_matches_the_live_test(self):
        # The sequence proven on the inverter on 2026-09-23: mode, period, power, then discharge
        assert [(name, int(value)) for name, value in commands.discharge(0.5, 2)] == [
            ("storage_forcible_charge_discharge_setting_mode", 0),
            ("storage_forced_charging_and_discharging_period", 2),
            ("storage_forcible_discharge_power", 500),
            ("forcible_charge_discharge_write", 2),
        ]

    def test_period_rounds_up_so_the_inverter_never_stops_early(self):
        assert dict(commands.discharge(1, 0.2))["storage_forced_charging_and_discharging_period"] == 1
        assert dict(commands.discharge(1, 90.5))["storage_forced_charging_and_discharging_period"] == 91

    def test_stop_command(self):
        assert [(name, int(value)) for name, value in commands.stop()] == [("forcible_charge_discharge_write", 0)]


class TestStore:
    @pytest.fixture()
    def store(self, tmp_path):
        return WindowStore(tmp_path / "discharge_windows.json")

    def test_no_file_means_no_windows(self, store):
        assert store.load() == []

    def test_add_replace_delete(self, store):
        w = store.add(settings())
        assert store.get(w.id).name == "New"
        store.replace(w.id, settings(name="Renamed"))
        assert [x.name for x in store.load()] == ["Renamed"]
        assert store.replace("missing", settings()) is None
        assert store.delete(w.id) is True
        assert store.delete(w.id) is False
        assert store.load() == []

    def test_reads_the_file_written_by_the_previous_version(self, store):
        # The format on the Pi before the rewrite: the same fields, so the windows carry over
        store.path.write_text(json.dumps({"windows": [{
            "id": "default0", "name": "Night Export", "start_time": "23:35", "duration_minutes": 145,
            "target_soc": 5.0, "notify": True, "enabled": True,
        }]}))
        assert store.load()[0].name == "Night Export"

    def test_an_unreadable_file_raises_instead_of_losing_the_windows(self, store):
        store.path.write_text("{not json")
        with pytest.raises(ValueError):
            store.load()

    def test_overlap_wraps_past_midnight(self, store):
        night = store.add(settings(start="23:35", minutes=145))
        assert store.overlap(settings(start="01:00", minutes=30)) == night
        assert store.overlap(settings(start="02:00", minutes=30)) is None
        assert store.overlap(settings(start="23:00", minutes=35)) is None

    def test_disabled_windows_never_overlap(self, store):
        store.add(settings(start="22:00", minutes=60, enabled=False))
        assert store.overlap(settings(start="22:30")) is None
        assert store.overlap(settings(start="22:30", enabled=False)) is None
        store.add(settings(start="10:00", minutes=60))
        assert store.overlap(settings(start="10:30", enabled=False)) is None

    def test_a_window_never_overlaps_itself(self, store):
        w = store.add(settings(start="22:00", minutes=60))
        assert store.overlap(settings(start="22:30"), exclude_id=w.id) is None
