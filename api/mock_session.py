"""
Mock session that talks to the mock solar simulator instead of FusionSolar.

Drop-in replacement for SolarSession — same public interface (call, post_config_signals,
keep_alive, shutdown) so routers work unchanged.
"""

import httpx


class _AttrDict:
    """Simple object that allows attribute access on a dict."""

    def __init__(self, data: dict):
        for key, value in data.items():
            setattr(self, key, value)


class MockSession:
    def __init__(self, mock_url: str):
        self._url = mock_url.rstrip("/")

    async def call(self, method_name: str, *args, **kwargs):
        """Route FusionSolarClient method calls to the mock HTTP API."""
        async with httpx.AsyncClient() as client:
            if method_name == "is_session_active":
                r = await client.get(f"{self._url}/mock/session-active")
                return r.json()["active"]

            if method_name == "get_plant_ids":
                r = await client.get(f"{self._url}/mock/plant-ids")
                return r.json()["plant_ids"]

            if method_name == "get_power_status":
                r = await client.get(f"{self._url}/mock/power-status")
                return _AttrDict(r.json())

            if method_name == "get_battery_basic_stats":
                battery_dn = args[0]
                r = await client.get(f"{self._url}/mock/battery-stats/{battery_dn}")
                return _AttrDict(r.json())

            if method_name == "get_plant_flow":
                plant_id = args[0]
                r = await client.get(f"{self._url}/mock/plant-flow/{plant_id}")
                return r.json()

            raise ValueError(f"MockSession: unknown method {method_name!r}")

    async def post_config_signals(self, device_dn: str, change_values: list[dict]):
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{self._url}/mock/config-signals",
                json={"dn": device_dn, "changeValues": change_values},
            )
            return r.json()

    async def keep_alive(self):
        pass

    async def shutdown(self):
        pass
