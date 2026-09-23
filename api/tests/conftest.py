"""Shared test fixtures."""

import os

import pytest

# Set before any application code imports config.py
os.environ.setdefault("MOCK_MODE", "1")
os.environ.setdefault("API_KEY", "test-key")

import mock_clock


@pytest.fixture(autouse=True)
def reset_mock_clock():
    """Reset virtual clock before and after each test."""
    mock_clock.reset()
    yield
    mock_clock.reset()
