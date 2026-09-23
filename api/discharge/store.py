"""The saved windows: a small JSON file on the Docker volume, replaced atomically on every change."""

import json
import os
import uuid
from pathlib import Path

from .models import DischargeWindow, WindowSettings
from .schedule import minutes_of_day


class WindowStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> list[DischargeWindow]:
        """All windows. A missing file means none; an unreadable one raises rather than losing them."""
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text())
        return [DischargeWindow(**w) for w in data.get("windows", [])]

    def get(self, window_id: str) -> DischargeWindow | None:
        return next((w for w in self.load() if w.id == window_id), None)

    def add(self, settings: WindowSettings) -> DischargeWindow:
        window = DischargeWindow(id=uuid.uuid4().hex[:8], **settings.model_dump())
        self._save([*self.load(), window])
        return window

    def replace(self, window_id: str, settings: WindowSettings) -> DischargeWindow | None:
        windows = self.load()
        for i, w in enumerate(windows):
            if w.id == window_id:
                windows[i] = DischargeWindow(id=window_id, **settings.model_dump())
                self._save(windows)
                return windows[i]
        return None

    def delete(self, window_id: str) -> bool:
        windows = self.load()
        kept = [w for w in windows if w.id != window_id]
        if len(kept) == len(windows):
            return False
        self._save(kept)
        return True

    def overlap(self, settings: WindowSettings, exclude_id: str | None = None) -> DischargeWindow | None:
        """The first other enabled window sharing a minute of the day with these settings, if enabled."""
        if not settings.enabled:
            return None
        minutes = minutes_of_day(DischargeWindow(id="", **settings.model_dump()))
        for w in self.load():
            if w.enabled and w.id != exclude_id and minutes & minutes_of_day(w):
                return w
        return None

    def _save(self, windows: list[DischargeWindow]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"windows": [w.model_dump() for w in windows]}, indent=2))
        os.replace(tmp, self.path)
