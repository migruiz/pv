"""
PV Solar API: live readings from the Huawei inverter over its WiFi hotspot, and discharge windows.

Run with:  uvicorn main:app --reload
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

import notifications
from config import INVERTER_HOST, INVERTER_POLL_INTERVAL, INVERTER_PORT, MOCK_MODE, MOCK_URL
from discharge.controller import DischargeController
from discharge.router import router as discharge_router
from discharge.store import WindowStore
from inverter.reader import InverterReader
from kindle_dashboard.history import HistoryStore
from kindle_dashboard.router import router as kindle_router
from routers import dashboard, health

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pv.api")

# Docker volume in production, the api/ folder in local development
DATA_DIR = Path("/data") if Path("/data").is_dir() else Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pushes go to every phone on the topic: a simulated discharge must never reach the real phone
    if not MOCK_MODE:
        notifications.init_firebase()

    history = HistoryStore(os.environ.get("HISTORY_DB_PATH", str(DATA_DIR / "history.sqlite3")))
    app.state.history = history

    async def record_history(data):
        await asyncio.to_thread(history.record, data)

    if MOCK_MODE:
        from inverter.simulator import simulator_client_factory

        logger.info("Running in MOCK mode against the simulator at %s", MOCK_URL)
        logging.getLogger("httpx").setLevel(logging.WARNING)  # a line per register read otherwise
        inverter = InverterReader(
            host=MOCK_URL,
            port=0,
            password="mock",
            interval=INVERTER_POLL_INTERVAL,
            settle_s=0,
            client_factory=simulator_client_factory(MOCK_URL),
            on_reading=record_history,
        )
    else:
        inverter = InverterReader(
            host=INVERTER_HOST,
            port=INVERTER_PORT,
            password=os.environ["INVERTER_INSTALLER_PASS"],
            interval=INVERTER_POLL_INTERVAL,
            on_reading=record_history,
        )
    app.state.inverter = inverter

    controller = DischargeController(WindowStore(DATA_DIR / "discharge_windows.json"), inverter)
    app.state.discharge = controller

    tasks = [asyncio.create_task(inverter.run()), asyncio.create_task(controller.run())]

    yield

    # A discharge in progress is left running: its command carries the window's end, and the next
    # start applies the rule again
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await inverter.stop()
    await asyncio.to_thread(history.close)


app = FastAPI(title="PV Solar API", lifespan=lifespan)

app.include_router(health.router)
app.include_router(dashboard.router)
app.include_router(kindle_router)
app.include_router(discharge_router)

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

    async def _clock_moved(t):
        await app.state.discharge.refresh()
        return {"time": t.isoformat(), "virtual": mock_clock.is_virtual()}

    @mock_router.get("/time")
    async def get_mock_time():
        return {"time": mock_clock.get_now().isoformat(), "virtual": mock_clock.is_virtual()}

    @mock_router.post("/time")
    async def set_mock_time(body: SetTimeRequest):
        return await _clock_moved(mock_clock.set_time(body.hour, body.minute))

    @mock_router.post("/time/advance")
    async def advance_mock_time(body: AdvanceTimeRequest):
        return await _clock_moved(mock_clock.advance(body.minutes))

    @mock_router.post("/time/reset")
    async def reset_mock_time():
        return await _clock_moved(mock_clock.reset())

    app.include_router(mock_router)
