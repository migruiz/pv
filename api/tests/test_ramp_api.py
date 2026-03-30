"""HTTP-level tests for charge ramp configuration and control endpoints."""

import asyncio
import os

import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

import mock_clock
from charge_ramp.manager import ChargeRampManager
from charge_ramp.router import router as ramp_router
from config import BATTERY_DN

from tests.helpers import FakeAppState, FakeSession


HEADERS = {"X-API-Key": os.environ.get("API_KEY", "test-key")}


@pytest.fixture()
async def client(app_state, ramp_config_path, patch_sleep):
    """Async HTTP client wired to a test FastAPI app with charge ramp state."""
    mock_clock.set_time(12, 0)
    session = FakeSession()

    app = FastAPI()
    app.state.session = session
    app.state.discharge_tasks = app_state.discharge_tasks
    app.state.discharge_statuses = app_state.discharge_statuses
    app.state.windows_changed = app_state.windows_changed
    app.state.charge_ramp_task = None
    app.state.charge_ramp_status = None
    app.state.charge_ramp_manager = ChargeRampManager(app.state, session, BATTERY_DN)

    app.include_router(ramp_router)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # Cleanup
    if app.state.charge_ramp_task and not app.state.charge_ramp_task.done():
        app.state.charge_ramp_task.cancel()
        try:
            await app.state.charge_ramp_task
        except asyncio.CancelledError:
            pass


# ---------------------------------------------------------------------------
# Config Endpoints
# ---------------------------------------------------------------------------

class TestGetConfig:
    async def test_returns_defaults(self, client):
        resp = await client.get("/charge-ramp/config", headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["duration_minutes"] == 240
        assert data["initial_power"] == 200
        assert data["top_power"] == 2500
        assert data["final_power"] == 200


class TestUpdateConfig:
    async def test_partial_update(self, client):
        resp = await client.put(
            "/charge-ramp/config",
            headers=HEADERS,
            json={"duration_minutes": 180, "top_power": 2000},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["duration_minutes"] == 180
        assert data["top_power"] == 2000
        # Unchanged fields
        assert data["initial_power"] == 200
        assert data["final_power"] == 200

    async def test_persists_across_reads(self, client):
        await client.put(
            "/charge-ramp/config",
            headers=HEADERS,
            json={"initial_power": 500},
        )
        resp = await client.get("/charge-ramp/config", headers=HEADERS)
        assert resp.json()["initial_power"] == 500

    async def test_validation_min_power(self, client):
        resp = await client.put(
            "/charge-ramp/config",
            headers=HEADERS,
            json={"initial_power": 100},  # Below min 200
        )
        assert resp.status_code == 422

    async def test_validation_max_power(self, client):
        resp = await client.put(
            "/charge-ramp/config",
            headers=HEADERS,
            json={"top_power": 3000},  # Above max 2500
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Status Endpoint
# ---------------------------------------------------------------------------

class TestGetStatus:
    async def test_idle_status(self, client):
        resp = await client.get("/charge-ramp/status", headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["active"] is False


# ---------------------------------------------------------------------------
# Start/Stop Endpoints
# ---------------------------------------------------------------------------

class TestStartStop:
    async def test_start_ramp(self, client):
        resp = await client.post("/charge-ramp/start", headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["initial_power_w"] == 200
        assert data["duration_minutes"] == 240

    async def test_start_already_running(self, client):
        await client.post("/charge-ramp/start", headers=HEADERS)
        resp = await client.post("/charge-ramp/start", headers=HEADERS)
        assert resp.status_code == 400
        assert "already running" in resp.json()["detail"]

    async def test_stop_ramp(self, client):
        await client.post("/charge-ramp/start", headers=HEADERS)
        resp = await client.post("/charge-ramp/stop", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    async def test_stop_not_running(self, client):
        resp = await client.post("/charge-ramp/stop", headers=HEADERS)
        assert resp.status_code == 400
        assert "not running" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class TestAuth:
    async def test_no_api_key(self, client):
        resp = await client.get("/charge-ramp/config")
        assert resp.status_code in (401, 422)

    async def test_wrong_api_key(self, client):
        resp = await client.get("/charge-ramp/config", headers={"X-API-Key": "wrong"})
        assert resp.status_code == 401
