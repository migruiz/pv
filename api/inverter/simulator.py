"""Mock mode: stands in for the inverter's Modbus client, backed by the mock solar simulator over HTTP.

The simulator serves and accepts the same register names as the real inverter, so mock mode runs the
real InverterReader, register mapping and discharge commands.
"""

import httpx


class _Result:
    def __init__(self, value):
        self.value = value


class SimulatorClient:
    def __init__(self, url: str):
        self._http = httpx.AsyncClient(base_url=url.rstrip("/"), timeout=5)

    async def login(self, username: str, password: str) -> bool:
        return True

    async def get(self, name: str) -> _Result:
        response = await self._http.get("/mock/registers")
        response.raise_for_status()
        return _Result(response.json()[name])

    async def set(self, name: str, value) -> bool:
        response = await self._http.post("/mock/registers", json={name: int(value)})
        response.raise_for_status()
        return True

    async def stop(self):
        await self._http.aclose()


def simulator_client_factory(url: str):
    """A client_factory for InverterReader that connects to the simulator at url."""

    async def create(host: str, port: int) -> SimulatorClient:
        return SimulatorClient(url)

    return create
