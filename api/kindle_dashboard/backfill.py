"""One-time cloud history seed. Never used by PNG rendering."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from kindle_dashboard.history import FIELDS, finite

logger = logging.getLogger("pv.history")
DUBLIN = ZoneInfo("Europe/Dublin")


def fetch_history(client, start, end):
    """Read device DC power/SOC and plant consumption; normalize to UTC epochs."""
    base = f"https://{client._huawei_subdomain}.fusionsolar.huawei.com"
    rows = {}

    def put(stamp, field, raw):
        value = finite(raw)
        if value is not None and start.timestamp() <= stamp <= end.timestamp():
            if field == "battery_soc" and not 0 <= value <= 100:
                return
            rows.setdefault(stamp, {"timestamp": stamp})[field] = value

    def get(path, params):
        response = client._session.get(base + path, params=params, timeout=20)
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success"):
            raise RuntimeError(f"FusionSolar history request failed: {payload.get('failCode')}")
        return payload["data"]

    day = start.astimezone(DUBLIN).date()
    while day <= end.astimezone(DUBLIN).date():
        midnight = datetime.combine(day, datetime.min.time(), DUBLIN)
        noon_ms = round((midnight + timedelta(hours=12)).timestamp() * 1000)
        for dn, signal, field in (("NE=239198740", "30017", "pv_kw"),
                                  ("NE=239198746", "30007", "battery_soc")):
            data = get("/rest/pvms/web/device/v1/device-history-data",
                       {"deviceDn": dn, "signalIds": [signal], "date": noon_ms})
            for sample in data.get(signal, {}).get("pmDataList", []):
                put(sample["startTime"], field, sample.get("counterValue"))
        data = get("/rest/pvms/web/station/v1/overview/energy-balance", {
            "stationDn": "NE=239198726", "timeDim": 2,
            "queryTime": round(midnight.timestamp() * 1000),
            "timeZone": midnight.utcoffset().total_seconds() / 3600,
            "timeZoneStr": "Europe/Dublin"})
        if data.get("clientTimezone") != "Europe/Dublin":
            raise ValueError("Unexpected FusionSolar history timezone")
        axis, consumption = data.get("xAxis", []), data.get("usePower", [])
        if len(axis) != len(consumption):
            raise ValueError("FusionSolar consumption timestamps do not match readings")
        previous = float("-inf")
        for label, reading in zip(axis, consumption):
            local = datetime.strptime(label, "%Y-%m-%d %H:%M").replace(tzinfo=DUBLIN)
            candidates = sorted({local.replace(fold=fold).timestamp() for fold in (0, 1)})
            stamp = next((candidate for candidate in candidates if candidate > previous), None)
            if stamp is None:
                continue
            previous = stamp
            put(stamp, "home_kw", reading)
        day += timedelta(days=1)
    if any(not any(field in row for row in rows.values()) for field in FIELDS):
        raise ValueError("FusionSolar did not return all three historical series")
    return [rows[stamp] for stamp in sorted(rows)]


async def seed_history(session, store):
    """Retry initial seeding briefly; a persisted marker prevents repeat queries."""
    if await asyncio.to_thread(store.seeded):
        return
    for attempt in range(3):
        try:
            end = datetime.now(timezone.utc)
            samples = await session.get_chart_history(end - timedelta(hours=12), end)
            await asyncio.to_thread(store.seed, samples, end)
            logger.info("Seeded chart history with %d FusionSolar samples", len(samples))
            return
        except Exception as exc:
            logger.warning("History seed attempt %d failed: %s", attempt + 1, exc)
            if attempt < 2:
                await asyncio.sleep(60)
