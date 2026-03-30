"""FastAPI endpoints for charge ramp configuration and control."""

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import require_api_key

from .models import ChargeRampConfig, ChargeRampConfigUpdate, ChargeRampStatus, StartResponse, StopResponse

router = APIRouter(
    prefix="/charge-ramp",
    dependencies=[Depends(require_api_key)],
)


@router.get("/config", response_model=ChargeRampConfig)
async def get_config(request: Request):
    """Get the current charge ramp configuration."""
    from . import config_store
    return config_store.load_config()


@router.put("/config", response_model=ChargeRampConfig)
async def update_config(body: ChargeRampConfigUpdate, request: Request):
    """Update the charge ramp configuration (partial update)."""
    from . import config_store
    return config_store.update_config(body)


@router.get("/status", response_model=ChargeRampStatus)
async def get_status(request: Request):
    """Get the current charge ramp runtime status."""
    manager = request.app.state.charge_ramp_manager
    return manager.get_status()


@router.post("/start", response_model=StartResponse)
async def start_ramp(request: Request):
    """Start the charge ramp with the current configuration."""
    manager = request.app.state.charge_ramp_manager
    try:
        return await manager.start()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/stop", response_model=StopResponse)
async def stop_ramp(request: Request):
    """Stop the running charge ramp and restore TOU mode."""
    manager = request.app.state.charge_ramp_manager
    try:
        return await manager.stop()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
