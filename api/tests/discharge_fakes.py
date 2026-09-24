"""Fakes for the discharge and daytime target tests: a settable clock and an inverter that records commands."""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from inverter.reader import InverterUnavailable
from mock_clock import TZ


class Clock:
    """Dublin time that only moves when a test moves it."""

    def __init__(self, start: datetime):
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def at(self, hour: int, minute: int = 0) -> datetime:
        self.now = self.now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return self.now

    def advance(self, minutes: float) -> datetime:
        self.now += timedelta(minutes=minutes)
        return self.now


class FakeInverter:
    """Serves a battery % and the settings, records every command; fails reads or writes on demand."""

    def __init__(self, soc: float = 80.0):
        self.soc = soc
        self.operation_mode = 5  # TOU
        self.spare_solar_to_battery = False
        self.commands: list[dict] = []
        self.reading_fails = False
        self.write_fails = False
        self.reply_lost = False  # the inverter takes the command, but the reply never arrives

    def age(self):
        return None if self.reading_fails else 1.0

    def dashboard(self) -> dict:
        if self.reading_fails:
            raise InverterUnavailable("no reading in 30 s")
        return {"battery_soc": self.soc, "operation_mode": self.operation_mode,
                "spare_solar_to_battery": self.spare_solar_to_battery}

    async def write(self, settings):
        if self.write_fails:
            raise InverterUnavailable("write failed")
        command = {name: int(value) for name, value in settings}
        self.commands.append(command)
        self.operation_mode = command.get("storage_working_mode_settings", self.operation_mode)
        if "storage_excess_pv_energy_use_in_tou" in command:
            self.spare_solar_to_battery = command["storage_excess_pv_energy_use_in_tou"] == 1
        if self.reply_lost:
            raise InverterUnavailable("no response received")

    @property
    def last(self) -> dict | None:
        return self.commands[-1] if self.commands else None

    def discharging(self) -> bool:
        return self.last is not None and self.last["forcible_charge_discharge_write"] == 2

    def discharges(self) -> list[dict]:
        """Every discharge command sent (a stop sent just in case is not one)."""
        return [c for c in self.commands if c["forcible_charge_discharge_write"] == 2]


def dublin(year=2026, month=9, day=23, hour=12, minute=0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=TZ)


@pytest.fixture()
def notified():
    """The push notifications sent, as (kind, window name) pairs."""
    sent = []
    with (
        patch("notifications.notify_discharge_started", lambda *a, window_name=None: sent.append(("started", window_name))),
        patch("notifications.notify_discharge_update", lambda *a, window_name=None: sent.append(("update", window_name))),
        patch("notifications.notify_discharge_stopped", lambda *a, window_name=None: sent.append(("stopped", window_name))),
    ):
        yield sent
