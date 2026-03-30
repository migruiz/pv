"""HTTP-level tests for charge window CRUD and control endpoints."""

import asyncio
import os

import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

import mock_clock
from charge_windows.router_control import router as charge_control_router
from charge_windows.router_windows import router as charge_windows_router
from charge_windows.scheduler import ChargeWindowScheduler
from charge_windows import config_store
from charge_windows.models import ChargeWindowCreate
from config import BATTERY_DN

from tests.helpers import FakeAppState, FakeSession


HEADERS = {"X-API-Key": os.environ.get("API_KEY", "test-key")}


@pytest.fixture()
async def client(app_state, charge_config_path, config_path, patch_sleep, mock_notifications):
    """Async HTTP client wired to a test FastAPI app with charge window state."""
    mock_clock.set_time(12, 0)
    session = FakeSession()

    app = FastAPI()
    app.state.session = session
    app.state.discharge_tasks = app_state.discharge_tasks
    app.state.discharge_statuses = app_state.discharge_statuses
    app.state.windows_changed = app_state.windows_changed
    app.state.charge_tasks = app_state.charge_tasks
    app.state.charge_statuses = app_state.charge_statuses
    app.state.charge_windows_changed = app_state.charge_windows_changed

    scheduler = ChargeWindowScheduler(app.state, session, BATTERY_DN)
    app.state.charge_scheduler = scheduler

    app.include_router(charge_control_router)
    app.include_router(charge_windows_router)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # Cleanup
    for task in list(app.state.charge_tasks.values()):
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


# ---------------------------------------------------------------------------
# CRUD Endpoints
# ---------------------------------------------------------------------------

class TestListWindows:
    async def test_list_empty(self, client):
        resp = await client.get("/charge-windows", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json() == []


class TestCreateWindow:
    async def test_create(self, client):
        resp = await client.post(
            "/charge-windows",
            headers=HEADERS,
            json={
                "name": "Midday Charge",
                "start_time": "10:00",
                "start_power": 200,
                "peak_time": "12:00",
                "peak_power": 2500,
                "end_time": "14:00",
                "end_power": 200,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Midday Charge"
        assert data["start_power"] == 200
        assert data["peak_power"] == 2500
        assert len(data["id"]) == 8

    async def test_create_overlapping(self, client):
        await client.post(
            "/charge-windows",
            headers=HEADERS,
            json={
                "name": "First",
                "start_time": "10:00", "start_power": 200,
                "peak_time": "12:00", "peak_power": 2500,
                "end_time": "14:00", "end_power": 200,
            },
        )
        resp = await client.post(
            "/charge-windows",
            headers=HEADERS,
            json={
                "name": "Overlap",
                "start_time": "13:00", "start_power": 200,
                "peak_time": "14:00", "peak_power": 2500,
                "end_time": "15:00", "end_power": 200,
            },
        )
        assert resp.status_code == 409

    async def test_validation_invalid_time(self, client):
        resp = await client.post(
            "/charge-windows",
            headers=HEADERS,
            json={
                "name": "Bad",
                "start_time": "25:00", "start_power": 200,
                "peak_time": "12:00", "peak_power": 2500,
                "end_time": "14:00", "end_power": 200,
            },
        )
        assert resp.status_code == 422

    async def test_validation_power_below_min(self, client):
        resp = await client.post(
            "/charge-windows",
            headers=HEADERS,
            json={
                "name": "Bad",
                "start_time": "10:00", "start_power": 100,
                "peak_time": "12:00", "peak_power": 2500,
                "end_time": "14:00", "end_power": 200,
            },
        )
        assert resp.status_code == 422


class TestGetWindow:
    async def test_get_existing(self, client):
        resp = await client.post(
            "/charge-windows",
            headers=HEADERS,
            json={
                "name": "Test",
                "start_time": "10:00", "start_power": 200,
                "peak_time": "12:00", "peak_power": 2500,
                "end_time": "14:00", "end_power": 200,
            },
        )
        window_id = resp.json()["id"]

        resp = await client.get(f"/charge-windows/{window_id}", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["name"] == "Test"

    async def test_get_missing(self, client):
        resp = await client.get("/charge-windows/nonexist", headers=HEADERS)
        assert resp.status_code == 404


class TestUpdateWindow:
    async def test_partial_update(self, client):
        resp = await client.post(
            "/charge-windows",
            headers=HEADERS,
            json={
                "name": "Original",
                "start_time": "10:00", "start_power": 200,
                "peak_time": "12:00", "peak_power": 2500,
                "end_time": "14:00", "end_power": 200,
            },
        )
        window_id = resp.json()["id"]

        resp = await client.put(
            f"/charge-windows/{window_id}",
            headers=HEADERS,
            json={"name": "Updated", "peak_power": 2000},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Updated"
        assert data["peak_power"] == 2000
        assert data["start_power"] == 200  # Unchanged


class TestDeleteWindow:
    async def test_delete(self, client):
        resp = await client.post(
            "/charge-windows",
            headers=HEADERS,
            json={
                "name": "ToDelete",
                "start_time": "10:00", "start_power": 200,
                "peak_time": "12:00", "peak_power": 2500,
                "end_time": "14:00", "end_power": 200,
            },
        )
        window_id = resp.json()["id"]

        resp = await client.delete(f"/charge-windows/{window_id}", headers=HEADERS)
        assert resp.status_code == 204

    async def test_delete_missing(self, client):
        resp = await client.delete("/charge-windows/nonexist", headers=HEADERS)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Control Endpoints
# ---------------------------------------------------------------------------

class TestStartStop:
    async def test_start_window(self, client):
        resp = await client.post(
            "/charge-windows",
            headers=HEADERS,
            json={
                "name": "Test",
                "start_time": "10:00", "start_power": 200,
                "peak_time": "12:00", "peak_power": 2500,
                "end_time": "14:00", "end_power": 200,
            },
        )
        window_id = resp.json()["id"]

        resp = await client.post(f"/charge-windows/{window_id}/start", headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["initial_power_w"] is not None

    async def test_stop_window(self, client):
        resp = await client.post(
            "/charge-windows",
            headers=HEADERS,
            json={
                "name": "Test",
                "start_time": "10:00", "start_power": 200,
                "peak_time": "12:00", "peak_power": 2500,
                "end_time": "14:00", "end_power": 200,
            },
        )
        window_id = resp.json()["id"]

        await client.post(f"/charge-windows/{window_id}/start", headers=HEADERS)
        resp = await client.post(f"/charge-windows/{window_id}/stop", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["success"] is True


class TestStatusEndpoints:
    async def test_all_statuses(self, client):
        await client.post(
            "/charge-windows",
            headers=HEADERS,
            json={
                "name": "Test",
                "start_time": "10:00", "start_power": 200,
                "peak_time": "12:00", "peak_power": 2500,
                "end_time": "14:00", "end_power": 200,
            },
        )
        resp = await client.get("/charge-windows/status", headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["active"] is False

    async def test_single_status(self, client):
        resp = await client.post(
            "/charge-windows",
            headers=HEADERS,
            json={
                "name": "Test",
                "start_time": "10:00", "start_power": 200,
                "peak_time": "12:00", "peak_power": 2500,
                "end_time": "14:00", "end_power": 200,
            },
        )
        window_id = resp.json()["id"]

        resp = await client.get(f"/charge-windows/{window_id}/status", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["active"] is False


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class TestAuth:
    async def test_no_api_key(self, client):
        resp = await client.get("/charge-windows")
        assert resp.status_code in (401, 422)

    async def test_wrong_api_key(self, client):
        resp = await client.get("/charge-windows", headers={"X-API-Key": "wrong"})
        assert resp.status_code == 401
