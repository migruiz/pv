"""Tests for charge window config store CRUD and overlap detection."""

import pytest

from charge_windows import config_store
from charge_windows.models import ChargeWindow, ChargeWindowCreate, ChargeWindowUpdate
from discharge import config_store as discharge_store
from discharge.models import DischargeWindow, DischargeWindowCreate


class TestCRUD:
    def test_empty_by_default(self, charge_config_path):
        windows = config_store.load_windows()
        assert windows == []

    def test_add_window(self, charge_config_path):
        create = ChargeWindowCreate(
            name="Test Charge",
            start_time="10:00",
            start_power=200,
            peak_time="12:00",
            peak_power=2500,
            end_time="14:00",
            end_power=200,
        )
        window = config_store.add_window(create)
        assert window.name == "Test Charge"
        assert len(window.id) == 8

        loaded = config_store.load_windows()
        assert len(loaded) == 1
        assert loaded[0].id == window.id

    def test_get_window(self, charge_config_path):
        create = ChargeWindowCreate(
            name="Test",
            start_time="10:00", start_power=200,
            peak_time="12:00", peak_power=2500,
            end_time="14:00", end_power=200,
        )
        window = config_store.add_window(create)
        found = config_store.get_window(window.id)
        assert found is not None
        assert found.name == "Test"

    def test_get_window_not_found(self, charge_config_path):
        assert config_store.get_window("nonexist") is None

    def test_update_window(self, charge_config_path):
        create = ChargeWindowCreate(
            name="Original",
            start_time="10:00", start_power=200,
            peak_time="12:00", peak_power=2500,
            end_time="14:00", end_power=200,
        )
        window = config_store.add_window(create)

        updated = config_store.update_window(
            window.id,
            ChargeWindowUpdate(name="Updated", peak_power=2000),
        )
        assert updated is not None
        assert updated.name == "Updated"
        assert updated.peak_power == 2000
        # Unchanged fields preserved
        assert updated.start_power == 200
        assert updated.end_power == 200

    def test_update_window_not_found(self, charge_config_path):
        result = config_store.update_window("nonexist", ChargeWindowUpdate(name="X"))
        assert result is None

    def test_delete_window(self, charge_config_path):
        create = ChargeWindowCreate(
            name="ToDelete",
            start_time="10:00", start_power=200,
            peak_time="12:00", peak_power=2500,
            end_time="14:00", end_power=200,
        )
        window = config_store.add_window(create)
        assert config_store.delete_window(window.id) is True
        assert config_store.load_windows() == []

    def test_delete_window_not_found(self, charge_config_path):
        assert config_store.delete_window("nonexist") is False


class TestDurationMinutes:
    def test_simple_duration(self):
        w = ChargeWindow(
            id="t1", name="T",
            start_time="10:00", start_power=200,
            peak_time="12:00", peak_power=2500,
            end_time="14:00", end_power=200,
        )
        assert w.duration_minutes == 240  # 4 hours

    def test_midnight_crossing(self):
        w = ChargeWindow(
            id="t2", name="T",
            start_time="22:00", start_power=200,
            peak_time="00:00", peak_power=2500,
            end_time="02:00", end_power=200,
        )
        assert w.duration_minutes == 240  # 4 hours


class TestSameTypeOverlap:
    def test_no_overlap(self, charge_config_path):
        w1 = ChargeWindowCreate(
            name="Morning",
            start_time="08:00", start_power=200,
            peak_time="09:00", peak_power=2500,
            end_time="10:00", end_power=200,
        )
        config_store.add_window(w1)

        w2 = ChargeWindowCreate(
            name="Afternoon",
            start_time="14:00", start_power=200,
            peak_time="15:00", peak_power=2500,
            end_time="16:00", end_power=200,
        )
        assert config_store.check_overlap(w2) is None

    def test_overlap_detected(self, charge_config_path):
        w1 = ChargeWindowCreate(
            name="Morning",
            start_time="10:00", start_power=200,
            peak_time="12:00", peak_power=2500,
            end_time="14:00", end_power=200,
        )
        config_store.add_window(w1)

        w2 = ChargeWindowCreate(
            name="Overlap",
            start_time="13:00", start_power=200,
            peak_time="14:00", peak_power=2500,
            end_time="15:00", end_power=200,
        )
        conflict = config_store.check_overlap(w2)
        assert conflict is not None
        assert conflict.name == "Morning"

    def test_overlap_disabled_window_ignored(self, charge_config_path):
        w1 = ChargeWindowCreate(
            name="Disabled",
            start_time="10:00", start_power=200,
            peak_time="12:00", peak_power=2500,
            end_time="14:00", end_power=200,
            enabled=False,
        )
        config_store.add_window(w1)

        w2 = ChargeWindowCreate(
            name="Same time",
            start_time="10:00", start_power=200,
            peak_time="12:00", peak_power=2500,
            end_time="14:00", end_power=200,
        )
        assert config_store.check_overlap(w2) is None

    def test_overlap_exclude_self(self, charge_config_path):
        w = config_store.add_window(ChargeWindowCreate(
            name="Self",
            start_time="10:00", start_power=200,
            peak_time="12:00", peak_power=2500,
            end_time="14:00", end_power=200,
        ))
        # Updating itself should not conflict
        assert config_store.check_overlap(w, exclude_id=w.id) is None


class TestCrossTypeOverlap:
    def test_charge_overlaps_discharge(self, charge_config_path, config_path):
        """A charge window should detect overlap with a discharge window."""
        # Create a discharge window
        discharge_store.save_windows([DischargeWindow(
            id="dw01",
            name="Night Export",
            start_time="22:00",
            duration_minutes=240,
            target_soc=0,
            notify=True,
            enabled=True,
        )])

        # Try to create a charge window that overlaps
        charge = ChargeWindowCreate(
            name="Late Night",
            start_time="23:00", start_power=200,
            peak_time="00:00", peak_power=2500,
            end_time="01:00", end_power=200,
        )
        conflict = config_store.check_overlap(charge)
        assert conflict is not None
        assert conflict.name == "Night Export"

    def test_no_cross_type_overlap(self, charge_config_path, config_path):
        """No conflict when windows don't overlap."""
        discharge_store.save_windows([DischargeWindow(
            id="dw01",
            name="Night Export",
            start_time="22:00",
            duration_minutes=240,
            target_soc=0,
            notify=True,
            enabled=True,
        )])

        charge = ChargeWindowCreate(
            name="Midday",
            start_time="10:00", start_power=200,
            peak_time="12:00", peak_power=2500,
            end_time="14:00", end_power=200,
        )
        assert config_store.check_overlap(charge) is None

    def test_discharge_overlaps_charge(self, charge_config_path, config_path):
        """A discharge window should detect overlap with a charge window."""
        config_store.add_window(ChargeWindowCreate(
            name="Midday Charge",
            start_time="10:00", start_power=200,
            peak_time="12:00", peak_power=2500,
            end_time="14:00", end_power=200,
        ))

        discharge_candidate = DischargeWindowCreate(
            name="Afternoon",
            start_time="13:00",
            duration_minutes=120,
            target_soc=10,
        )
        conflict = discharge_store.check_overlap(discharge_candidate)
        assert conflict is not None


class TestActiveStatePersistence:
    def test_save_and_load_active(self, charge_config_path, tmp_path):
        """Active state persists and loads correctly."""
        window = ChargeWindow(
            id="test01", name="Test",
            start_time="10:00", start_power=200,
            peak_time="12:00", peak_power=2500,
            end_time="14:00", end_power=200,
        )
        config_store.save_active("test01", "2026-03-30T10:00:00", window)

        result = config_store.load_active("test01")
        assert result is not None
        start_iso, loaded = result
        assert start_iso == "2026-03-30T10:00:00"
        assert loaded.name == "Test"

    def test_load_active_not_found(self, charge_config_path):
        assert config_store.load_active("nonexist") is None

    def test_clear_active(self, charge_config_path):
        window = ChargeWindow(
            id="test01", name="Test",
            start_time="10:00", start_power=200,
            peak_time="12:00", peak_power=2500,
            end_time="14:00", end_power=200,
        )
        config_store.save_active("test01", "2026-03-30T10:00:00", window)
        config_store.clear_active("test01")
        assert config_store.load_active("test01") is None
