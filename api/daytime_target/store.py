"""The saved target: a small JSON file on the Docker volume, replaced atomically on every change."""

import json
import os
from pathlib import Path


class TargetStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> int:
        """The target battery %. A missing file means 0 (all spare solar to the grid); an unreadable one raises."""
        if not self.path.exists():
            return 0
        return int(json.loads(self.path.read_text())["target_soc"])

    def save(self, target_soc: int) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"target_soc": target_soc}, indent=2))
        os.replace(tmp, self.path)
