"""Daytime target endpoints: read it, and change it (applied before the reply)."""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from auth import require_api_key

from .controller import DaytimeTargetController, resume_below

router = APIRouter(prefix="/daytime-target", dependencies=[Depends(require_api_key)])


class TargetSettings(BaseModel):
    """0 sends all spare solar to the grid; 100 puts all of it into the battery."""

    target_soc: int = Field(ge=0, le=100)


class TargetView(TargetSettings):
    resume_below: int  # once at the target, spare solar goes back into the battery at this %
    window_running: bool  # a discharge window is running: spare solar goes to the grid until it ends
    # Only on a save's reply: the target is saved, but the inverter did not respond yet (retried shortly)
    warning: str | None = None


def _view(controller: DaytimeTargetController, target_soc: int, error: str | None = None) -> TargetView:
    warning = None
    if error:
        warning = f"Saved, but the inverter did not respond ({error}). Retrying every 30 seconds."
    return TargetView(target_soc=target_soc, resume_below=resume_below(target_soc),
                      window_running=controller.window_running(), warning=warning)


def _controller(request: Request) -> DaytimeTargetController:
    return request.app.state.daytime_target


@router.get("", response_model=TargetView)
async def get_target(controller: DaytimeTargetController = Depends(_controller)):
    return _view(controller, controller.store.load())


@router.put("", response_model=TargetView)
async def set_target(settings: TargetSettings, controller: DaytimeTargetController = Depends(_controller)):
    """Save the target. Where spare solar goes is set on the inverter before this returns."""
    error = await controller.save(settings.target_soc)
    return _view(controller, settings.target_soc, error)
