"""Background reader that polls the inverter over its WiFi hotspot and caches the latest readings.

A single Modbus session serves every client: /dashboard and the Kindle's /dashboard.png only read
the cache, so the load on the inverter stays the same however often the app or the Kindle refresh.
The inverter answers one local session at a time, so nothing else should poll it while the API runs.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone

from inverter.mapping import FAST_REGISTERS, SLOW_REGISTERS, to_dashboard

logger = logging.getLogger("pv.inverter")

# Huawei's non-standard Modbus exception 0x80: not logged in, or the login session expired.
NOT_AUTHENTICATED = "exception_code=128"


class InverterUnavailable(RuntimeError):
    """There is no reading recent enough to show."""


class LoginRejected(RuntimeError):
    """The inverter refused the installer password. Retrying would lock logins, so polling stops."""


async def create_modbus_client(host: str, port: int):
    from huawei_solar import AsyncHuaweiSolar

    return await AsyncHuaweiSolar.create(host, port=port, slave_id=0)


class InverterReader:
    def __init__(
        self,
        host: str,
        port: int,
        password: str,
        interval: float = 3.0,
        slow_every: int = 10,
        stale_after: float = 30.0,
        reconnect_after: int = 3,
        retry_delay: float = 15.0,
        settle_s: float = 2.0,
        client_factory=create_modbus_client,
        clock=time.time,
    ):
        self._host = host
        self._port = port
        self._password = password
        self.interval = interval
        self._slow_every = slow_every
        self._stale_after = stale_after
        self._reconnect_after = reconnect_after
        self._retry_delay = retry_delay
        self._settle_s = settle_s
        self._client_factory = client_factory
        self._clock = clock

        self._client = None
        self._values: dict = {}
        self._updated_at: float | None = None
        self._slow_due = True
        self._retry_at = 0.0
        self._rounds = 0
        self._failed_rounds = 0
        self._failure_streak = 0
        self._logins = 0
        self._last_error: str | None = None
        self._stopped: str | None = None

    # ------------------------------------------------------------------
    # Cache (used by the routers)
    # ------------------------------------------------------------------

    def dashboard(self) -> dict:
        """Latest readings in the /dashboard shape; InverterUnavailable if they are too old."""
        age = self.age()
        if age is None or age > self._stale_after:
            reason = self._stopped or self._last_error or "waiting for the first reading"
            raise InverterUnavailable(f"No inverter reading in the last {self._stale_after:.0f} s: {reason}")
        updated_at = datetime.fromtimestamp(self._updated_at, timezone.utc).isoformat()
        return {**to_dashboard(self._values), "updated_at": updated_at}

    def age(self) -> float | None:
        return None if self._updated_at is None else self._clock() - self._updated_at

    def status(self) -> dict:
        age = self.age()
        return {
            "connected": self._client is not None,
            "last_reading_age_s": None if age is None else round(age, 1),
            "rounds": self._rounds,
            "failed_rounds": self._failed_rounds,
            "logins": self._logins,
            "last_error": self._last_error,
            "stopped": self._stopped,
        }

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    async def run(self):
        logger.info("Polling inverter at %s:%s every %s s", self._host, self._port, self.interval)
        while True:
            started = time.monotonic()
            try:
                await self.step()
            except LoginRejected as exc:
                self._stopped = str(exc)
                logger.error("%s", exc)
                return
            await asyncio.sleep(max(0.0, self.interval - (time.monotonic() - started)))

    async def step(self):
        """Connect when needed, then read one round. Only LoginRejected escapes."""
        if self._client is None:
            if self._clock() < self._retry_at:
                return
            try:
                await self._connect()
            except LoginRejected:
                raise
            except Exception as exc:
                await self._give_up_connection(f"connect failed: {exc}")
                return

        try:
            await self._read_round()
        except Exception as exc:
            if NOT_AUTHENTICATED not in str(exc):
                self._record_failure(f"read failed: {exc}")
                if self._failure_streak % self._reconnect_after == 0:
                    await self._disconnect()
                return
            self._record_failure("login session expired")
            try:
                await self._login()
            except LoginRejected:
                raise
            except Exception as login_exc:
                await self._give_up_connection(f"login failed: {login_exc}")

    async def stop(self):
        await self._disconnect()

    async def _connect(self):
        self._client = await self._client_factory(self._host, self._port)
        if self._settle_s:
            await asyncio.sleep(self._settle_s)
        await self._login()

    async def _login(self):
        self._logins += 1
        if not await self._client.login("installer", self._password):
            await self._disconnect()
            raise LoginRejected("Inverter rejected the installer password; polling stopped to avoid a login lockout")

    async def _read_round(self):
        fresh = {}
        for name in FAST_REGISTERS:
            fresh[name] = (await self._client.get(name)).value
        self._values.update(fresh)
        self._rounds += 1
        if self._failure_streak:
            logger.info("Inverter readings recovered after %d failed rounds", self._failure_streak)
            self._failure_streak = 0
        if self._slow_due or self._rounds % self._slow_every == 0:
            await self._read_slow()
        # Publish once the whole round is in, so the first reading never shows default settings/totals
        self._updated_at = self._clock()

    async def _read_slow(self):
        """Settings and lifetime totals change rarely; a failed read keeps the previous values."""
        try:
            for name in SLOW_REGISTERS:
                self._values[name] = (await self._client.get(name)).value
            self._slow_due = False
        except Exception as exc:
            if NOT_AUTHENTICATED in str(exc):
                raise
            self._slow_due = True
            self._last_error = f"settings read failed: {exc}"

    async def _give_up_connection(self, message: str):
        self._record_failure(message)
        await self._disconnect()
        self._retry_at = self._clock() + self._retry_delay

    async def _disconnect(self):
        client, self._client = self._client, None
        if client is not None:
            try:
                await client.stop()
            except Exception:
                pass

    def _record_failure(self, message: str):
        self._failed_rounds += 1
        self._failure_streak += 1
        self._last_error = message
        # One line when trouble starts, then every 100 rounds (~5 min): never a line per round.
        if self._failure_streak == 1 or self._failure_streak % 100 == 0:
            logger.warning("Inverter: %s (%d failed rounds in a row)", message, self._failure_streak)
