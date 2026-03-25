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

from config import KEEP_ALIVE_INTERVAL, MOCK_MODE, MOCK_URL
from routers import auto_discharge, dashboard, health

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
    app.state.auto_discharge_task = None
    app.state.auto_discharge_status = {"active": False}

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

    yield

    if app.state.auto_discharge_task and not app.state.auto_discharge_task.done():
        app.state.auto_discharge_task.cancel()
    if keep_alive_task:
        keep_alive_task.cancel()
    await session.shutdown()


app = FastAPI(title="PV Solar API", lifespan=lifespan)

app.include_router(health.router)
app.include_router(dashboard.router)
app.include_router(auto_discharge.router)
