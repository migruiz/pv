"""Mock-mode stand-in for InverterReader, fed by the mock solar simulator.

The simulator imitates FusionSolar's cloud responses, so this keeps the old cloud flow parsing for
local development only. Production readings come from inverter.reader over the inverter's hotspot.
"""

import asyncio
import time
from datetime import datetime, timezone

from config import BATTERY_DN
from inverter.reader import InverterUnavailable


def parse_flow(flow_data: dict) -> dict:
    """Extract key power values from a FusionSolar-style plant flow response."""
    pv_kw = 0.0
    battery_soc = 0.0
    battery_kw = 0.0
    grid_kw = 0.0
    home_kw = 0.0

    data = flow_data.get("data", {})
    flow = data.get("flow", {})
    nodes = flow.get("nodes", [])
    links = flow.get("links", [])

    for node in nodes:
        moc_id = node.get("mocId", 0)
        value = node.get("value")
        tips = node.get("deviceTips", {})
        if moc_id == 20812 and value is not None:   # PV / String
            pv_kw = float(value)
        elif moc_id == 20815:                        # Battery / Energy Store
            if value is not None:
                battery_kw = float(value)
            if "SOC" in tips:
                battery_soc = float(tips["SOC"])
        elif moc_id == 90002 and value is not None:  # Home / Electrical Load
            home_kw = float(value)

    grid_importing = False
    battery_charging = False

    for link in links:
        desc = link.get("description", {})
        label = desc.get("label", "")
        val_str = desc.get("value", "")

        # Grid link: "buy.power" = grid buys from you = exporting
        #            "sell.power" = grid sells to you = importing
        if "buy" in label:
            grid_importing = False
            try:
                grid_kw = float(val_str.replace("kW", "").strip())
            except (ValueError, AttributeError):
                pass
        elif "sell" in label or "input" in label:
            grid_importing = True
            try:
                grid_kw = float(val_str.replace("kW", "").strip())
            except (ValueError, AttributeError):
                pass

        # Battery link (inverter → battery = charging)
        from_node = link.get("fromNode", "")
        to_node = link.get("toNode", "")
        for node in nodes:
            if node.get("mocId") == 20815:
                bat_id = node.get("id", "")
                if to_node == bat_id and link.get("flowing") == "FORWARD":
                    battery_charging = True
                elif from_node == bat_id and link.get("flowing") == "FORWARD":
                    battery_charging = False

    return {
        "pv_kw": pv_kw,
        "battery_soc": battery_soc,
        "battery_kw": battery_kw,
        "grid_kw": grid_kw,
        "home_kw": home_kw,
        "grid_importing": grid_importing,
        "battery_charging": battery_charging,
    }


class MockInverterReader:
    def __init__(self, session, interval: float = 3.0, stale_after: float = 30.0):
        self._session = session
        self.interval = interval
        self._stale_after = stale_after
        self._latest: dict | None = None
        self._updated_at: float | None = None
        self._last_error: str | None = None

    def dashboard(self) -> dict:
        age = self.age()
        if age is None or age > self._stale_after:
            reason = self._last_error or "waiting for the first reading"
            raise InverterUnavailable(f"No mock reading in the last {self._stale_after:.0f} s: {reason}")
        updated_at = datetime.fromtimestamp(self._updated_at, timezone.utc).isoformat()
        return {**self._latest, "updated_at": updated_at}

    def age(self) -> float | None:
        return None if self._updated_at is None else time.time() - self._updated_at

    def status(self) -> dict:
        age = self.age()
        return {
            "connected": True,
            "last_reading_age_s": None if age is None else round(age, 1),
            "last_error": self._last_error,
            "mock": True,
        }

    async def run(self):
        while True:
            try:
                self._latest = await self._read()
                self._updated_at = time.time()
                self._last_error = None
            except Exception as exc:
                self._last_error = str(exc)
            await asyncio.sleep(self.interval)

    async def stop(self):
        pass

    async def _read(self) -> dict:
        plant_ids = await self._session.call("get_plant_ids")
        plant_id = plant_ids[0] if plant_ids else None

        ps = await self._session.call("get_power_status")
        b = await self._session.call("get_battery_basic_stats", BATTERY_DN)

        flow_values = {}
        if plant_id:
            flow_values = parse_flow(await self._session.call("get_plant_flow", plant_id))

        try:
            inv = await self._session.get_inverter_settings(BATTERY_DN)
        except Exception:
            inv = {"operation_mode": 5, "charge_from_ac": 1, "max_charge_power": 2500}

        return {
            "pv_kw": flow_values.get("pv_kw", ps.current_power_kw),
            "battery_soc": flow_values.get("battery_soc", b.state_of_charge),
            "battery_charge_discharge_kw": flow_values.get("battery_kw", b.current_charge_discharge_kw),
            "battery_charging": flow_values.get("battery_charging", False),
            "grid_kw": flow_values.get("grid_kw", 0.0),
            "grid_importing": flow_values.get("grid_importing", False),
            "home_kw": flow_values.get("home_kw", 0.0),
            "energy_today_kwh": ps.energy_today_kwh,
            "discharged_today_kwh": b.total_discharged_today_kwh,
            "total_energy_kwh": ps.energy_kwh,
            "operation_mode": inv.get("operation_mode", 5),
            "charge_from_ac": inv.get("charge_from_ac", 1),
            "max_charge_power": inv.get("max_charge_power", 2500),
        }
