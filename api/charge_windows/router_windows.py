"""CRUD REST endpoints for charge window configuration."""

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import require_api_key

from . import config_store
from .models import ChargeWindow, ChargeWindowCreate, ChargeWindowUpdate

router = APIRouter(
    prefix="/charge-windows",
    dependencies=[Depends(require_api_key)],
)


@router.get("", response_model=list[ChargeWindow])
async def list_windows():
    """List all configured charge windows."""
    return config_store.load_windows()


@router.get("/{window_id}", response_model=ChargeWindow)
async def get_window(window_id: str):
    """Get a single charge window by ID."""
    window = config_store.get_window(window_id)
    if window is None:
        raise HTTPException(status_code=404, detail=f"Charge window {window_id} not found")
    return window


@router.post("", response_model=ChargeWindow, status_code=201)
async def create_window(body: ChargeWindowCreate, request: Request):
    """Create a new charge window."""
    _validate_time(body.start_time, "start_time")
    _validate_time(body.peak_time, "peak_time")
    _validate_time(body.end_time, "end_time")

    conflict = config_store.check_overlap(body)
    if conflict:
        name = getattr(conflict, "name", "unknown")
        raise HTTPException(
            status_code=409,
            detail=f"Overlaps with window '{name}'",
        )

    window = config_store.add_window(body)
    request.app.state.charge_windows_changed.set()
    return window


@router.put("/{window_id}", response_model=ChargeWindow)
async def update_window(window_id: str, body: ChargeWindowUpdate, request: Request):
    """Update a charge window (partial update)."""
    existing = config_store.get_window(window_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Charge window {window_id} not found")

    for field in ("start_time", "peak_time", "end_time"):
        value = getattr(body, field, None)
        if value is not None:
            _validate_time(value, field)

    # Build a merged candidate for overlap checking
    merged = existing.model_dump()
    for key, value in body.model_dump(exclude_unset=True).items():
        merged[key] = value
    candidate = ChargeWindow(**merged)

    if candidate.enabled:
        conflict = config_store.check_overlap(candidate, exclude_id=window_id)
        if conflict:
            name = getattr(conflict, "name", "unknown")
            raise HTTPException(
                status_code=409,
                detail=f"Overlaps with window '{name}'",
            )

    updated = config_store.update_window(window_id, body)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Charge window {window_id} not found")

    request.app.state.charge_windows_changed.set()
    return updated


@router.delete("/{window_id}", status_code=204)
async def delete_window(window_id: str, request: Request):
    """Delete a charge window."""
    # Stop if running
    scheduler = request.app.state.charge_scheduler
    try:
        await scheduler.stop_window(window_id)
    except ValueError:
        pass

    if not config_store.delete_window(window_id):
        raise HTTPException(status_code=404, detail=f"Charge window {window_id} not found")

    request.app.state.charge_windows_changed.set()


def _validate_time(time_str: str, field_name: str = "time") -> None:
    """Validate HH:MM format with valid hour/minute ranges."""
    try:
        h, m = time_str.split(":")
        hour, minute = int(h), int(m)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid {field_name} format: '{time_str}'. Expected HH:MM (00:00-23:59)",
        )
