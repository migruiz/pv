"""Shared configuration constants."""

import os

# Mock mode: use the mock solar simulator instead of the real inverter
MOCK_MODE = os.environ.get("MOCK_MODE", "").lower() in ("1", "true", "yes")
MOCK_URL = os.environ.get("MOCK_URL", "http://localhost:3002")

# Readings and battery commands over the inverter's WiFi hotspot (Modbus TCP, installer login)
INVERTER_HOST = os.environ.get("INVERTER_HOST", "192.168.8.1")
INVERTER_PORT = int(os.environ.get("INVERTER_PORT", "6607"))
INVERTER_POLL_INTERVAL = float(os.environ.get("INVERTER_POLL_INTERVAL", "3"))
