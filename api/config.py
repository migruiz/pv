"""Shared configuration constants."""

import os

# FusionSolar session keep-alive interval (seconds)
KEEP_ALIVE_INTERVAL = 120

# Battery device identifier
BATTERY_DN = "NE=239198746"

# Mock mode: use mock simulator instead of real FusionSolar
MOCK_MODE = os.environ.get("MOCK_MODE", "").lower() in ("1", "true", "yes")
MOCK_URL = os.environ.get("MOCK_URL", "http://localhost:3002")

# Live readings over the inverter's WiFi hotspot (Modbus TCP, installer login)
INVERTER_HOST = os.environ.get("INVERTER_HOST", "192.168.8.1")
INVERTER_PORT = int(os.environ.get("INVERTER_PORT", "6607"))
INVERTER_POLL_INTERVAL = float(os.environ.get("INVERTER_POLL_INTERVAL", "3"))
