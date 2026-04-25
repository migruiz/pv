"""
FusionSolar session manager.

Maintains a single FusionSolarClient instance with:
- Cookie persistence across API restarts (avoids unnecessary logins)
- asyncio.Lock to serialize access (FusionSolarPy is synchronous)
- Manual session-state restoration when loading from cookies
"""

import asyncio
import json
import logging
import time
from pathlib import Path

from fusion_solar_py.client import FusionSolarClient

COOKIE_FILE = Path(__file__).parent / "cookies.json"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"

logger = logging.getLogger("pv.session")


class SolarSession:
    def __init__(self, username: str, password: str, subdomain: str):
        self._username = username
        self._password = password
        self._subdomain = subdomain
        self._client: FusionSolarClient | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Client lifecycle
    # ------------------------------------------------------------------

    async def _get_or_create_client(self) -> FusionSolarClient:
        if self._client is not None:
            return self._client

        # Try restoring from saved cookies (avoids a full login)
        cookies = self._load_cookies()
        if cookies:
            logger.info("Attempting session restore from saved cookies")
            try:
                client = await asyncio.to_thread(
                    FusionSolarClient,
                    self._username, self._password, self._subdomain, cookies=cookies,
                )
                alive = await asyncio.to_thread(client.is_session_active)
                if alive:
                    await asyncio.to_thread(self._restore_session_state, client)
                    self._client = client
                    self._save_cookies()
                    logger.info("Session restored successfully from cookies")
                    return self._client
                logger.warning("Saved cookies expired")
            except Exception as exc:
                logger.warning("Cookie restore failed: %s", exc)

        # Fresh login — replicate FusionSolarClient._configure_session manually so
        # we can tolerate a 503 on /unisess/v1/auth/session (Huawei's legacy SSO
        # subsystem occasionally goes down independently of the rest of the portal).
        # Passing truthy cookies to the constructor skips its strict auto-login.
        logger.info("Performing fresh FusionSolar login")
        client = await asyncio.to_thread(
            FusionSolarClient,
            self._username, self._password, self._subdomain,
            cookies={"_skip_auto_login": "1"},
        )
        await asyncio.to_thread(self._fresh_login, client)
        self._client = client
        self._save_cookies()
        logger.info("Login successful, cookies saved")
        return self._client

    def _fresh_login(self, client: FusionSolarClient):
        """Manual replacement for FusionSolarClient._configure_session.

        Differs only in tolerating a non-200 response from
        /unisess/v1/auth/session — see _try_set_unisess_csrf for why that's safe.
        """
        client._session.headers["User-Agent"] = USER_AGENT
        client._login()
        payload = client.keep_alive()
        if not payload:
            raise RuntimeError("Login failed: no payload from keep-alive")

        r = client._session.get(
            url=f"https://{self._subdomain}.fusionsolar.huawei.com"
                "/rest/neteco/web/organization/v2/company/current",
            params={"_": round(time.time() * 1000)},
        )
        r.raise_for_status()
        client._company_id = r.json()["data"]["moDn"]

        self._try_set_unisess_csrf(client)

    def _restore_session_state(self, client: FusionSolarClient):
        """Restore _company_id and roarand without calling _login()."""
        client._session.headers["User-Agent"] = USER_AGENT

        # roarand (CSRF token) via keep_alive
        client.keep_alive()

        # company ID
        r = client._session.get(
            url=f"https://{self._subdomain}.fusionsolar.huawei.com"
                "/rest/neteco/web/organization/v2/company/current",
            params={"_": round(time.time() * 1000)},
        )
        r.raise_for_status()
        client._company_id = r.json()["data"]["moDn"]

        self._try_set_unisess_csrf(client)

    def _try_set_unisess_csrf(self, client: FusionSolarClient):
        """Best-effort: refresh roarand from the legacy unisess CSRF endpoint.

        keep_alive() already populated roarand from the dpcloud keep-alive
        payload, which Huawei's own web portal uses for both reads and writes.
        The unisess endpoint provides an equivalent token from the older SSO
        subsystem — when available we prefer it, but a 503 here is non-fatal.
        """
        try:
            r = client._session.get(
                url=f"https://{self._subdomain}.fusionsolar.huawei.com"
                    "/unisess/v1/auth/session",
            )
            if r.status_code != 200:
                logger.warning(
                    "unisess /auth/session returned %s; keeping dpcloud-issued roarand",
                    r.status_code,
                )
                return
            client._session.headers["roarand"] = r.json()["csrfToken"]
        except Exception as exc:
            logger.warning(
                "unisess /auth/session unavailable (%s); keeping dpcloud-issued roarand",
                exc,
            )

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    async def call(self, method_name: str, *args, **kwargs):
        """Thread-safe call to any FusionSolarClient method."""
        async with self._lock:
            client = await self._get_or_create_client()
            fn = getattr(client, method_name)
            return await asyncio.to_thread(fn, *args, **kwargs)

    async def post_config_signals(self, device_dn: str, change_values: list[dict]):
        """POST to set-config-signals (raw call bypassing FusionSolarPy).
        change_values: list of {"id": "<signal_id>", "value": "<value>"}
        """
        async with self._lock:
            client = await self._get_or_create_client()
            return await asyncio.to_thread(
                self._post_config_signals_sync, client, device_dn, change_values
            )

    def _post_config_signals_sync(
        self, client: FusionSolarClient, device_dn: str, change_values: list[dict]
    ):
        url = (
            f"https://{self._subdomain}.fusionsolar.huawei.com"
            "/rest/pvms/web/device/v1/deviceExt/set-config-signals"
        )
        data = {
            "dn": device_dn,
            "changeValues": json.dumps(change_values),
        }
        r = client._session.post(url, data=data)
        r.raise_for_status()
        return r.json()

    async def get_inverter_settings(self, device_dn: str) -> dict:
        """Read current inverter settings from FusionSolar config signals."""
        async with self._lock:
            client = await self._get_or_create_client()
            return await asyncio.to_thread(
                self._get_inverter_settings_sync, client, device_dn,
            )

    def _get_inverter_settings_sync(self, client: FusionSolarClient, device_dn: str) -> dict:
        """Fetch config signals and extract operation mode, AC charge, and max charge power."""
        url = (
            f"https://{self._subdomain}.fusionsolar.huawei.com"
            "/rest/pvms/web/device/v1/deviceExt/get-config-signals"
        )
        r = client._session.get(url, params={"dn": device_dn})
        r.raise_for_status()
        data = r.json()

        # Defaults
        settings = {"operation_mode": 5, "charge_from_ac": 1, "max_charge_power": 2500}

        # Parse signal values from the nested response
        signal_map = {"230320241": "operation_mode", "230320279": "charge_from_ac", "10011": "max_charge_power"}
        for group in data.get("data", []):
            for signal in group.get("configSignalDisplayList", []):
                signal_id = str(signal.get("id", ""))
                if signal_id in signal_map:
                    try:
                        settings[signal_map[signal_id]] = int(float(signal.get("value", "0")))
                    except (ValueError, TypeError):
                        pass

        return settings

    async def keep_alive(self):
        """Keep the FusionSolar session alive and persist cookies."""
        async with self._lock:
            if self._client is None:
                return
            try:
                await asyncio.to_thread(self._client.keep_alive)
                self._save_cookies()
            except Exception as exc:
                logger.warning("Keep-alive failed, will re-login on next call: %s", exc)
                self._client = None

    async def shutdown(self):
        async with self._lock:
            if self._client:
                try:
                    await asyncio.to_thread(self._client.log_out)
                except Exception:
                    pass
                self._client = None

    # ------------------------------------------------------------------
    # Cookie persistence
    # ------------------------------------------------------------------

    def _load_cookies(self) -> dict | None:
        if not COOKIE_FILE.exists():
            return None
        try:
            return json.loads(COOKIE_FILE.read_text())
        except Exception:
            return None

    def _save_cookies(self):
        if self._client:
            COOKIE_FILE.write_text(json.dumps(self._client.get_cookies()))
