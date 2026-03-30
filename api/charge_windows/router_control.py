"""Start/stop/status endpoints for charge window control."""

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import require_api_key

from .models import ChargeWindowStatus, StartResponse, StopResponse

router = APIRouter(
    prefix="/charge-windows",
    dependencies=[Depends(require_api_key)],
)


@router.get("/status", response_model=list[ChargeWindowStatus])
async def all_statuses(request: Request):
    """Get runtime status for all configured charge windows."""
    scheduler = request.app.state.charge_scheduler
    return scheduler.get_all_statuses()


@router.get("/{window_id}/status", response_model=ChargeWindowStatus)
async def window_status(window_id: str, request: Request):
    """Get runtime status for a single charge window."""
    scheduler = request.app.state.charge_scheduler
    return scheduler.get_status(window_id)


@router.post("/{window_id}/start", response_model=StartResponse)
async def start_window(window_id: str, request: Request):
    """Manually start a specific charge window now."""
    scheduler = request.app.state.charge_scheduler
    try:
        return await scheduler.start_window(window_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/{window_id}/stop", response_model=StopResponse)
async def stop_window(window_id: str, request: Request):
    """Stop a specific running charge window."""
    scheduler = request.app.state.charge_scheduler
    try:
        return await scheduler.stop_window(window_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
