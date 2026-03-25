"""Auto-discharge — drain battery to 0% by 2:00 AM Dublin time.

Self-contained module: configuration, models, scheduling logic,
background correction loop, and all HTTP endpoints.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

import notifications
from auth import require_api_key
from config import MOCK_MODE
from dependencies import get_session
from session import SolarSession

logger = logging.getLogger("pv.auto_discharge")

router = APIRouter(
    prefix="/batteries/{battery_id}/auto-discharge",
    dependencies=[Depends(require_api_key)],
)

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------

BATTERY_REAL_CAPACITY_KWH = 4.8          # Usable capacity (rated 5.0, real ~4.8)
MAX_DISCHARGE_POWER_KW = 2.5             # Inverter hard limit
MIN_SOC_TO_START = 5.0                   # Don't bother if SOC <= this %
TARGET_HOUR = 2                          # 2:00 AM
TARGET_MINUTE = 0
CORRECTION_INTERVAL = 30 if MOCK_MODE else 300  # 30s in mock, 5 min in production
TZ = ZoneInfo("Europe/Dublin")
SCHEDULE_HOUR = 22                       # Auto-start at 10:00 PM
SCHEDULE_MINUTE = 0

# FusionSolar signal IDs for forced charge/discharge control
SIGNALS = {
    "charge_discharge_mode": "230320245",     # 0=Stop, 1=Charge, 2=Discharge
    "forced_power_kw": "230320259",           # 0.000~2.500 kW
    "setting_mode": "230320257",              # 0=Duration, 1=Energy
    "forced_period_min": "230320281",         # 0~1440 min
}

# ------------------------------------------------------------------
# Models
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

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _minutes_until_target() -> float:
    """Minutes remaining until the next target time."""
    now = datetime.now(TZ)
    target = now.replace(hour=TARGET_HOUR, minute=TARGET_MINUTE, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds() / 60


def _calc_discharge_power(soc: float, minutes_remaining: float) -> float | None:
    """Calculate discharge power in kW, or None if not worthwhile."""
    if soc <= MIN_SOC_TO_START or minutes_remaining <= 0:
        return None
    remaining_kwh = (soc / 100.0) * BATTERY_REAL_CAPACITY_KWH
    hours_remaining = minutes_remaining / 60.0
    return min(remaining_kwh / hours_remaining, MAX_DISCHARGE_POWER_KW)


def _build_target_time() -> datetime:
    """Return the next target datetime."""
    target = datetime.now(TZ).replace(hour=TARGET_HOUR, minute=TARGET_MINUTE, second=0, microsecond=0)
    if target <= datetime.now(TZ):
        target += timedelta(days=1)
    return target


def _build_discharge_command(power_kw: float, duration_min: int) -> list[dict]:
    """Build the FusionSolar signal payload for forced discharge."""
    return [
        {"id": SIGNALS["charge_discharge_mode"], "value": "2"},
        {"id": SIGNALS["setting_mode"], "value": "0"},
        {"id": SIGNALS["forced_power_kw"], "value": f"{power_kw:.3f}"},
        {"id": SIGNALS["forced_period_min"], "value": str(duration_min)},
    ]


def _stop_command() -> list[dict]:
    """Build the FusionSolar signal payload to stop forced charge/discharge."""
    return [{"id": SIGNALS["charge_discharge_mode"], "value": "0"}]


def _build_status_dict(battery_id: str, soc: float, power_kw: float, minutes_left: float) -> dict:
    """Build a status snapshot dict."""
    return {
        "active": True,
        "battery_id": battery_id,
        "current_soc": soc,
        "remaining_energy_kwh": round((soc / 100.0) * BATTERY_REAL_CAPACITY_KWH, 3),
        "discharge_power_kw": round(power_kw, 3),
        "target_time": _build_target_time().isoformat(),
        "minutes_remaining": round(minutes_left, 1),
        "hours_remaining": round(minutes_left / 60, 2),
        "last_adjustment": datetime.now(TZ).isoformat(),
    }

# ------------------------------------------------------------------
# Background loop
# ------------------------------------------------------------------

async def _correction_loop(app_state, session: SolarSession, battery_id: str):
    """Re-adjusts discharge power every CORRECTION_INTERVAL seconds until target time."""
    logger.info("Auto-discharge loop started for battery %s", battery_id)
    try:
        while True:
            await asyncio.sleep(CORRECTION_INTERVAL)

            minutes_left = _minutes_until_target()

            # Target time reached — stop and exit
            if minutes_left <= 1:
                logger.info("Target time reached, stopping discharge")
                try:
                    await session.post_config_signals(battery_id, _stop_command())
                except Exception as exc:
                    logger.error("Failed to stop discharge at target: %s", exc)
                notifications.notify_discharge_stopped("Target time reached")
                break

            # Read current SOC
            try:
                b = await session.call("get_battery_basic_stats", battery_id)
                soc = b.state_of_charge
            except Exception as exc:
                logger.error("Failed to read SOC: %s", exc)
                continue

            power_kw = _calc_discharge_power(soc, minutes_left)

            if power_kw is None:
                logger.info("SOC too low (%.1f%%) or time expired, stopping", soc)
                try:
                    await session.post_config_signals(battery_id, _stop_command())
                except Exception as exc:
                    logger.error("Failed to stop discharge: %s", exc)
                notifications.notify_discharge_stopped(f"SOC too low ({soc:.1f}%)")
                break

            # Send adjusted command
            duration_min = int(min(minutes_left, 1440))
            try:
                await session.post_config_signals(
                    battery_id, _build_discharge_command(power_kw, duration_min)
                )
                logger.info(
                    "Adjusted: SOC=%.1f%%, power=%.3f kW, duration=%d min, target in %.0f min",
                    soc, power_kw, duration_min, minutes_left,
                )
            except Exception as exc:
                logger.error("Failed to send command: %s", exc)

            app_state.auto_discharge_status = _build_status_dict(
                battery_id, soc, power_kw, minutes_left
            )
            notifications.notify_discharge_update(soc, power_kw, minutes_left)

    except asyncio.CancelledError:
        logger.info("Auto-discharge loop cancelled")
        try:
            await session.post_config_signals(battery_id, _stop_command())
        except Exception:
            pass
        notifications.notify_discharge_stopped("Manually stopped")
        raise
    finally:
        app_state.auto_discharge_status = {"active": False}
        app_state.auto_discharge_task = None
        logger.info("Auto-discharge loop ended")

# ------------------------------------------------------------------
# Shared start logic (used by endpoint and scheduler)
# ------------------------------------------------------------------

async def _start_discharge(app_state, session, battery_id: str) -> dict:
    """Start auto-discharge. Returns result dict or raises on failure."""
    b = await session.call("get_battery_basic_stats", battery_id)
    soc = b.state_of_charge

    minutes_left = _minutes_until_target()
    power_kw = _calc_discharge_power(soc, minutes_left)

    if power_kw is None:
        raise ValueError(
            f"Discharge not worthwhile: SOC={soc}%, minutes_to_target={minutes_left:.0f}"
        )

    duration_min = int(min(minutes_left, 1440))
    await session.post_config_signals(
        battery_id, _build_discharge_command(power_kw, duration_min)
    )

    app_state.auto_discharge_task = asyncio.create_task(
        _correction_loop(app_state, session, battery_id)
    )
    app_state.auto_discharge_status = _build_status_dict(
        battery_id, soc, power_kw, minutes_left
    )
    notifications.notify_discharge_started(soc, power_kw, minutes_left)

    return {
        "success": True,
        "initial_soc": soc,
        "discharge_power_kw": round(power_kw, 3),
        "remaining_energy_kwh": round((soc / 100.0) * BATTERY_REAL_CAPACITY_KWH, 3),
        "duration_min": duration_min,
        "target_time": _build_target_time().isoformat(),
    }


# ------------------------------------------------------------------
# Daily scheduler — auto-start at 10 PM
# ------------------------------------------------------------------

def _seconds_until_schedule() -> float:
    """Seconds until the next scheduled start time (10 PM Dublin)."""
    now = datetime.now(TZ)
    target = now.replace(hour=SCHEDULE_HOUR, minute=SCHEDULE_MINUTE, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def daily_scheduler(app_state, session, battery_id: str):
    """Background task that auto-starts discharge at 10 PM every day."""
    while True:
        wait = _seconds_until_schedule()
        logger.info(
            "Daily scheduler: next auto-discharge in %.0f min at %s %02d:%02d",
            wait / 60, TZ, SCHEDULE_HOUR, SCHEDULE_MINUTE,
        )
        await asyncio.sleep(wait)

        # Skip if already running
        if (
            app_state.auto_discharge_task is not None
            and not app_state.auto_discharge_task.done()
        ):
            logger.info("Daily scheduler: auto-discharge already running, skipping")
            continue

        try:
            result = await _start_discharge(app_state, session, battery_id)
            logger.info("Daily scheduler: auto-discharge started — SOC=%.1f%%", result["initial_soc"])
        except Exception as exc:
            logger.error("Daily scheduler: failed to start auto-discharge: %s", exc)


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.post("")
async def start(
    request: Request,
    battery_id: str,
    session: SolarSession = Depends(get_session),
):
    """Start automatic battery discharge to reach 0% by 2:00 AM (Europe/Dublin)."""
    if (
        request.app.state.auto_discharge_task is not None
        and not request.app.state.auto_discharge_task.done()
    ):
        raise HTTPException(status_code=409, detail="Auto-discharge is already running")

    try:
        result = await _start_discharge(request.app.state, session, battery_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return result


@router.post("/stop")
async def stop(
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


@router.get("/status")
async def status(request: Request, battery_id: str):
    """Check whether auto-discharge is active and its current parameters."""
    data = request.app.state.auto_discharge_status.copy()

    if data.get("active"):
        minutes_left = _minutes_until_target()
        data["minutes_remaining"] = round(minutes_left, 1)
        data["hours_remaining"] = round(minutes_left / 60, 2)

    return AutoDischargeStatus(**data)
