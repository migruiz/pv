"""The /discharge-windows endpoints: saves are applied before the reply, and refusals say why."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from discharge.controller import DischargeController
from discharge.router import router
from discharge.store import WindowStore
from tests.discharge_fakes import Clock, FakeInverter, dublin, notified  # noqa: F401 (fixture)

HEADERS = {"X-API-Key": "test-key"}
NIGHT = {"name": "Night Export", "start_time": "23:35", "duration_minutes": 145, "target_soc": 5,
         "notify": True, "enabled": True}


@pytest.fixture()
def clock():
    return Clock(dublin(hour=14, minute=7))


@pytest.fixture()
def inverter():
    return FakeInverter(soc=80)


@pytest.fixture()
async def api(tmp_path, clock, inverter, notified):
    app = FastAPI()
    app.include_router(router)
    app.state.discharge = DischargeController(WindowStore(tmp_path / "windows.json"), inverter, clock=clock)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=HEADERS) as client:
        yield client


async def test_wrong_api_key_is_rejected(api):
    response = await api.get("/discharge-windows", headers={"X-API-Key": "wrong"})
    assert response.status_code == 401


async def test_create_list_update_delete(api):
    created = (await api.post("/discharge-windows", json=NIGHT)).json()
    morning = {**NIGHT, "name": "Morning", "start_time": "05:00", "duration_minutes": 120, "enabled": False}
    await api.post("/discharge-windows", json=morning)

    listed = (await api.get("/discharge-windows")).json()
    assert [w["name"] for w in listed] == ["Morning", "Night Export"]  # by start time
    assert listed[1]["state"] == {"discharging": False, "target_reached": False, "power_kw": None, "soc": None,
                                  "minutes_remaining": None, "ends_at": None}

    updated = await api.put(f"/discharge-windows/{created['id']}", json={**NIGHT, "target_soc": 10})
    assert updated.status_code == 200
    assert updated.json()["target_soc"] == 10

    assert (await api.delete(f"/discharge-windows/{created['id']}")).status_code == 204
    assert [w["name"] for w in (await api.get("/discharge-windows")).json()] == ["Morning"]


async def test_a_window_starting_now_is_already_discharging_in_the_reply(api, inverter):
    manual = {**NIGHT, "name": "Manual", "start_time": "14:07", "duration_minutes": 60, "target_soc": 50}
    response = await api.post("/discharge-windows", json=manual)
    assert response.status_code == 201
    state = response.json()["state"]
    assert state["discharging"] is True
    assert state["power_kw"] == pytest.approx(1.44)  # 30% of 4.8 kWh in an hour
    assert state["minutes_remaining"] == 60
    assert inverter.discharging()


async def test_switching_off_in_the_reply(api, inverter):
    manual = {**NIGHT, "start_time": "14:00", "duration_minutes": 60}
    created = (await api.post("/discharge-windows", json=manual)).json()
    response = await api.put(f"/discharge-windows/{created['id']}", json={**manual, "enabled": False})
    assert response.json()["state"]["discharging"] is False
    assert inverter.last == {"forcible_charge_discharge_write": 0}


async def test_a_save_the_inverter_did_not_answer_says_so(api, inverter):
    inverter.write_fails = True
    manual = {**NIGHT, "name": "Manual", "start_time": "14:07", "duration_minutes": 60, "target_soc": 50}
    response = await api.post("/discharge-windows", json=manual)
    assert response.status_code == 201
    assert response.json()["warning"] == (
        "Saved, but the inverter did not respond (write failed). Retrying every 30 seconds."
    )
    assert [w["name"] for w in (await api.get("/discharge-windows")).json()] == ["Manual"]


async def test_deleting_a_running_window_whose_stop_fails_is_refused(api, inverter):
    manual = {**NIGHT, "start_time": "14:00", "duration_minutes": 60}
    created = (await api.post("/discharge-windows", json=manual)).json()
    inverter.write_fails = True
    response = await api.delete(f"/discharge-windows/{created['id']}")
    assert response.status_code == 502
    assert response.json()["detail"] == (
        "Could not stop the discharge (write failed), so the window was not deleted. Try again."
    )
    listed = (await api.get("/discharge-windows")).json()
    assert listed[0]["state"]["discharging"] is True


async def test_overlap_is_refused_with_the_reason(api):
    await api.post("/discharge-windows", json=NIGHT)
    response = await api.post("/discharge-windows", json={**NIGHT, "name": "Late", "start_time": "01:00"})
    assert response.status_code == 409
    assert response.json()["detail"] == "Overlaps with 'Night Export' (23:35 to 02:00)"


async def test_a_disabled_window_may_overlap(api):
    await api.post("/discharge-windows", json=NIGHT)
    response = await api.post("/discharge-windows", json={**NIGHT, "name": "Spare", "enabled": False})
    assert response.status_code == 201


async def test_editing_a_window_never_overlaps_itself(api):
    created = (await api.post("/discharge-windows", json=NIGHT)).json()
    response = await api.put(f"/discharge-windows/{created['id']}", json={**NIGHT, "start_time": "23:00"})
    assert response.status_code == 200


@pytest.mark.parametrize("change", [
    {"start_time": "24:00"},
    {"start_time": "9:00"},
    {"duration_minutes": 0},
    {"target_soc": 101},
    {"name": ""},
])
async def test_invalid_settings_are_refused(api, change):
    response = await api.post("/discharge-windows", json={**NIGHT, **change})
    assert response.status_code == 422


async def test_unknown_window_is_404(api):
    assert (await api.put("/discharge-windows/missing", json=NIGHT)).status_code == 404
    assert (await api.delete("/discharge-windows/missing")).status_code == 404
