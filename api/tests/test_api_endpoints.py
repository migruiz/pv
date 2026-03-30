"""HTTP-level tests for discharge window CRUD and control endpoints.

Uses httpx AsyncClient with FastAPI's ASGI transport — no real server needed.
"""

import asyncio
import os

import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

import mock_clock
from discharge import config_store
from discharge.models import DischargeWindow
from discharge.router_control import compat_router, router as control_router
from discharge.router_windows import router as windows_router
from discharge.scheduler import WindowScheduler
from config import BATTERY_DN

from tests.helpers import FakeAppState, FakeSession


HEADERS = {"X-API-Key": os.environ.get("API_KEY", "test-key")}


@pytest.fixture()
async def client(app_state, config_path, mock_notifications, patch_sleep):
    """Async HTTP client wired to a test FastAPI app with state pre-configured."""
    mock_clock.set_time(12, 0)
    session = FakeSession(soc_sequence=[80, 79, 78, 77, 76, 75, 74, 73, 72, 71])

    app = FastAPI()
    # Set app state directly (no lifespan needed for tests)
    app.state.session = session
    app.state.discharge_tasks = app_state.discharge_tasks
    app.state.discharge_statuses = app_state.discharge_statuses
    app.state.windows_changed = app_state.windows_changed
    app.state.scheduler = WindowScheduler(app.state, session, BATTERY_DN)

    app.include_router(control_router)
    app.include_router(windows_router)
    app.include_router(compat_router)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # Cleanup: stop any running tasks
    for task in list(app.state.discharge_tasks.values()):
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
    async def test_list_returns_seeded_default(self, client):
        resp = await client.get("/discharge-windows", headers=HEADERS)
        assert resp.status_code == 200
        windows = resp.json()
        assert len(windows) >= 1
        assert windows[0]["name"] == "Night Export"


class TestCreateWindow:
    async def test_create(self, client):
        resp = await client.post(
            "/discharge-windows",
            headers=HEADERS,
            json={
                "name": "Morning",
                "start_time": "06:00",
                "duration_minutes": 120,
                "target_soc": 10,
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Morning"
        assert data["start_time"] == "06:00"
        assert "id" in data

    async def test_create_overlapping(self, client):
        # The default Night Export is 22:00-02:00
        resp = await client.post(
            "/discharge-windows",
            headers=HEADERS,
            json={
                "name": "Conflict",
                "start_time": "23:00",
                "duration_minutes": 60,
                "target_soc": 0,
            },
        )
        assert resp.status_code == 409


class TestGetWindow:
    async def test_get_existing(self, client):
        # List to get the default window's ID
        resp = await client.get("/discharge-windows", headers=HEADERS)
        window_id = resp.json()[0]["id"]

        resp = await client.get(f"/discharge-windows/{window_id}", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["id"] == window_id

    async def test_get_missing(self, client):
        resp = await client.get("/discharge-windows/nonexistent", headers=HEADERS)
        assert resp.status_code == 404


class TestUpdateWindow:
    async def test_partial_update(self, client):
        resp = await client.get("/discharge-windows", headers=HEADERS)
        window_id = resp.json()[0]["id"]

        resp = await client.put(
            f"/discharge-windows/{window_id}",
            headers=HEADERS,
            json={"target_soc": 15},
        )
        assert resp.status_code == 200
        assert resp.json()["target_soc"] == 15
        # Other fields unchanged
        assert resp.json()["name"] == "Night Export"


class TestDeleteWindow:
    async def test_delete(self, client):
        # Create a window to delete
        resp = await client.post(
            "/discharge-windows",
            headers=HEADERS,
            json={
                "name": "ToDelete",
                "start_time": "06:00",
                "duration_minutes": 30,
                "target_soc": 0,
            },
        )
        window_id = resp.json()["id"]

        resp = await client.delete(f"/discharge-windows/{window_id}", headers=HEADERS)
        assert resp.status_code == 204

        # Verify deleted
        resp = await client.get(f"/discharge-windows/{window_id}", headers=HEADERS)
        assert resp.status_code == 404

    async def test_delete_missing(self, client):
        resp = await client.delete("/discharge-windows/nonexistent", headers=HEADERS)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Control Endpoints
# ---------------------------------------------------------------------------

class TestStartStop:
    async def test_start_window(self, client):
        resp = await client.get("/discharge-windows", headers=HEADERS)
        window_id = resp.json()[0]["id"]

        resp = await client.post(f"/discharge-windows/{window_id}/start", headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["initial_soc"] == 80

    async def test_stop_window(self, client):
        resp = await client.get("/discharge-windows", headers=HEADERS)
        window_id = resp.json()[0]["id"]

        # Start first
        await client.post(f"/discharge-windows/{window_id}/start", headers=HEADERS)

        resp = await client.post(f"/discharge-windows/{window_id}/stop", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["success"] is True


class TestStatusEndpoints:
    async def test_all_statuses(self, client):
        resp = await client.get("/discharge-windows/status", headers=HEADERS)
        assert resp.status_code == 200
        statuses = resp.json()
        assert isinstance(statuses, list)
        assert len(statuses) >= 1

    async def test_single_status(self, client):
        resp = await client.get("/discharge-windows", headers=HEADERS)
        window_id = resp.json()[0]["id"]

        resp = await client.get(f"/discharge-windows/{window_id}/status", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["window_id"] == window_id


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class TestAuth:
    async def test_no_api_key(self, client):
        resp = await client.get("/discharge-windows")
        assert resp.status_code in (401, 422)

    async def test_wrong_api_key(self, client):
        resp = await client.get("/discharge-windows", headers={"X-API-Key": "wrong"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Backward-compatible endpoints
# ---------------------------------------------------------------------------

class TestCompatEndpoints:
    async def test_compat_status_no_active(self, client):
        resp = await client.get(
            f"/batteries/{BATTERY_DN}/auto-discharge/status",
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["active"] is False

    async def test_compat_stop(self, client):
        resp = await client.post(
            f"/batteries/{BATTERY_DN}/auto-discharge/stop",
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
