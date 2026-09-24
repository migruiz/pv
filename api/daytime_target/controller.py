"""Where spare solar goes: into the battery below the daytime target, to the grid at or above it.

The inverter stays in TOU mode all day. TOU's "excess PV energy" setting decides where solar the house
does not use goes: fed to the grid, or into the battery. check() sets it from the battery % and the
saved target every 30 s, and straight after a save. Either way the battery keeps powering the house, and
the grid never charges it by day: only the TOU charge period at night does.

Discharge windows come first: for the whole of a window's run, even once it has reached its target,
spare solar goes to the grid, so solar never refills what the window is emptying.

check() also keeps the night charge safe: between 02:00 and 05:00, an inverter switched out of TOU mode
(by hand, in the FusionSolar app) is put back into it, so the 02:05 grid charge always runs.

Nothing depends on this running: if the API or the hotspot link dies, the setting stays where it was
(the battery takes a little more or less solar), and the TOU night charge happens anyway.
"""

import asyncio
import logging
from datetime import datetime, time

from huawei_solar.register_values import StorageExcessPvEnergyUseInTOU, StorageWorkingModesC

from discharge.schedule import current_run
from discharge.store import WindowStore
from inverter.reader import InverterUnavailable
from mock_clock import TZ, get_now

from .store import TargetStore

logger = logging.getLogger("pv.target")

CHECK_INTERVAL = 30       # seconds: at the full 2.5 kW, the battery gains about 0.4% in that time
GAP = 10                  # % below the target at which spare solar goes back into the battery
NIGHT_CHARGE = (time(2, 0), time(5, 0))  # Dublin time: the inverter must be in TOU mode for its grid charge
FIRST_READING_WAIT = 30   # seconds to wait for the inverter's first reading at startup

EXCESS_PV = "storage_excess_pv_energy_use_in_tou"
WORKING_MODE = "storage_working_mode_settings"
TOU = StorageWorkingModesC.TIME_OF_USE_LUNA2000


def resume_below(target: int) -> int:
    """The battery % at which spare solar goes back into the battery, once the target was reached."""
    return max(target - GAP, 0)


def spare_solar_to_battery(soc: float, target: int, to_battery_now: bool, fresh: bool) -> bool:
    """Whether spare solar should charge the battery.

    At or above the target it goes to the grid. It goes back into the battery only once the battery has
    dropped GAP% below the target (80% target: at 70%), so the setting changes a couple of times a day, not
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
    def __init__(self, store: TargetStore, windows: WindowStore, inverter, clock=get_now):
        self.store = store
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

        start, end = NIGHT_CHARGE
        if start <= now.astimezone(TZ).time() < end and reading["operation_mode"] != TOU:
            await self._inverter.write([(WORKING_MODE, TOU)])
            logger.warning("Inverter was in operation mode %s during the night charge: switched back to TOU",
                           reading["operation_mode"])

        target = self.store.load()
        soc = float(reading["battery_soc"])
        to_battery_now = bool(reading["spare_solar_to_battery"])
        window = current_run(self._windows.load(), now)
        if window is not None:
            wanted, reason = False, f"discharge window '{window.window.name.strip()}' is running"
        else:
            wanted = spare_solar_to_battery(soc, target, to_battery_now, self._fresh)
            reason = f"daytime target {target}%"
        if wanted != to_battery_now:
            value = StorageExcessPvEnergyUseInTOU.CHARGE if wanted else StorageExcessPvEnergyUseInTOU.FED_TO_GRID
            await self._inverter.write([(EXCESS_PV, value)])
            logger.info("Battery %.0f%%, %s: spare solar now goes to the %s",
                        soc, reason, "battery" if wanted else "grid")
        self._fresh = False
