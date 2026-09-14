"""
PV Solar API — FastAPI middleware for Huawei FusionSolar.

Run with:  uvicorn main:app --reload
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

import notifications
from config import (
    BATTERY_DN,
    INVERTER_HOST,
    INVERTER_POLL_INTERVAL,
    INVERTER_PORT,
    KEEP_ALIVE_INTERVAL,
    MOCK_MODE,
    MOCK_URL,
)
from charge_windows.router_control import router as charge_control_router
from charge_windows.router_windows import router as charge_windows_router
from charge_windows.scheduler import ChargeWindowScheduler
from discharge.router_control import compat_router, router as control_router
from discharge.router_windows import router as windows_router
from discharge.scheduler import WindowScheduler
from kindle_dashboard.router import router as kindle_router
from routers import dashboard, health

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pv.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if MOCK_MODE:
        from mock_session import MockSession

        session = MockSession(mock_url=MOCK_URL)
        logger.info("Running in MOCK mode, connecting to %s", MOCK_URL)
    else:
        from session import SolarSession

        session = SolarSession(
            username=os.environ["FUSIONSOLAR_USER"],
            password=os.environ["FUSIONSOLAR_PASS"],
            subdomain=os.environ.get("HUAWEI_SUBDOMAIN", "uni003eu5"),
        )

    app.state.session = session
    app.state.discharge_tasks = {}
    app.state.discharge_statuses = {}
    app.state.windows_changed = asyncio.Event()

    notifications.init_firebase()

    # Live readings straight from the inverter; the cloud session is only used for battery control
    if MOCK_MODE:
        from inverter.mock_reader import MockInverterReader

        inverter = MockInverterReader(session, interval=INVERTER_POLL_INTERVAL)
    else:
        from inverter.reader import InverterReader

        inverter = InverterReader(
            host=INVERTER_HOST,
            port=INVERTER_PORT,
            password=os.environ["INVERTER_INSTALLER_PASS"],
            interval=INVERTER_POLL_INTERVAL,
        )
    app.state.inverter = inverter
    inverter_task = asyncio.create_task(inverter.run())

    if not MOCK_MODE:
        try:
            await session.call("get_power_status")
            logger.info("FusionSolar session ready")
        except Exception as exc:
            logger.error("Initial connection failed: %s", exc)

    keep_alive_task = None
    if not MOCK_MODE:
        async def _keep_alive_loop():
            while True:
                await asyncio.sleep(KEEP_ALIVE_INTERVAL)
                await session.keep_alive()
                logger.debug("Keep-alive sent")

        keep_alive_task = asyncio.create_task(_keep_alive_loop())

    # Multi-window discharge scheduler
    scheduler = WindowScheduler(app.state, session, BATTERY_DN)
    app.state.scheduler = scheduler
    scheduler_task = asyncio.create_task(scheduler.run())

    # Charge window scheduler
    app.state.charge_tasks = {}
    app.state.charge_statuses = {}
    app.state.charge_windows_changed = asyncio.Event()
    charge_scheduler = ChargeWindowScheduler(app.state, session, BATTERY_DN)
    app.state.charge_scheduler = charge_scheduler
    charge_scheduler_task = asyncio.create_task(charge_scheduler.run())

    yield

    scheduler_task.cancel()
    charge_scheduler_task.cancel()
    for task in app.state.discharge_tasks.values():
        if not task.done():
            task.cancel()
    for task in app.state.charge_tasks.values():
        if not task.done():
            task.cancel()
    if keep_alive_task:
        keep_alive_task.cancel()
    inverter_task.cancel()
    await inverter.stop()
    await session.shutdown()


app = FastAPI(title="PV Solar API", lifespan=lifespan)

app.include_router(health.router)
app.include_router(dashboard.router)
app.include_router(kindle_router)
app.include_router(control_router)   # Static paths first (/status, /{id}/start, /{id}/stop)
app.include_router(windows_router)    # Dynamic path last (/{window_id} CRUD)
app.include_router(compat_router)
app.include_router(charge_control_router)  # Static paths first (/status, /{id}/start, /{id}/stop)
app.include_router(charge_windows_router)  # Dynamic path last (/{window_id} CRUD)

# Mock-only endpoints for virtual clock control
if MOCK_MODE:
    from fastapi import APIRouter
    from pydantic import BaseModel

    import mock_clock

    mock_router = APIRouter(prefix="/mock")

    class SetTimeRequest(BaseModel):
        hour: int
        minute: int = 0

    class AdvanceTimeRequest(BaseModel):
        minutes: int

    @mock_router.get("/time")
    async def get_mock_time():
        return {
            "time": mock_clock.get_now().isoformat(),
            "virtual": mock_clock.is_virtual(),
        }

    @mock_router.post("/time")
    async def set_mock_time(body: SetTimeRequest):
        t = mock_clock.set_time(body.hour, body.minute)
        app.state.windows_changed.set()
        return {"time": t.isoformat(), "virtual": True}

    @mock_router.post("/time/advance")
    async def advance_mock_time(body: AdvanceTimeRequest):
        t = mock_clock.advance(body.minutes)
        app.state.windows_changed.set()
        return {"time": t.isoformat(), "virtual": True}

    @mock_router.post("/time/reset")
    async def reset_mock_time():
        t = mock_clock.reset()
        return {"time": t.isoformat(), "virtual": False}

    app.include_router(mock_router)
