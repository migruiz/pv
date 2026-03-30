"""Start/stop/status endpoints for discharge window control."""

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import require_api_key

from .models import StartResponse, StopResponse, WindowStatus

router = APIRouter(
    prefix="/discharge-windows",
    dependencies=[Depends(require_api_key)],
)


@router.get("/status", response_model=list[WindowStatus])
async def all_statuses(request: Request):
    """Get runtime status for all configured windows."""
    scheduler = request.app.state.scheduler
    return scheduler.get_all_statuses()


@router.get("/{window_id}/status", response_model=WindowStatus)
async def window_status(window_id: str, request: Request):
    """Get runtime status for a single window."""
    scheduler = request.app.state.scheduler
    return scheduler.get_status(window_id)


@router.post("/{window_id}/start", response_model=StartResponse)
async def start_window(window_id: str, request: Request):
    """Manually start a specific discharge window now."""
    scheduler = request.app.state.scheduler
    try:
        return await scheduler.start_window(window_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/{window_id}/stop", response_model=StopResponse)
async def stop_window(window_id: str, request: Request):
    """Stop a specific running discharge window."""
    scheduler = request.app.state.scheduler
    try:
        return await scheduler.stop_window(window_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ------------------------------------------------------------------
# Backward-compatible endpoints (keep existing app working)
# ------------------------------------------------------------------

compat_router = APIRouter(
    prefix="/batteries/{battery_id}/auto-discharge",
    dependencies=[Depends(require_api_key)],
)


@compat_router.get("/status")
async def compat_status(battery_id: str, request: Request):
    """Backward-compatible: return first active window's status."""
    scheduler = request.app.state.scheduler
    for s in scheduler.get_all_statuses():
        if s.active:
            return s
    return WindowStatus(window_id="", window_name="", active=False)


@compat_router.post("/stop")
async def compat_stop(battery_id: str, request: Request):
    """Backward-compatible: stop all running windows."""
    scheduler = request.app.state.scheduler
    await scheduler.stop_all()
    return {"success": True, "detail": "All windows stopped"}
