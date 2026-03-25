"""
PV Solar API — FastAPI middleware for Huawei FusionSolar.

Run with:  uvicorn main:app --reload
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel

from auth import require_api_key
from session import SolarSession

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pv.api")

KEEP_ALIVE_INTERVAL = 120  # seconds

# Battery device
BATTERY_DN = "NE=239198746"

# Auto-discharge configuration
BATTERY_REAL_CAPACITY_KWH = 4.8          # Usable capacity (rated 5.0, real ~4.8)
MAX_DISCHARGE_POWER_KW = 2.5             # Inverter hard limit
MIN_SOC_TO_START = 5.0                   # Don't bother if SOC <= this %
AUTO_DISCHARGE_TARGET_HOUR = 2           # Target: 2:00 AM
AUTO_DISCHARGE_TARGET_MINUTE = 0
AUTO_DISCHARGE_CORRECTION_INTERVAL = 300 # Re-check every 5 min (seconds)
AUTO_DISCHARGE_TZ = ZoneInfo("Europe/Dublin")

# Signal IDs used by auto-discharge (reverse-engineered from FusionSolar web portal)
SIGNALS = {
    "charge_discharge_mode": "230320245",     # 0=Stop, 1=Charge, 2=Discharge
    "forced_power_kw": "230320259",           # 0.000~2.500 kW
    "setting_mode": "230320257",              # 0=Duration, 1=Energy
    "forced_period_min": "230320281",         # 0~1440 min
}


# ------------------------------------------------------------------
# Auto-discharge helpers
# ------------------------------------------------------------------

def _minutes_until_target() -> float:
    """Minutes remaining until the next 2:00 AM in Europe/Dublin."""
    now = datetime.now(AUTO_DISCHARGE_TZ)
    target = now.replace(
        hour=AUTO_DISCHARGE_TARGET_HOUR,
        minute=AUTO_DISCHARGE_TARGET_MINUTE,
        second=0,
        microsecond=0,
    )
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds() / 60


def _calc_discharge_power(soc: float, minutes_remaining: float) -> float | None:
    """Calculate discharge power in kW, or None if not worthwhile."""
    if soc <= MIN_SOC_TO_START:
        return None
    if minutes_remaining <= 0:
        return None
    remaining_kwh = (soc / 100.0) * BATTERY_REAL_CAPACITY_KWH
    hours_remaining = minutes_remaining / 60.0
    power_kw = remaining_kwh / hours_remaining
    return min(power_kw, MAX_DISCHARGE_POWER_KW)


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
    app.state.auto_discharge_task = None
    app.state.auto_discharge_status = {"active": False}

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
    if app.state.auto_discharge_task and not app.state.auto_discharge_task.done():
        app.state.auto_discharge_task.cancel()
    task.cancel()
    await session.shutdown()


app = FastAPI(title="PV Solar API", lifespan=lifespan)


# ------------------------------------------------------------------
# Dependency
# ------------------------------------------------------------------

def get_session(request: Request) -> SolarSession:
    return request.app.state.session


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


# ------------------------------------------------------------------
# Dashboard
# ------------------------------------------------------------------

def _parse_flow(flow_data: dict) -> dict:
    """Extract key power values from the plant flow response."""
    pv_kw = 0.0
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
        "grid_kw": grid_kw,
        "home_kw": home_kw,
        "grid_importing": grid_importing,
        "battery_charging": battery_charging,
    }


@app.get("/dashboard", dependencies=[Depends(require_api_key)])
async def get_dashboard(session: SolarSession = Depends(get_session)):
    """Combined dashboard data for the Android app."""
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
            "battery_soc": flow_values.get("battery_soc", b.state_of_charge),
            "battery_charge_discharge_kw": b.current_charge_discharge_kw,
            "battery_charging": flow_values.get("battery_charging", False),
            "grid_kw": flow_values.get("grid_kw", 0.0),
            "grid_importing": flow_values.get("grid_importing", False),
            "home_kw": flow_values.get("home_kw", 0.0),
            "energy_today_kwh": ps.energy_today_kwh,
            "discharged_today_kwh": b.total_discharged_today_kwh,
            "total_energy_kwh": ps.energy_kwh,
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


# ------------------------------------------------------------------
# Auto-discharge
# ------------------------------------------------------------------

class AutoDischargeStatus(BaseModel):
    active: bool
    battery_id: Optional[str] = None
    current_soc: Optional[float] = None
    remaining_energy_kwh: Optional[float] = None
    discharge_power_kw: Optional[float] = None
    target_time: Optional[str] = None
    minutes_remaining: Optional[float] = None
    hours_remaining: Optional[float] = None
    last_adjustment: Optional[str] = None


async def _auto_discharge_loop(app_state, session: SolarSession, battery_id: str):
    """Background loop that re-adjusts discharge power every 5 minutes until target time."""
    logger.info("Auto-discharge loop started for battery %s", battery_id)
    try:
        while True:
            await asyncio.sleep(AUTO_DISCHARGE_CORRECTION_INTERVAL)

            minutes_left = _minutes_until_target()

            # Target time reached — stop discharge and exit
            if minutes_left <= 1:
                logger.info("Auto-discharge target time reached, stopping")
                try:
                    await session.post_config_signals(battery_id, [
                        {"id": SIGNALS["charge_discharge_mode"], "value": "0"},
                    ])
                except Exception as exc:
                    logger.error("Failed to stop discharge at target: %s", exc)
                break

            # Read current SOC
            try:
                b = await session.call("get_battery_basic_stats", battery_id)
                soc = b.state_of_charge
            except Exception as exc:
                logger.error("Auto-discharge: failed to read SOC: %s", exc)
                continue

            power_kw = _calc_discharge_power(soc, minutes_left)

            if power_kw is None:
                logger.info("Auto-discharge: SOC too low (%.1f%%) or time expired, stopping", soc)
                try:
                    await session.post_config_signals(battery_id, [
                        {"id": SIGNALS["charge_discharge_mode"], "value": "0"},
                    ])
                except Exception as exc:
                    logger.error("Failed to stop discharge: %s", exc)
                break

            # Send adjusted forced-discharge command
            duration_min = int(min(minutes_left, 1440))
            change_values = [
                {"id": SIGNALS["charge_discharge_mode"], "value": "2"},
                {"id": SIGNALS["setting_mode"], "value": "0"},
                {"id": SIGNALS["forced_power_kw"], "value": f"{power_kw:.3f}"},
                {"id": SIGNALS["forced_period_min"], "value": str(duration_min)},
            ]
            try:
                await session.post_config_signals(battery_id, change_values)
                logger.info(
                    "Auto-discharge adjusted: SOC=%.1f%%, power=%.3f kW, "
                    "duration=%d min, target in %.0f min",
                    soc, power_kw, duration_min, minutes_left,
                )
            except Exception as exc:
                logger.error("Auto-discharge: failed to send command: %s", exc)

            # Update shared status
            now_str = datetime.now(AUTO_DISCHARGE_TZ).isoformat()
            target = datetime.now(AUTO_DISCHARGE_TZ).replace(
                hour=AUTO_DISCHARGE_TARGET_HOUR,
                minute=AUTO_DISCHARGE_TARGET_MINUTE,
                second=0, microsecond=0,
            )
            if target <= datetime.now(AUTO_DISCHARGE_TZ):
                target += timedelta(days=1)
            app_state.auto_discharge_status = {
                "active": True,
                "battery_id": battery_id,
                "current_soc": soc,
                "remaining_energy_kwh": round((soc / 100.0) * BATTERY_REAL_CAPACITY_KWH, 3),
                "discharge_power_kw": round(power_kw, 3),
                "target_time": target.isoformat(),
                "minutes_remaining": round(minutes_left, 1),
                "hours_remaining": round(minutes_left / 60, 2),
                "last_adjustment": now_str,
            }

    except asyncio.CancelledError:
        logger.info("Auto-discharge loop cancelled")
        try:
            await session.post_config_signals(battery_id, [
                {"id": SIGNALS["charge_discharge_mode"], "value": "0"},
            ])
        except Exception:
            pass
        raise
    finally:
        app_state.auto_discharge_status = {"active": False}
        app_state.auto_discharge_task = None
        logger.info("Auto-discharge loop ended")


@app.post("/batteries/{battery_id}/auto-discharge", dependencies=[Depends(require_api_key)])
async def start_auto_discharge(
    request: Request,
    battery_id: str,
    session: SolarSession = Depends(get_session),
):
    """Start automatic battery discharge to reach 0% by 2:00 AM (Europe/Dublin)."""
    # Guard: already running
    if (
        request.app.state.auto_discharge_task is not None
        and not request.app.state.auto_discharge_task.done()
    ):
        raise HTTPException(status_code=409, detail="Auto-discharge is already running")

    # Read current SOC
    try:
        b = await session.call("get_battery_basic_stats", battery_id)
        soc = b.state_of_charge
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to read battery: {exc}")

    minutes_left = _minutes_until_target()
    power_kw = _calc_discharge_power(soc, minutes_left)

    if power_kw is None:
        raise HTTPException(
            status_code=400,
            detail=f"Discharge not worthwhile: SOC={soc}%, minutes_to_target={minutes_left:.0f}",
        )

    # Send initial forced-discharge command
    duration_min = int(min(minutes_left, 1440))
    change_values = [
        {"id": SIGNALS["charge_discharge_mode"], "value": "2"},
        {"id": SIGNALS["setting_mode"], "value": "0"},
        {"id": SIGNALS["forced_power_kw"], "value": f"{power_kw:.3f}"},
        {"id": SIGNALS["forced_period_min"], "value": str(duration_min)},
    ]
    try:
        await session.post_config_signals(battery_id, change_values)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to start discharge: {exc}")

    # Start background correction loop
    bg_task = asyncio.create_task(
        _auto_discharge_loop(request.app.state, session, battery_id)
    )
    request.app.state.auto_discharge_task = bg_task

    target = datetime.now(AUTO_DISCHARGE_TZ).replace(
        hour=AUTO_DISCHARGE_TARGET_HOUR,
        minute=AUTO_DISCHARGE_TARGET_MINUTE,
        second=0, microsecond=0,
    )
    if target <= datetime.now(AUTO_DISCHARGE_TZ):
        target += timedelta(days=1)

    request.app.state.auto_discharge_status = {
        "active": True,
        "battery_id": battery_id,
        "current_soc": soc,
        "remaining_energy_kwh": round((soc / 100.0) * BATTERY_REAL_CAPACITY_KWH, 3),
        "discharge_power_kw": round(power_kw, 3),
        "target_time": target.isoformat(),
        "minutes_remaining": round(minutes_left, 1),
        "hours_remaining": round(minutes_left / 60, 2),
        "last_adjustment": datetime.now(AUTO_DISCHARGE_TZ).isoformat(),
    }

    return {
        "success": True,
        "initial_soc": soc,
        "discharge_power_kw": round(power_kw, 3),
        "remaining_energy_kwh": round((soc / 100.0) * BATTERY_REAL_CAPACITY_KWH, 3),
        "duration_min": duration_min,
        "target_time": target.isoformat(),
    }


@app.post("/batteries/{battery_id}/auto-discharge/stop", dependencies=[Depends(require_api_key)])
async def stop_auto_discharge(
    request: Request,
    battery_id: str,
    session: SolarSession = Depends(get_session),
):
    """Cancel the auto-discharge background loop and stop forced discharge."""
    task = request.app.state.auto_discharge_task
    if task is None or task.done():
        raise HTTPException(status_code=404, detail="No auto-discharge is currently running")

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    return {"success": True, "detail": "Auto-discharge stopped"}


@app.get("/batteries/{battery_id}/auto-discharge/status", dependencies=[Depends(require_api_key)])
async def get_auto_discharge_status(request: Request, battery_id: str):
    """Check whether auto-discharge is active and its current parameters."""
    status = request.app.state.auto_discharge_status.copy()

    # Update time fields to be current (not stale from last correction cycle)
    if status.get("active"):
        minutes_left = _minutes_until_target()
        status["minutes_remaining"] = round(minutes_left, 1)
        status["hours_remaining"] = round(minutes_left / 60, 2)

    return AutoDischargeStatus(**status)
