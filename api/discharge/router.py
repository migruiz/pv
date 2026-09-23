"""Discharge window endpoints: list, create, update, delete. Every change is applied straight away."""

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import require_api_key

from .controller import DischargeController
from .models import DischargeWindow, WindowSettings, WindowView
from .schedule import end_time

router = APIRouter(prefix="/discharge-windows", dependencies=[Depends(require_api_key)])


def _controller(request: Request) -> DischargeController:
    return request.app.state.discharge


def _view(controller: DischargeController, window: DischargeWindow, error: str | None = None) -> WindowView:
    warning = None
    if error:
        warning = f"Saved, but the inverter did not respond ({error}). Retrying every 30 seconds."
    return WindowView(**window.model_dump(), state=controller.state_of(window), warning=warning)


def _refuse_overlap(controller: DischargeController, settings: WindowSettings, exclude_id: str | None = None):
    other = controller.store.overlap(settings, exclude_id)
    if other is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Overlaps with '{other.name.strip()}' ({other.start_time} to {end_time(other)})",
        )


@router.get("", response_model=list[WindowView])
async def list_windows(controller: DischargeController = Depends(_controller)):
    """All windows by start time, each with what the controller is doing with it now."""
    windows = sorted(controller.store.load(), key=lambda w: w.start_time)
    return [_view(controller, w) for w in windows]


@router.post("", response_model=WindowView, status_code=201)
async def create_window(settings: WindowSettings, controller: DischargeController = Depends(_controller)):
    """Create a window. If it covers the current time, discharging starts before this returns."""
    _refuse_overlap(controller, settings)
    window = controller.store.add(settings)
    error = await controller.refresh(window.id)
    return _view(controller, window, error)


@router.put("/{window_id}", response_model=WindowView)
async def update_window(
    window_id: str, settings: WindowSettings, controller: DischargeController = Depends(_controller),
):
    """Replace a window's settings. The change applies straight away, also to a running discharge."""
    if controller.store.get(window_id) is None:
        raise HTTPException(status_code=404, detail="Window not found")
    _refuse_overlap(controller, settings, exclude_id=window_id)
    window = controller.store.replace(window_id, settings)
    error = await controller.refresh(window_id)
    return _view(controller, window, error)


@router.delete("/{window_id}", status_code=204)
async def delete_window(window_id: str, controller: DischargeController = Depends(_controller)):
    """Delete a window. A discharge it was running stops first; if it cannot, the window is kept."""
    if controller.store.get(window_id) is None:
        raise HTTPException(status_code=404, detail="Window not found")
    error = await controller.delete(window_id)
    if error:
        raise HTTPException(
            status_code=502,
            detail=f"Could not stop the discharge ({error}), so the window was not deleted. Try again.",
        )
