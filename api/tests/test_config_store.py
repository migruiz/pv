"""Tests for discharge window config store (JSON CRUD + overlap detection)."""

import json

import pytest

from discharge import config_store
from discharge.models import DischargeWindow, DischargeWindowCreate, DischargeWindowUpdate


class TestLoadAndSave:
    def test_load_seeds_default_when_missing(self, config_path):
        """First load creates the file with the default Night Export window."""
        windows = config_store.load_windows()
        assert len(windows) == 1
        assert windows[0].name == "Night Export"
        assert windows[0].start_time == "22:00"
        assert windows[0].duration_minutes == 240
        assert config_path.exists()

    def test_round_trip(self, config_path):
        windows = [
            DischargeWindow(id="a", name="W1", start_time="08:00", duration_minutes=60, target_soc=10),
            DischargeWindow(id="b", name="W2", start_time="14:00", duration_minutes=120, target_soc=20),
        ]
        config_store.save_windows(windows)
        loaded = config_store.load_windows()
        assert len(loaded) == 2
        assert loaded[0].id == "a"
        assert loaded[1].id == "b"

    def test_atomic_write_no_tmp_left(self, config_path):
        """The .tmp file should not remain after save."""
        windows = [DischargeWindow(id="x", name="X", start_time="10:00", duration_minutes=30, target_soc=0)]
        config_store.save_windows(windows)
        assert not config_path.with_suffix(".tmp").exists()

    def test_load_empty_file(self, config_path):
        """Gracefully handle a corrupted/empty file."""
        config_path.write_text("")
        windows = config_store.load_windows()
        assert windows == []


class TestCRUD:
    def test_add_window(self, config_path):
        create = DischargeWindowCreate(
            name="Morning", start_time="06:00", duration_minutes=120, target_soc=10,
        )
        window = config_store.add_window(create)
        assert window.name == "Morning"
        assert len(window.id) == 8  # UUID hex[:8]

        # Verify persisted
        loaded = config_store.load_windows()
        assert any(w.id == window.id for w in loaded)

    def test_get_window(self, config_path):
        create = DischargeWindowCreate(
            name="Afternoon", start_time="14:00", duration_minutes=60, target_soc=20,
        )
        window = config_store.add_window(create)
        found = config_store.get_window(window.id)
        assert found is not None
        assert found.name == "Afternoon"

    def test_get_window_missing(self, config_path):
        # Seed the file so it exists
        config_store.load_windows()
        assert config_store.get_window("nonexistent") is None

    def test_update_window_partial(self, config_path):
        create = DischargeWindowCreate(
            name="Evening", start_time="18:00", duration_minutes=90, target_soc=30,
        )
        window = config_store.add_window(create)

        updated = config_store.update_window(
            window.id, DischargeWindowUpdate(target_soc=15),
        )
        assert updated is not None
        assert updated.target_soc == 15
        assert updated.name == "Evening"  # unchanged
        assert updated.duration_minutes == 90  # unchanged

    def test_update_window_missing(self, config_path):
        config_store.load_windows()
        assert config_store.update_window("missing", DischargeWindowUpdate(name="X")) is None

    def test_delete_window(self, config_path):
        create = DischargeWindowCreate(
            name="ToDelete", start_time="08:00", duration_minutes=30, target_soc=0,
        )
        window = config_store.add_window(create)
        assert config_store.delete_window(window.id) is True
        assert config_store.get_window(window.id) is None

    def test_delete_window_missing(self, config_path):
        config_store.load_windows()
        assert config_store.delete_window("nonexistent") is False


class TestOverlapDetection:
    def _save_window(self, config_path, **kwargs):
        """Helper to persist a window on a clean slate and return it."""
        # Ensure we start from an empty config (no seeded default)
        if not config_path.exists():
            config_store.save_windows([])
        defaults = dict(name="W", start_time="22:00", duration_minutes=240, target_soc=0, enabled=True)
        defaults.update(kwargs)
        create = DischargeWindowCreate(**defaults)
        return config_store.add_window(create)

    def test_same_time_overlaps(self, config_path):
        self._save_window(config_path, name="A", start_time="22:00", duration_minutes=240)
        candidate = DischargeWindowCreate(
            name="B", start_time="22:00", duration_minutes=120, target_soc=0,
        )
        conflict = config_store.check_overlap(candidate)
        assert conflict is not None
        assert conflict.name == "A"

    def test_midnight_crossing_overlap(self, config_path):
        # Window A: 22:00-02:00, Window B: 01:00-03:00 → overlap at 01:00-02:00
        self._save_window(config_path, name="A", start_time="22:00", duration_minutes=240)
        candidate = DischargeWindowCreate(
            name="B", start_time="01:00", duration_minutes=120, target_soc=0,
        )
        assert config_store.check_overlap(candidate) is not None

    def test_no_overlap(self, config_path):
        # 22:00-02:00 vs 08:00-10:00 → no overlap
        self._save_window(config_path, name="A", start_time="22:00", duration_minutes=240)
        candidate = DischargeWindowCreate(
            name="B", start_time="08:00", duration_minutes=120, target_soc=0,
        )
        assert config_store.check_overlap(candidate) is None

    def test_exclude_self_on_update(self, config_path):
        window = self._save_window(config_path, name="A", start_time="22:00", duration_minutes=240)
        # The window should not conflict with itself
        assert config_store.check_overlap(window, exclude_id=window.id) is None

    def test_disabled_window_ignored(self, config_path):
        self._save_window(config_path, name="A", start_time="22:00", duration_minutes=240, enabled=False)
        candidate = DischargeWindowCreate(
            name="B", start_time="22:00", duration_minutes=120, target_soc=0,
        )
        assert config_store.check_overlap(candidate) is None

    def test_adjacent_no_overlap(self, config_path):
        # 08:00-10:00 (120min) and 10:00-12:00 → no overlap (end minute is exclusive)
        self._save_window(config_path, name="A", start_time="08:00", duration_minutes=120)
        candidate = DischargeWindowCreate(
            name="B", start_time="10:00", duration_minutes=120, target_soc=0,
        )
        assert config_store.check_overlap(candidate) is None
