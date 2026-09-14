"""Tests for the Kindle e-ink dashboard renderer and GET /dashboard.png."""

import io

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from PIL import Image

import kindle_dashboard.router as kindle_module
import mock_clock
from inverter.reader import InverterUnavailable
from kindle_dashboard import renderer

SAMPLE = {
    "pv_kw": 2.517,
    "battery_soc": 73.0,
    "battery_charge_discharge_kw": 0.001,
    "battery_charging": True,
    "grid_kw": 2.237,
    "grid_importing": False,
    "home_kw": 0.279,
    "energy_today_kwh": 1.77,
    "operation_mode": 5,
    "updated_at": "2026-09-14T08:51:07+00:00",
}
TOKEN = "k" * 64
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


class FakeInverter:
    """Stands in for the background inverter reader."""

    def __init__(self):
        self.data = dict(SAMPLE)
        self.error = None

    def dashboard(self):
        if self.error:
            raise self.error
        return self.data


def _image(payload: bytes) -> Image.Image:
    return Image.open(io.BytesIO(payload))


@pytest.fixture()
async def client(monkeypatch):
    """Test app with only the Kindle router and a fake inverter reader."""
    monkeypatch.setenv("KINDLE_TOKEN", TOKEN)
    monkeypatch.setattr(kindle_module, "_last_good", None)
    monkeypatch.setattr(kindle_module, "_cached", None)
    inverter = FakeInverter()

    app = FastAPI()
    app.state.inverter = inverter
    app.include_router(kindle_module.router)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, inverter


@pytest.fixture()
def render_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(kindle_module, "render_png", lambda *args: calls.append(args) or b"png")
    return calls


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

class TestRenderer:
    def test_exact_kindle_size_and_monochrome(self):
        image = renderer.render(SAMPLE, mock_clock.get_now())
        assert image.size == (800, 600)
        assert image.mode == "1"

    def test_png_is_valid_and_small(self):
        payload = renderer.render_png(SAMPLE, mock_clock.get_now())
        assert len(payload) < 200_000
        assert _image(payload).format == "PNG"

    def test_stale_banner_changes_image(self):
        now = mock_clock.get_now()
        assert renderer.render_png(SAMPLE, now) != renderer.render_png(SAMPLE, now, stale=True)

    def test_missing_or_bad_values_render_as_zero(self):
        image = renderer.render({"battery_soc": "n/a"}, mock_clock.get_now())
        assert image.size == (800, 600)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class TestAuth:
    async def test_missing_token_rejected(self, client):
        ac, _ = client
        assert (await ac.get("/dashboard.png")).status_code == 401

    async def test_wrong_token_rejected(self, client):
        ac, _ = client
        resp = await ac.get("/dashboard.png", headers={"Authorization": "Bearer wrong"})
        assert resp.status_code == 401

    async def test_api_key_header_not_accepted(self, client):
        ac, _ = client
        resp = await ac.get("/dashboard.png", headers={"X-API-Key": TOKEN})
        assert resp.status_code == 401

    async def test_unset_token_rejects_everything(self, client, monkeypatch):
        ac, _ = client
        monkeypatch.delenv("KINDLE_TOKEN")
        resp = await ac.get("/dashboard.png", headers={"Authorization": "Bearer "})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

class TestDashboardPng:
    async def test_returns_uncached_kindle_png(self, client):
        ac, _ = client
        resp = await ac.get("/dashboard.png", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        assert resp.headers["cache-control"] == "no-store"
        assert _image(resp.content).size == (800, 600)

    async def test_timestamp_is_the_reading_time_in_dublin(self, client, render_calls):
        ac, _ = client
        await ac.get("/dashboard.png", headers=HEADERS)
        _, updated_at, stale = render_calls[0]
        assert str(updated_at.tzinfo) == "Europe/Dublin"
        assert (updated_at.hour, updated_at.minute, updated_at.second, stale) == (9, 51, 7, False)

    async def test_same_reading_is_drawn_only_once(self, client, render_calls):
        ac, inverter = client
        await ac.get("/dashboard.png", headers=HEADERS)
        await ac.get("/dashboard.png", headers=HEADERS)
        assert len(render_calls) == 1
        inverter.data = {**SAMPLE, "updated_at": "2026-09-14T08:51:10+00:00"}
        await ac.get("/dashboard.png", headers=HEADERS)
        assert len(render_calls) == 2

    async def test_failure_redraws_last_good_readings_as_stale(self, client, render_calls):
        ac, inverter = client
        await ac.get("/dashboard.png", headers=HEADERS)
        inverter.error = InverterUnavailable("inverter offline")
        resp = await ac.get("/dashboard.png", headers=HEADERS)
        assert resp.status_code == 200
        data, updated_at, stale = render_calls[1]
        assert data == SAMPLE
        assert (updated_at.hour, updated_at.minute, stale) == (9, 51, True)

    async def test_failure_before_any_success_still_returns_png(self, client):
        ac, inverter = client
        inverter.error = InverterUnavailable("inverter offline")
        resp = await ac.get("/dashboard.png", headers=HEADERS)
        assert resp.status_code == 200
        assert _image(resp.content).size == (800, 600)
