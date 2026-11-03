"""Where spare solar goes: into the battery below the daytime target, to the grid at or above it.

check() switches the inverter's operation mode from the battery % and the saved target every 30 s, and
straight after a save:

- below the target, Maximum self-consumption: solar the house does not use fills the battery;
- at or above it, TOU, with TOU's "excess PV energy" setting on fed to grid: spare solar is exported.

TOU's own "charge" setting is not used: on 3 Nov 2026 the inverter ignored it all morning (read back as
charge, battery idle, spare solar exported), while self-consumption charged at once. In either mode the
battery keeps powering the house, and the grid never charges it by day: only TOU's charge period at
night does.

Self-consumption only between 08:00 and 23:00. From 23:00 to 08:00 the inverter is always in TOU, so
the 02:01 grid charge runs and the full battery is held until 08:00 while the house runs on the night
rate; a mode changed by hand is put back within 30 s at any hour.

Discharge windows come first: for the whole of a window's run, even once it has reached its target,
the inverter is in TOU with spare solar to the grid, so solar never refills what the window is emptying.
A mode change while a window runs asks the discharge controller to check at once, in case the change
cancelled its forced discharge.

If the API or the hotspot link dies, the mode stays where it was. In TOU nothing is lost. In
self-consumption the battery fills to 100 % and, until the API is back, the night grid charge does not
run (the battery powers the house through the night instead).
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, time

from huawei_solar.register_values import StorageExcessPvEnergyUseInTOU, StorageWorkingModesC

from discharge.schedule import current_run
from discharge.store import WindowStore
from inverter.reader import InverterUnavailable
from mock_clock import TZ, get_now

from .store import TargetStore

logger = logging.getLogger("pv.target")

CHECK_INTERVAL = 30       # seconds: at the full 2.5 kW, the battery gains about 0.4% in that time
GAP = 5                   # % below the target at which spare solar goes back into the battery
DAYTIME = (time(8, 0), time(23, 0))  # Dublin time: self-consumption allowed; TOU outside, for the night charge
FIRST_READING_WAIT = 30   # seconds to wait for the inverter's first reading at startup

EXCESS_PV = "storage_excess_pv_energy_use_in_tou"
WORKING_MODE = "storage_working_mode_settings"
TOU = StorageWorkingModesC.TIME_OF_USE_LUNA2000
SELF_CONSUMPTION = StorageWorkingModesC.MAXIMISE_SELF_CONSUMPTION
MODE_NAMES = {TOU: "TOU", SELF_CONSUMPTION: "Maximum self-consumption"}


def resume_below(target: int) -> int:
    """The battery % at which spare solar goes back into the battery, once the target was reached."""
    return max(target - GAP, 0)


def spare_solar_to_battery(soc: float, target: int, to_battery_now: bool, fresh: bool) -> bool:
    """Whether spare solar should charge the battery.

    At or above the target it goes to the grid. It goes back into the battery only once the battery has
    dropped GAP% below the target (80% target: at 75%), so the setting changes a few times a day, not
    every time the house draws a little. Right after a save there is no gap: a battery anywhere below the
    new target charges.
    """
    if target <= 0:
        return False
    if target >= 100:
        return True
    if soc >= target:
        return False
    if fresh or soc <= resume_below(target):
        return True
    return to_battery_now


class DaytimeTargetController:
    def __init__(self, store: TargetStore, windows: WindowStore, inverter, clock=get_now,
                 on_mode_change_in_window: Callable[[], Awaitable] | None = None):
        self.store = store
        self._on_mode_change_in_window = on_mode_change_in_window
        self._windows = windows
        self._inverter = inverter
        self._clock = clock
        self._lock = asyncio.Lock()
        self._fresh = False  # a target was just saved: ignore the gap once
        self._error: str | None = None

    def window_running(self) -> bool:
        """Whether a discharge window is running now, holding the target back."""
        return current_run(self._windows.load(), self._clock()) is not None

    async def run(self) -> None:
        for _ in range(FIRST_READING_WAIT):
            if self._inverter.age() is not None:
                break
            await asyncio.sleep(1)
        while True:
            await self.check()
            await asyncio.sleep(CHECK_INTERVAL)

    async def save(self, target_soc: int) -> str | None:
        """Save a new target and apply it now. Returns why the inverter could not be set (retried), or None."""
        async with self._lock:
            self.store.save(target_soc)
            self._fresh = True
            return await self._apply_logged()

    async def check(self) -> str | None:
        """Apply the rule once. Never raises: returns why it failed (retried in 30 s), or None."""
        async with self._lock:
            return await self._apply_logged()

    async def _apply_logged(self) -> str | None:
        """_apply, with a failure logged and returned instead of raised. Call under the lock."""
        try:
            await self._apply(self._clock())
        except Exception as exc:
            error = str(exc)
            # Once when trouble starts, not every 30 s while the inverter is unreachable
            if error != self._error:
                if isinstance(exc, InverterUnavailable):
                    logger.warning("Daytime target check postponed: %s", exc)
                else:
                    logger.exception("Daytime target check failed")
            self._error = error
            return error
        if self._error is not None:
            logger.info("Daytime target check working again")
            self._error = None
        return None

    async def _apply(self, now: datetime) -> None:
        reading = self._inverter.dashboard()
        target = self.store.load()
        soc = float(reading["battery_soc"])
        mode = reading["operation_mode"]
        to_battery_now = bool(reading["spare_solar_to_battery"])  # self-consumption, or TOU set to charge

        start, end = DAYTIME
        window = current_run(self._windows.load(), now)
        if not start <= now.astimezone(TZ).time() < end:
            wanted, reason = False, "night (TOU from 23:00 to 08:00)"
        elif window is not None:
            wanted, reason = False, f"discharge window '{window.window.name.strip()}' is running"
        else:
            wanted = spare_solar_to_battery(soc, target, to_battery_now, self._fresh)
            reason = f"daytime target {target}%"

        if wanted:
            settings = [] if mode == SELF_CONSUMPTION else [(WORKING_MODE, SELF_CONSUMPTION)]
        else:
            settings = [] if mode == TOU else [(WORKING_MODE, TOU)]
            if settings or to_battery_now:  # TOU's own setting goes to the grid too
                settings.append((EXCESS_PV, StorageExcessPvEnergyUseInTOU.FED_TO_GRID))
        if settings:
            await self._inverter.write(settings)
            new_mode = SELF_CONSUMPTION if wanted else TOU
            was = "" if mode == new_mode else f", was {MODE_NAMES.get(mode, f'mode {mode}')}"
            logger.info("Battery %.0f%%, %s: spare solar now goes to the %s (%s%s)",
                        soc, reason, "battery" if wanted else "grid", MODE_NAMES[new_mode], was)
            if window is not None and mode != new_mode and self._on_mode_change_in_window is not None:
                await self._on_mode_change_in_window()
        self._fresh = False
