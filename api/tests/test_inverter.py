"""Tests for the local inverter reader, its commands, its /dashboard mapping and GET /dashboard."""

import asyncio
from datetime import datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from inverter.mapping import FAST_REGISTERS, SLOW_REGISTERS, to_dashboard
from inverter.reader import InverterReader, InverterUnavailable
from routers import dashboard as dashboard_module

# Values read from the SUN2000-5K-LB0 on 2026-09-14, cross-checked against the FusionSolar cloud
READINGS = {
    "input_power": 5052,
    "active_power": 5050,
    "power_meter_active_power": 4723,
    "storage_charge_discharge_power": 0,
    "storage_state_of_capacity": 75.0,
    "daily_yield_energy": 18.55,
    "storage_current_day_discharge_capacity": 1.76,
    "storage_working_mode_settings": 5,
    "storage_charge_from_grid_function": True,
    "storage_maximum_charging_power": 2500,
    "storage_excess_pv_energy_use_in_tou": 0,  # fed to grid, read on 2026-09-24
    "accumulated_yield_energy": 5922.79,
}
NOT_LOGGED_IN = RuntimeError(
    "Got error while reading from register 32064: ExceptionResponse(dev_id=0, function_code=131, exception_code=128)"
)
API_HEADERS = {"X-API-Key": "test-key"}


class Result:
    def __init__(self, value):
        self.value = value


class FakeClient:
    """Stands in for AsyncHuaweiSolar: serves READINGS and fails on demand."""

    def __init__(self, login_ok=True):
        self.readings = dict(READINGS)
        self.login_ok = login_ok
        self.logins = 0
        self.reads = []
        self.fail_with = None
        self.stopped = False
        self.writes = []
        self.accept_writes = True

    async def login(self, username, password):
        assert (username, password) == ("installer", "secret")
        self.logins += 1
        return self.login_ok

    async def get(self, name):
        self.reads.append(name)
        if self.fail_with is not None:
            raise self.fail_with
        return Result(self.readings[name])

    async def set(self, name, value):
        if self.fail_with is not None:
            raise self.fail_with
        self.writes.append((name, value))
        return self.accept_writes

    async def stop(self):
        self.stopped = True


class Clock:
    def __init__(self):
        self.now = 1_789_000_000.0

    def __call__(self):
        return self.now


def make_reader(*clients, **overrides):
    """Reader wired to fake clients handed out in order (the last one repeats) and a fake clock."""
    handed_out = []

    async def factory(host, port):
        client = clients[min(len(handed_out), len(clients) - 1)]
        handed_out.append(client)
        return client

    clock = Clock()
    options = {"client_factory": factory, "clock": clock, "settle_s": 0, **overrides}
    return InverterReader("192.168.8.1", 6607, "secret", **options), handed_out, clock


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------

class TestMapping:
    def test_exporting_with_idle_battery(self):
        assert to_dashboard(READINGS) == {
            "pv_kw": 5.052,
            "battery_soc": 75.0,
            "battery_charge_discharge_kw": 0.0,
            "battery_charging": False,
            "grid_kw": 4.723,
            "grid_importing": False,
            "home_kw": 0.327,
            "energy_today_kwh": 18.55,
            "discharged_today_kwh": 1.76,
            "total_energy_kwh": 5922.79,
            "operation_mode": 5,
            "charge_from_ac": 1,
            "max_charge_power": 2500,
            "spare_solar_to_battery": False,
        }

    def test_importing_while_battery_discharges(self):
        data = to_dashboard({
            **READINGS,
            "input_power": 0,
            "active_power": 900,
            "power_meter_active_power": -1200,
            "storage_charge_discharge_power": -800,
        })
        assert (data["grid_kw"], data["grid_importing"]) == (1.2, True)
        assert (data["battery_charge_discharge_kw"], data["battery_charging"]) == (0.8, False)
        assert data["home_kw"] == 2.1

    def test_charging_battery(self):
        data = to_dashboard({**READINGS, "storage_charge_discharge_power": 1500})
        assert (data["battery_charge_discharge_kw"], data["battery_charging"]) == (1.5, True)

    def test_enum_and_bool_registers_become_ints(self):
        class SelfConsumption:  # huawei-solar returns StorageWorkingModesC members
            value = 2

        data = to_dashboard({
            **READINGS,
            "storage_working_mode_settings": SelfConsumption(),
            "storage_charge_from_grid_function": False,
        })
        assert (data["operation_mode"], data["charge_from_ac"]) == (2, 0)

    def test_spare_solar_charging_the_battery(self):
        class Charge:  # huawei-solar returns StorageExcessPvEnergyUseInTOU members
            value = 1

        assert to_dashboard({**READINGS, "storage_excess_pv_energy_use_in_tou": Charge()})["spare_solar_to_battery"]

    def test_unread_settings_use_the_previous_defaults(self):
        data = to_dashboard({name: READINGS[name] for name in FAST_REGISTERS})
        assert (data["operation_mode"], data["charge_from_ac"], data["max_charge_power"]) == (5, 1, 2500)


# ---------------------------------------------------------------------------
# Reader
# ---------------------------------------------------------------------------

class TestReader:
    async def test_history_receives_only_successful_complete_readings(self):
        from unittest.mock import AsyncMock

        sink = AsyncMock()
        client = FakeClient()
        reader, _, clock = make_reader(client, on_reading=sink)
        await reader.step()
        sink.assert_awaited_once_with(reader.dashboard())
        client.fail_with = TimeoutError('offline')
        clock.now += 3
        await reader.step()
        assert sink.await_count == 1

    async def test_history_failure_does_not_break_live_reading_or_reconnect(self):
        from unittest.mock import AsyncMock

        reader, handed_out, _ = make_reader(FakeClient(), on_reading=AsyncMock(side_effect=OSError('disk full')))
        await reader.step()
        assert reader.dashboard()['battery_soc'] == 75
        assert reader.status()['failed_rounds'] == 0
        assert len(handed_out) == 1

    async def test_first_round_logs_in_once_and_reads_everything(self):
        client = FakeClient()
        reader, handed_out, clock = make_reader(client)
        await reader.step()
        assert (len(handed_out), client.logins) == (1, 1)
        assert client.reads == FAST_REGISTERS + SLOW_REGISTERS
        data = reader.dashboard()
        assert data["pv_kw"] == 5.052
        assert datetime.fromisoformat(data["updated_at"]).timestamp() == clock.now

    async def test_first_reading_is_published_only_after_settings_are_read(self):
        client = FakeClient()
        reader, _, _ = make_reader(client)
        real_get = client.get
        visible_during_settings_read = []

        async def get(name):
            if name == SLOW_REGISTERS[0]:
                try:
                    reader.dashboard()
                    visible_during_settings_read.append(True)
                except InverterUnavailable:
                    visible_during_settings_read.append(False)
            return await real_get(name)

        client.get = get
        await reader.step()
        assert visible_during_settings_read == [False]
        assert reader.dashboard()["total_energy_kwh"] == 5922.79

    async def test_settings_are_reread_only_every_few_rounds(self):
        client = FakeClient()
        reader, _, _ = make_reader(client, slow_every=3)
        for _ in range(6):
            await reader.step()
        assert client.reads.count("input_power") == 6
        assert client.reads.count("storage_working_mode_settings") == 3  # rounds 1, 3 and 6

    async def test_readings_go_stale(self):
        reader, _, clock = make_reader(FakeClient(), stale_after=30)
        with pytest.raises(InverterUnavailable, match="first reading"):
            reader.dashboard()
        await reader.step()
        clock.now += 29
        assert reader.dashboard()["battery_soc"] == 75.0
        clock.now += 2
        with pytest.raises(InverterUnavailable):
            reader.dashboard()

    async def test_expired_session_logs_in_again_without_reconnecting(self):
        client = FakeClient()
        reader, handed_out, _ = make_reader(client)
        await reader.step()
        client.fail_with = NOT_LOGGED_IN
        await reader.step()
        assert client.logins == 2
        client.fail_with = None
        await reader.step()
        assert len(handed_out) == 1
        assert reader.status()["failed_rounds"] == 1

    async def test_repeated_failures_reconnect_with_a_new_client(self):
        first, second = FakeClient(), FakeClient()
        reader, handed_out, _ = make_reader(first, second, reconnect_after=3)
        await reader.step()
        first.fail_with = TimeoutError("No response received after 3 retries")
        for _ in range(3):
            await reader.step()
        assert first.stopped
        await reader.step()
        assert handed_out == [first, second]
        assert reader.dashboard()["grid_kw"] == 4.723

    async def test_connection_failure_waits_before_retrying(self):
        client = FakeClient()
        attempts = []

        async def flaky_factory(host, port):
            attempts.append(host)
            if len(attempts) == 1:
                raise OSError("Host unreachable")
            return client

        reader, _, clock = make_reader(client_factory=flaky_factory, retry_delay=15)
        await reader.step()
        await reader.step()
        assert len(attempts) == 1
        clock.now += 15
        await reader.step()
        assert len(attempts) == 2
        assert reader.dashboard()["battery_soc"] == 75.0

    async def test_rejected_password_stops_polling_for_good(self):
        client = FakeClient(login_ok=False)
        reader, _, _ = make_reader(client)
        await reader.run()  # returns instead of retrying and locking logins
        assert client.logins == 1
        assert client.stopped
        assert "rejected" in reader.status()["stopped"]
        with pytest.raises(InverterUnavailable, match="rejected"):
            reader.dashboard()

    async def test_failed_settings_read_keeps_live_values(self):
        client = FakeClient()
        real_get = client.get

        async def get(name):
            if name in SLOW_REGISTERS:
                raise TimeoutError("No response received")
            return await real_get(name)

        client.get = get
        reader, _, _ = make_reader(client)
        await reader.step()
        data = reader.dashboard()
        assert (data["pv_kw"], data["operation_mode"]) == (5.052, 5)
        assert reader.status()["failed_rounds"] == 0


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

class TestCommands:
    async def test_write_sends_each_setting_in_order_over_the_polling_session(self):
        client = FakeClient()
        reader, handed_out, _ = make_reader(client)
        await reader.step()
        await reader.write([("storage_forcible_discharge_power", 500), ("forcible_charge_discharge_write", 2)])
        assert client.writes == [("storage_forcible_discharge_power", 500), ("forcible_charge_discharge_write", 2)]
        assert len(handed_out) == 1

    async def test_a_written_setting_shows_at_once_without_waiting_for_the_next_settings_read(self):
        client = FakeClient()
        reader, _, _ = make_reader(client)
        await reader.step()
        await reader.write([("storage_excess_pv_energy_use_in_tou", 1), ("forcible_charge_discharge_write", 0)])
        dashboard = reader.dashboard()
        assert dashboard["spare_solar_to_battery"] is True
        assert "forcible_charge_discharge_write" not in reader._values  # commands are not readings

    async def test_write_without_a_session_raises(self):
        reader, _, _ = make_reader(FakeClient())
        with pytest.raises(InverterUnavailable, match="Not connected"):
            await reader.write([("forcible_charge_discharge_write", 0)])

    async def test_a_refused_write_raises(self):
        client = FakeClient()
        reader, _, _ = make_reader(client)
        await reader.step()
        client.accept_writes = False
        with pytest.raises(InverterUnavailable, match="refused"):
            await reader.write([("forcible_charge_discharge_write", 0)])

    async def test_a_failed_write_raises(self):
        client = FakeClient()
        reader, _, _ = make_reader(client)
        await reader.step()
        client.fail_with = TimeoutError("No response received")
        with pytest.raises(InverterUnavailable, match="failed"):
            await reader.write([("forcible_charge_discharge_write", 0)])

    async def test_a_write_waits_for_the_reading_round_in_progress(self):
        client = FakeClient()
        reader, _, _ = make_reader(client)
        await reader.step()
        reading, release = asyncio.Event(), asyncio.Event()
        real_get = client.get

        async def slow_get(name):
            reading.set()
            await release.wait()
            return await real_get(name)

        client.get = slow_get
        poller = asyncio.create_task(reader.run())
        await reading.wait()
        writer = asyncio.create_task(reader.write([("forcible_charge_discharge_write", 0)]))
        await asyncio.sleep(0.01)
        assert client.writes == []
        release.set()
        await writer
        assert client.writes == [("forcible_charge_discharge_write", 0)]
        poller.cancel()


# ---------------------------------------------------------------------------
# GET /dashboard
# ---------------------------------------------------------------------------

@pytest.fixture()
async def api():
    reader, _, _ = make_reader(FakeClient())
    app = FastAPI()
    app.state.inverter = reader
    app.include_router(dashboard_module.router)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, reader


class TestDashboardEndpoint:
    async def test_wrong_api_key_rejected(self, api):
        ac, reader = api
        await reader.step()
        assert (await ac.get("/dashboard", headers={"X-API-Key": "wrong"})).status_code == 401

    async def test_serves_the_latest_reading(self, api):
        ac, reader = api
        await reader.step()
        resp = await ac.get("/dashboard", headers=API_HEADERS)
        assert resp.status_code == 200
        body = resp.json()
        assert (body["pv_kw"], body["home_kw"], body["grid_importing"]) == (5.052, 0.327, False)
        assert "updated_at" in body

    async def test_503_without_a_recent_reading(self, api):
        ac, _ = api
        resp = await ac.get("/dashboard", headers=API_HEADERS)
        assert resp.status_code == 503
        assert "No inverter reading" in resp.json()["detail"]
