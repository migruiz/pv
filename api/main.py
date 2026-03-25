"""
PV Solar API — FastAPI middleware for Huawei FusionSolar.

Run with:  uvicorn main:app --reload
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Literal, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from auth import require_api_key
from session import SolarSession

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pv.api")

KEEP_ALIVE_INTERVAL = 120  # seconds


# ------------------------------------------------------------------
# Lifespan: startup / background keep-alive / shutdown
# ------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    session = SolarSession(
        username=os.environ["FUSIONSOLAR_USER"],
        password=os.environ["FUSIONSOLAR_PASS"],
        subdomain=os.environ.get("HUAWEI_SUBDOMAIN", "uni003eu5"),
    )
    app.state.session = session

    # Eagerly establish the session at startup
    try:
        await session.call("get_power_status")
        logger.info("FusionSolar session ready")
    except Exception as exc:
        logger.error("Initial connection failed: %s", exc)

    # Background keep-alive
    async def _keep_alive_loop():
        while True:
            await asyncio.sleep(KEEP_ALIVE_INTERVAL)
            await session.keep_alive()
            logger.debug("Keep-alive sent")

    task = asyncio.create_task(_keep_alive_loop())
    yield
    task.cancel()
    await session.shutdown()


app = FastAPI(title="PV Solar API", lifespan=lifespan)


# ------------------------------------------------------------------
# Dependency
# ------------------------------------------------------------------

def get_session(request: Request) -> SolarSession:
    return request.app.state.session


# ------------------------------------------------------------------
# Routes — Read
# ------------------------------------------------------------------

@app.get("/status", dependencies=[Depends(require_api_key)])
async def get_status(session: SolarSession = Depends(get_session)):
    """Aggregate power status across all plants."""
    try:
        ps = await session.call("get_power_status")
        return {
            "current_power_kw": ps.current_power_kw,
            "energy_today_kwh": ps.energy_today_kwh,
            "total_energy_kwh": ps.energy_kwh,
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


def _parse_flow(flow_data: dict) -> dict:
    """Extract key power values from the plant flow response."""
    pv_kw = 0.0
    battery_kw = 0.0
    battery_soc = 0.0
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

    # Grid power and directions from links
    grid_importing = False
    battery_charging = False

    for link in links:
        desc = link.get("description", {})
        label = desc.get("label", "")
        val_str = desc.get("value", "")
        flowing = link.get("flowing", "NONE")

        # Grid link: "buy.power" = grid buys from you = exporting
        #            "sell.power" = grid sells to you = importing
        if "buy" in label:
            grid_importing = False  # you're exporting (grid buys from you)
            try:
                grid_kw = float(val_str.replace("kW", "").strip())
            except (ValueError, AttributeError):
                pass
        elif "sell" in label or "input" in label:
            grid_importing = True   # you're importing (grid sells to you)
            try:
                grid_kw = float(val_str.replace("kW", "").strip())
            except (ValueError, AttributeError):
                pass

        # Battery link (inverter → battery = charging)
        from_node = link.get("fromNode", "")
        to_node = link.get("toNode", "")
        # Find if this link connects to the battery node
        for node in nodes:
            if node.get("mocId") == 20815:
                bat_id = node.get("id", "")
                if to_node == bat_id and flowing == "FORWARD":
                    battery_charging = True
                elif from_node == bat_id and flowing == "FORWARD":
                    battery_charging = False

    return {
        "pv_kw": pv_kw,
        "battery_kw": battery_kw,
        "battery_soc": battery_soc,
        "grid_kw": grid_kw,
        "home_kw": home_kw,
        "grid_importing": grid_importing,
        "battery_charging": battery_charging,
    }


@app.get("/dashboard", dependencies=[Depends(require_api_key)])
async def get_dashboard(session: SolarSession = Depends(get_session)):
    """Combined dashboard data: status + battery + flow in one call."""
    try:
        plant_ids = await session.call("get_plant_ids")
        plant_id = plant_ids[0] if plant_ids else None

        ps = await session.call("get_power_status")
        b = await session.call("get_battery_basic_stats", BATTERY_DN)

        flow_values = {}
        if plant_id:
            flow_data = await session.call("get_plant_flow", plant_id)
            flow_values = _parse_flow(flow_data)

        return {
            "pv_kw": flow_values.get("pv_kw", ps.current_power_kw),
            "battery_kw": flow_values.get("battery_kw", b.current_charge_discharge_kw),
            "battery_soc": flow_values.get("battery_soc", b.state_of_charge),
            "grid_kw": flow_values.get("grid_kw", 0.0),
            "home_kw": flow_values.get("home_kw", 0.0),
            "grid_importing": flow_values.get("grid_importing", False),
            "battery_charging": flow_values.get("battery_charging", False),
            "energy_today_kwh": ps.energy_today_kwh,
            "total_energy_kwh": ps.energy_kwh,
            "battery_status": b.operating_status,
            "battery_capacity": b.rated_capacity,
            "charged_today_kwh": b.total_charged_today_kwh,
            "discharged_today_kwh": b.total_discharged_today_kwh,
            "battery_charge_discharge_kw": b.current_charge_discharge_kw,
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.get("/plants", dependencies=[Depends(require_api_key)])
async def list_plants(session: SolarSession = Depends(get_session)):
    """List all stations."""
    try:
        return await session.call("get_station_list")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.get("/plants/{plant_id}", dependencies=[Depends(require_api_key)])
async def get_plant(plant_id: str, session: SolarSession = Depends(get_session)):
    """Real-time KPIs for a specific plant."""
    try:
        return await session.call("get_current_plant_data", plant_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.get("/plants/{plant_id}/stats", dependencies=[Depends(require_api_key)])
async def get_plant_stats(
    plant_id: str,
    query_time: Optional[int] = None,
    session: SolarSession = Depends(get_session),
):
    """Daily energy-balance timeseries. query_time = ms since epoch at 00:00 of target day."""
    try:
        if query_time is not None:
            return await session.call("get_plant_stats", plant_id, query_time)
        return await session.call("get_plant_stats", plant_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.get("/plants/{plant_id}/flow", dependencies=[Depends(require_api_key)])
async def get_plant_flow(plant_id: str, session: SolarSession = Depends(get_session)):
    """Energy flow diagram data (PV → battery → grid → load)."""
    try:
        return await session.call("get_plant_flow", plant_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.get("/devices", dependencies=[Depends(require_api_key)])
async def list_devices(session: SolarSession = Depends(get_session)):
    """List all devices (inverter, battery, sensors)."""
    try:
        return await session.call("get_device_ids")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.get("/devices/{device_dn}/realtime", dependencies=[Depends(require_api_key)])
async def get_device_realtime(
    device_dn: str, session: SolarSession = Depends(get_session)
):
    """Real-time data for a specific device."""
    try:
        return await session.call("get_real_time_data", device_dn)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.get("/plants/{plant_id}/batteries", dependencies=[Depends(require_api_key)])
async def list_batteries(plant_id: str, session: SolarSession = Depends(get_session)):
    """List battery IDs for a plant."""
    try:
        return await session.call("get_battery_ids", plant_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.get("/batteries/{battery_id}", dependencies=[Depends(require_api_key)])
async def get_battery(battery_id: str, session: SolarSession = Depends(get_session)):
    """Battery status: SOC, capacity, charge/discharge power."""
    try:
        b = await session.call("get_battery_basic_stats", battery_id)
        return {
            "state_of_charge": b.state_of_charge,
            "rated_capacity": b.rated_capacity,
            "operating_status": b.operating_status,
            "backup_time": b.backup_time,
            "bus_voltage": b.bus_voltage,
            "total_charged_today_kwh": b.total_charged_today_kwh,
            "total_discharged_today_kwh": b.total_discharged_today_kwh,
            "current_charge_discharge_kw": b.current_charge_discharge_kw,
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


# ------------------------------------------------------------------
# Routes — Device Configuration
# ------------------------------------------------------------------

BATTERY_DN = "NE=239198746"

# Signal IDs from get-config-signals (reverse-engineered from FusionSolar web portal)
SIGNALS = {
    # Forced charge/discharge
    "charge_discharge_mode": "230320245",     # 0=Stop, 1=Charge, 2=Discharge
    "forced_power_kw": "230320259",           # 0.000~2.500 kW (shown for both charge and discharge)
    "setting_mode": "230320257",              # 0=Duration, 1=Energy
    "forced_period_min": "230320281",         # 0~1440 min
    # Operation mode
    "operation_mode": "230320241",            # 2=Max self-consumption, 4=Fully fed to grid, 5=TOU
    "excess_pv_priority": "230320264",        # 0=Fed-to-grid preference, 1=Charge preference
    "allowed_ac_charge_kw": "230320255",      # 0.000~5.000 kW
    # Parameters
    "max_charge_power_w": "10011",            # 200~2500 W
    "max_discharge_power_w": "10012",         # 200~2500 W
    "end_of_charge_soc": "230320277",         # 90.0~100.0 %
    "end_of_discharge_soc": "230320278",      # 0.0~20.0 %
    "charge_from_ac": "230320279",            # 0=Disabled, 1=Enable
    "ac_charge_cutoff_soc": "230320280",      # 20.0~100.0 %
    # Peak shaving
    "peak_shaving": "230320484",              # 0=Disabled, 1=Active Power Limit
}


@app.get("/batteries/{battery_id}/config", dependencies=[Depends(require_api_key)])
async def get_battery_config(
    battery_id: str, session: SolarSession = Depends(get_session)
):
    """Get all configurable parameters for a battery device."""
    try:
        return await session.get_config_signals(battery_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


# --- Forced charge/discharge ---

class ForcedChargeDischargeRequest(BaseModel):
    mode: Literal["stop", "charge", "discharge"]
    power_kw: float = Field(default=0.7, ge=0.0, le=2.5, description="Charge/discharge power in kW")
    setting_mode: Literal["duration", "energy"] = "duration"
    duration_min: int = Field(default=60, ge=0, le=1440, description="Duration in minutes (when setting_mode=duration)")


@app.post("/batteries/{battery_id}/forced-charge", dependencies=[Depends(require_api_key)])
async def set_forced_charge_discharge(
    battery_id: str,
    body: ForcedChargeDischargeRequest,
    session: SolarSession = Depends(get_session),
):
    """Control forced charge/discharge of the battery.

    - **stop**: Stop forced charge/discharge
    - **charge**: Force charge the battery
    - **discharge**: Force discharge the battery
    """
    mode_map = {"stop": "0", "charge": "1", "discharge": "2"}
    setting_mode_map = {"duration": "0", "energy": "1"}

    change_values = [
        {"id": SIGNALS["charge_discharge_mode"], "value": mode_map[body.mode]},
        {"id": SIGNALS["setting_mode"], "value": setting_mode_map[body.setting_mode]},
    ]

    if body.mode != "stop":
        change_values.append({"id": SIGNALS["forced_power_kw"], "value": f"{body.power_kw:.3f}"})
        if body.setting_mode == "duration":
            change_values.append({"id": SIGNALS["forced_period_min"], "value": str(body.duration_min)})

    try:
        result = await session.post_config_signals(battery_id, change_values)
        return {"success": True, "mode": body.mode, "detail": result}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


# --- Operation mode ---

class OperationModeRequest(BaseModel):
    mode: Literal["maximum_self_consumption", "fully_fed_to_grid", "tou"]
    excess_pv_priority: Optional[Literal["fed_to_grid", "charge"]] = None
    allowed_ac_charge_kw: Optional[float] = Field(default=None, ge=0.0, le=5.0)


@app.post("/batteries/{battery_id}/operation-mode", dependencies=[Depends(require_api_key)])
async def set_operation_mode(
    battery_id: str,
    body: OperationModeRequest,
    session: SolarSession = Depends(get_session),
):
    """Change the battery operation mode (TOU, max self-consumption, etc.)."""
    mode_map = {"maximum_self_consumption": "2", "fully_fed_to_grid": "4", "tou": "5"}
    priority_map = {"fed_to_grid": "0", "charge": "1"}

    change_values = [
        {"id": SIGNALS["operation_mode"], "value": mode_map[body.mode]},
    ]
    if body.excess_pv_priority is not None:
        change_values.append(
            {"id": SIGNALS["excess_pv_priority"], "value": priority_map[body.excess_pv_priority]}
        )
    if body.allowed_ac_charge_kw is not None:
        change_values.append(
            {"id": SIGNALS["allowed_ac_charge_kw"], "value": f"{body.allowed_ac_charge_kw:.3f}"}
        )

    try:
        result = await session.post_config_signals(battery_id, change_values)
        return {"success": True, "mode": body.mode, "detail": result}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


# --- Battery parameters ---

class BatteryParamsRequest(BaseModel):
    max_charge_power_w: Optional[int] = Field(default=None, ge=200, le=2500)
    max_discharge_power_w: Optional[int] = Field(default=None, ge=200, le=2500)
    end_of_charge_soc: Optional[float] = Field(default=None, ge=90.0, le=100.0)
    end_of_discharge_soc: Optional[float] = Field(default=None, ge=0.0, le=20.0)
    charge_from_ac: Optional[bool] = None
    ac_charge_cutoff_soc: Optional[float] = Field(default=None, ge=20.0, le=100.0)


@app.post("/batteries/{battery_id}/params", dependencies=[Depends(require_api_key)])
async def set_battery_params(
    battery_id: str,
    body: BatteryParamsRequest,
    session: SolarSession = Depends(get_session),
):
    """Update battery parameters (charge limits, SOC thresholds, etc.)."""
    change_values = []
    if body.max_charge_power_w is not None:
        change_values.append({"id": SIGNALS["max_charge_power_w"], "value": str(body.max_charge_power_w)})
    if body.max_discharge_power_w is not None:
        change_values.append({"id": SIGNALS["max_discharge_power_w"], "value": str(body.max_discharge_power_w)})
    if body.end_of_charge_soc is not None:
        change_values.append({"id": SIGNALS["end_of_charge_soc"], "value": f"{body.end_of_charge_soc:.1f}"})
    if body.end_of_discharge_soc is not None:
        change_values.append({"id": SIGNALS["end_of_discharge_soc"], "value": f"{body.end_of_discharge_soc:.1f}"})
    if body.charge_from_ac is not None:
        change_values.append({"id": SIGNALS["charge_from_ac"], "value": "1" if body.charge_from_ac else "0"})
    if body.ac_charge_cutoff_soc is not None:
        change_values.append({"id": SIGNALS["ac_charge_cutoff_soc"], "value": f"{body.ac_charge_cutoff_soc:.1f}"})

    if not change_values:
        raise HTTPException(status_code=400, detail="No parameters provided")

    try:
        result = await session.post_config_signals(battery_id, change_values)
        return {"success": True, "detail": result}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


# ------------------------------------------------------------------
# Health
# ------------------------------------------------------------------

@app.get("/health")
async def health(session: SolarSession = Depends(get_session)):
    """Check if the FusionSolar session is alive (no API key required)."""
    try:
        alive = await session.call("is_session_active")
        return {"status": "ok" if alive else "session_expired"}
    except Exception:
        return {"status": "error"}
