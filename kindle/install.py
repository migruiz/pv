"""Install the solar dashboard plugin onto a USB-connected Kindle.

Close KOReader, connect the Kindle by USB, then:  python kindle/install.py [drive]
Existing device files are backed up under kindle/backups/ before being replaced.
"""
from datetime import datetime
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent
DRIVE = Path(sys.argv[1] if len(sys.argv) > 1 else "D:/")
CONFIG = ROOT / "solar-dashboard-config.json"


def copy_tree(source, target, backup):
    for item in source.rglob("*"):
        if not item.is_file():
            continue
        data = item.read_bytes()
        # The Kindle's shell and LuaJIT choke on Windows line endings.
        assert item.suffix not in {".sh", ".lua"} or b"\r\n" not in data, f"{item} has CRLF line endings"
        relative = item.relative_to(source)
        destination = target / relative
        if destination.exists():
            saved = backup / relative
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_bytes(destination.read_bytes())
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        assert destination.read_bytes() == data


def remove_stale(source, target, backup):
    """Delete device files this version no longer ships (e.g. the old suspend.sh), after backing them up."""
    if not target.is_dir():
        return
    shipped = {item.relative_to(source) for item in source.rglob("*") if item.is_file()}
    for item in target.rglob("*"):
        relative = item.relative_to(target)
        if item.is_file() and relative not in shipped:
            saved = backup / relative
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_bytes(item.read_bytes())
            item.unlink()
            print("Removed old file: " + relative.as_posix())


def main():
    assert (DRIVE / "koreader/settings.reader.lua").is_file(), "Kindle must be connected by USB with KOReader closed"
    assert CONFIG.is_file(), f"Create {CONFIG.name} from the example; token must match the API's KINDLE_TOKEN"
    config = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    config.setdefault("interval", 3)
    config.setdefault("full_refresh_every", 100)
    config.pop("power_mode", None)  # battery sleep mode was removed: the Kindle stays on mains power
    # Same constraints main.lua enforces: plain HTTP, IP address, /dashboard.png
    assert re.fullmatch(r"http://[\d.]+:\d+/dashboard\.png", config["url"]), "Invalid dashboard URL"
    assert len(config["token"]) >= 32, "Invalid dashboard token"

    backup = ROOT / "backups" / ("solar-kindle-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    backup.mkdir(parents=True)
    for name in ("settings.reader.lua", "crash.log"):
        existing = DRIVE / "koreader" / name
        if existing.is_file():
            (backup / name).write_bytes(existing.read_bytes())
    for source, target, saved in (
        (ROOT / "koreader/plugins/solardashboard.koplugin",
         DRIVE / "koreader/plugins/solardashboard.koplugin", backup / "plugin"),
        (ROOT / "extensions/solar-dashboard", DRIVE / "extensions/solar-dashboard", backup / "extension"),
    ):
        copy_tree(source, target, saved)
        remove_stale(source, target, saved)
    pairing = DRIVE / "koreader/settings/solar-dashboard.json"
    if pairing.exists():
        (backup / "solar-dashboard.json").write_bytes(pairing.read_bytes())
    pairing.write_text(json.dumps(config) + "\n", encoding="utf-8", newline="\n")
    (DRIVE / "notes/solar").mkdir(parents=True, exist_ok=True)
    assert json.loads(pairing.read_text(encoding="utf-8")) == config
    print("Solar dashboard installed: " + config["url"])
    print(f"Refresh every {config['interval']} s, full e-ink refresh every {config['full_refresh_every']} pictures")
    print("Backup: " + str(backup))


if __name__ == "__main__":
    main()
