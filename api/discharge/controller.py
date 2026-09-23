"""The one rule: discharge while an enabled window is running and the battery is above its target.

check() applies the rule. It runs when a window starts or ends, every few minutes while discharging to
correct the power, and straight after every change to the windows, so the saved windows are the only
instruction. Nothing is kept on disk: after a restart the next check simply applies the rule again.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime

import notifications
from config import MOCK_MODE
from inverter.reader import InverterUnavailable
from mock_clock import TZ, get_now

from . import commands
from .models import DischargeWindow, WindowState
from .power import calc_discharge_power
from .schedule import current_run, next_change
from .store import WindowStore

logger = logging.getLogger("pv.discharge")

CORRECTION_INTERVAL = 30 if MOCK_MODE else 300  # seconds between power corrections while discharging
RETRY_INTERVAL = 30                             # seconds, after a failed battery read or command
MAX_SLEEP = 3600                                # re-check at least hourly, whatever the windows say
FIRST_READING_WAIT = 30                         # seconds to wait for the inverter's first reading at startup


@dataclass
class Discharge:
    """What the inverter was last told to do."""

    window_id: str
    window_name: str
    end: datetime
    power_kw: float
    soc: float
    notified: bool = False


class DischargeController:
    def __init__(self, store: WindowStore, inverter, clock=get_now):
        self.store = store
        self._inverter = inverter
        self._clock = clock
        self._lock = asyncio.Lock()
        self._push_lock = asyncio.Lock()
        self._replan = asyncio.Event()
        self._current: Discharge | None = None
        # The inverter may be force-discharging without a confirmed command: true at startup (a discharge
        # from before a restart carries on until its period ends) and from any discharge write, even one
        # whose reply was lost. Only a confirmed stop clears it.
        self._maybe_discharging = True
        # Window id -> start of the run that reached its target: done until its next run
        self._target_reached: dict[str, datetime] = {}
        self._retry = False
        # When the last check read the clock: the next check is planned from there, so a start or end
        # that passes while a check is held up (a slow write) is caught at once, never skipped
        self._checked_at: datetime | None = None
        # Push notifications decided under the lock, then sent in the background, one at a time in order
        self._outbox: list[tuple] = []
        self._push_tasks: set[asyncio.Task] = set()

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------

    async def run(self) -> None:
        for _ in range(FIRST_READING_WAIT):
            if self._inverter.age() is not None:
                break
            await asyncio.sleep(1)
        while True:
            await self.check()
            # Sleep until the next check is due. A change to the windows runs its own check and
            # wakes this loop only to plan the sleep again, since a start or end may have moved.
            while True:
                self._replan.clear()
                try:
                    await asyncio.wait_for(self._replan.wait(), timeout=self.seconds_to_next_check())
                except asyncio.TimeoutError:
                    break

    async def refresh(self, changed_window_id: str | None = None) -> str | None:
        """Apply the rule now. A window that was just saved gets a fresh go even if it reached its target.

        Returns why the inverter could not be brought in line (it is retried shortly), or None.
        """
        if changed_window_id is not None:
            self._target_reached.pop(changed_window_id, None)
        error = await self.check()
        self._replan.set()
        return error

    async def delete(self, window_id: str) -> str | None:
        """Delete a window, first stopping the discharge it is running, then apply the rule.

        Returns why the stop failed, or None. On a failure the window is kept: the discharge would carry
        on with nothing in the app to show it. All under the lock, so no check can restart the discharge
        between the stop and the delete.
        """
        async with self._lock:
            error = None
            try:
                window = self.store.get(window_id)
                confirmed = self._current is not None and self._current.window_id == window_id
                # A start whose reply was lost leaves no _current, but may be this window's
                unconfirmed = (self._current is None and self._maybe_discharging and window is not None
                               and current_run([window], self._clock()) is not None)
                if confirmed or unconfirmed:
                    await self._stop("window deleted")
            except Exception as exc:
                logger.warning("Window not deleted: could not stop its discharge: %s", exc)
                self._retry, error = True, str(exc)
            else:
                self.store.delete(window_id)
                self._target_reached.pop(window_id, None)
                await self._apply_logged()
            outbox, self._outbox = self._outbox, []
        self._send_pushes(outbox)
        self._replan.set()
        return error

    def seconds_to_next_check(self) -> float:
        now = self._clock()
        since = self._checked_at or now
        delays = [MAX_SLEEP]
        if self._retry:
            delays.append(RETRY_INTERVAL)
        if self._current is not None:
            delays.append(CORRECTION_INTERVAL)
        try:
            upcoming = next_change(self.store.load(), since)
        except Exception:
            logger.exception("Could not read the discharge windows")
            upcoming = None
            delays.append(RETRY_INTERVAL)
        if upcoming is not None:
            delays.append((upcoming - now).total_seconds())
        return max(0.5, min(delays))

    # ------------------------------------------------------------------
    # The rule
    # ------------------------------------------------------------------

    async def check(self) -> str | None:
        """Apply the rule once. Never raises: returns why it failed (retried shortly), or None."""
        async with self._lock:
            error = await self._apply_logged()
            outbox, self._outbox = self._outbox, []
        # In the background: a stalled push must never hold up a stop, a reply or the next check
        self._send_pushes(outbox)
        return error

    async def _apply_logged(self) -> str | None:
        """_apply, with a failure logged and a retry planned instead of raised. Call under the lock."""
        try:
            now = self._checked_at = self._clock()
            await self._apply(now)
            self._retry = False
            return None
        except InverterUnavailable as exc:
            logger.warning("Discharge check postponed: %s", exc)
            error = str(exc)
        except Exception as exc:
            logger.exception("Discharge check failed")
            error = str(exc)
        self._retry = True
        return error

    async def _apply(self, now: datetime) -> None:
        run = current_run(self.store.load(), now)
        if run is not None and self._target_reached.get(run.window.id) == run.start:
            run = None

        if self._current is not None and (run is None or run.window.id != self._current.window_id):
            await self._stop("window ended" if now >= self._current.end else "window changed")
        if run is None:
            if self._maybe_discharging:
                await self._stop("no window running")
            return

        window = run.window
        soc = float(self._inverter.dashboard()["battery_soc"])
        minutes_left = (run.end - now).total_seconds() / 60
        power_kw = calc_discharge_power(soc, minutes_left, window.target_soc)
        if power_kw is None:
            self._target_reached[window.id] = run.start
            logger.info("'%s': battery at %.0f%%, at or below its %.0f%% target: done for today",
                        window.name, soc, window.target_soc)
            if self._current is not None or self._maybe_discharging:
                await self._stop(f"target reached ({soc:.0f}%)")
            return

        self._maybe_discharging = True
        await self._inverter.write(commands.discharge(power_kw, minutes_left))
        previous = self._current
        self._current = Discharge(window.id, window.name, run.end, power_kw, soc,
                                  notified=previous.notified if previous else False)
        logger.info("'%s': battery %.0f%%, discharging at %.3f kW, %.0f min left",
                    window.name, soc, power_kw, minutes_left)
        self._notify_progress(window, minutes_left)

    async def _stop(self, reason: str) -> None:
        await self._inverter.write(commands.stop())
        self._maybe_discharging = False
        stopped, self._current = self._current, None
        if stopped is None:
            logger.info("Sent stop to be sure the battery is not force-discharging (%s)", reason)
            return
        logger.info("'%s': stopped discharging, %s", stopped.window_name, reason)
        if stopped.notified:
            self._outbox.append((notifications.notify_discharge_stopped, (reason,), stopped.window_name))

    def _notify_progress(self, window: DischargeWindow, minutes_left: float) -> None:
        current = self._current
        args = (current.soc, current.power_kw, minutes_left)
        if window.notify and not current.notified:
            self._outbox.append((notifications.notify_discharge_started, args, window.name))
            current.notified = True
        elif window.notify:
            self._outbox.append((notifications.notify_discharge_update, args, window.name))
        elif current.notified:
            # Notifications switched off mid-discharge: clear the ongoing notification on the phone
            self._outbox.append((notifications.notify_discharge_stopped, ("notifications off",), window.name))
            current.notified = False

    def _send_pushes(self, outbox: list[tuple]) -> None:
        if outbox:
            task = asyncio.create_task(self._push(outbox))
            self._push_tasks.add(task)
            task.add_done_callback(self._push_tasks.discard)

    async def _push(self, outbox: list[tuple]) -> None:
        """Send push notifications one at a time, each to completion, in the order they were decided.

        Tasks start in the order they were created and the lock is first come, first served, so a
        "stopped" can never overtake the "started" before it. Each send is a blocking HTTPS call, run off
        the event loop and bounded by the Firebase client's own timeout (notifications.py).
        """
        async with self._push_lock:
            for notify, args, window_name in outbox:
                try:
                    await asyncio.to_thread(notify, *args, window_name=window_name)
                except Exception:
                    logger.exception("Push notification for '%s' failed", window_name)

    async def settle(self) -> None:
        """Wait for the push notifications already decided to be sent (used by tests)."""
        while self._push_tasks:
            await asyncio.gather(*self._push_tasks)

    # ------------------------------------------------------------------
    # State shown in the app
    # ------------------------------------------------------------------

    def state_of(self, window: DischargeWindow) -> WindowState:
        now = self._clock()
        current = self._current
        if current is not None and current.window_id == window.id:
            return WindowState(
                discharging=True,
                power_kw=round(current.power_kw, 3),
                soc=current.soc,
                minutes_remaining=round(max(0.0, (current.end - now).total_seconds() / 60), 1),
                ends_at=current.end.astimezone(TZ).isoformat(),
            )
        run = current_run([window], now)
        return WindowState(target_reached=run is not None and self._target_reached.get(window.id) == run.start)
