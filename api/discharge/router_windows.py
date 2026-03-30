"""CRUD REST endpoints for discharge window configuration."""

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import require_api_key

from . import config_store
from .models import DischargeWindow, DischargeWindowCreate, DischargeWindowUpdate

router = APIRouter(
    prefix="/discharge-windows",
    dependencies=[Depends(require_api_key)],
)


@router.get("", response_model=list[DischargeWindow])
async def list_windows():
    """List all configured discharge windows."""
    return config_store.load_windows()


@router.get("/{window_id}", response_model=DischargeWindow)
async def get_window(window_id: str):
    """Get a single discharge window by ID."""
    window = config_store.get_window(window_id)
    if window is None:
        raise HTTPException(status_code=404, detail=f"Window {window_id} not found")
    return window


@router.post("", response_model=DischargeWindow, status_code=201)
async def create_window(body: DischargeWindowCreate, request: Request):
    """Create a new discharge window."""
    _validate_time(body.start_time)

    conflict = config_store.check_overlap(body)
    if conflict:
        raise HTTPException(
            status_code=409,
            detail=f"Overlaps with window '{conflict.name}' ({conflict.start_time}, {conflict.duration_minutes} min)",
        )

    window = config_store.add_window(body)
    request.app.state.windows_changed.set()
    return window


@router.put("/{window_id}", response_model=DischargeWindow)
async def update_window(window_id: str, body: DischargeWindowUpdate, request: Request):
    """Update a discharge window (partial update)."""
    existing = config_store.get_window(window_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Window {window_id} not found")

    if body.start_time is not None:
        _validate_time(body.start_time)

    # Build a merged candidate for overlap checking
    merged = existing.model_dump()
    for key, value in body.model_dump(exclude_unset=True).items():
        merged[key] = value
    candidate = DischargeWindow(**merged)

    if candidate.enabled:
        conflict = config_store.check_overlap(candidate, exclude_id=window_id)
        if conflict:
            raise HTTPException(
                status_code=409,
                detail=f"Overlaps with window '{conflict.name}' ({conflict.start_time}, {conflict.duration_minutes} min)",
            )

    updated = config_store.update_window(window_id, body)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Window {window_id} not found")

    request.app.state.windows_changed.set()
    return updated


@router.delete("/{window_id}", status_code=204)
async def delete_window(window_id: str, request: Request):
    """Delete a discharge window."""
    if not config_store.delete_window(window_id):
        raise HTTPException(status_code=404, detail=f"Window {window_id} not found")

    # Stop if running
    task = request.app.state.discharge_tasks.get(window_id)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except Exception:
            pass

    request.app.state.windows_changed.set()


def _validate_time(time_str: str) -> None:
    """Validate HH:MM format with valid hour/minute ranges."""
    try:
        h, m = time_str.split(":")
        hour, minute = int(h), int(m)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid time format: '{time_str}'. Expected HH:MM (00:00-23:59)",
        )
