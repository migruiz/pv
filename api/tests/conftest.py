"""Shared test fixtures for the PV discharge windows test suite."""

import asyncio
import os
from unittest.mock import patch

import pytest

# Ensure MOCK_MODE is set before any application code imports config.py
os.environ.setdefault("MOCK_MODE", "1")
os.environ.setdefault("API_KEY", "test-key")

import mock_clock
from discharge import config_store
from discharge.models import DischargeWindow

from tests.helpers import FakeAppState, FakeSession


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_mock_clock():
    """Reset virtual clock before and after each test."""
    mock_clock.reset()
    yield
    mock_clock.reset()


@pytest.fixture()
def config_path(tmp_path):
    """Isolate config_store to a temp directory so tests don't touch dev files."""
    path = tmp_path / "discharge_windows.json"
    original = config_store._cached_path
    config_store._cached_path = path
    yield path
    config_store._cached_path = original


@pytest.fixture()
def fake_session():
    """A FakeSession with default SOC=80, decreasing by 10 each read."""
    return FakeSession(soc_sequence=[80, 70, 60, 50, 40, 30, 20, 10, 5, 0])


@pytest.fixture()
def app_state():
    """Fresh FakeAppState for each test."""
    return FakeAppState()


@pytest.fixture()
def sample_window():
    """A sample discharge window for testing."""
    return DischargeWindow(
        id="test0001",
        name="Test Window",
        start_time="22:00",
        duration_minutes=240,
        target_soc=0,
        notify=True,
        enabled=True,
    )


@pytest.fixture()
def mock_notifications():
    """Patch all notification functions and return the mocks for assertion."""
    with (
        patch("notifications.notify_discharge_started") as started,
        patch("notifications.notify_discharge_update") as updated,
        patch("notifications.notify_discharge_stopped") as stopped,
    ):
        yield {
            "started": started,
            "updated": updated,
            "stopped": stopped,
        }


@pytest.fixture()
def patch_sleep():
    """Patch asyncio.sleep globally to advance mock clock instantly.

    Each sleep call advances the virtual clock by the requested seconds (converted to minutes)
    and yields to the event loop without real delay. Uses the real sleep(0) internally to yield.
    """
    _real_sleep = asyncio.sleep
    call_count = 0
    max_calls = 500  # Safety limit to prevent infinite loops

    async def fake_sleep(seconds):
        nonlocal call_count
        if seconds == 0:
            # Pass-through for event-loop yields
            await _real_sleep(0)
            return
        call_count += 1
        if call_count > max_calls:
            raise RuntimeError(f"fake_sleep called {max_calls} times — possible infinite loop")
        # Advance mock clock by the sleep duration (in minutes)
        minutes = seconds / 60.0
        mock_clock.advance(max(1, int(minutes)))
        await _real_sleep(0)  # yield to event loop

    with patch("asyncio.sleep", new=fake_sleep):
        yield
