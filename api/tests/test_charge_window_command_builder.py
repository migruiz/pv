"""Tests for charge window FusionSolar signal payload construction."""

import json

from charge_windows.command_builder import (
    SIGNALS,
    TOU_WINDOWS_VALUE,
    build_power_update_command,
    build_restore_command,
    build_start_command,
)


class TestBuildStartCommand:
    def test_signal_count(self):
        signals = build_start_command(200)
        assert len(signals) == 3

    def test_sets_self_consumption_mode(self):
        signals = build_start_command(200)
        by_id = {s["id"]: s["value"] for s in signals}
        assert by_id[SIGNALS["operation_mode"]] == "2"

    def test_disables_ac_charge(self):
        signals = build_start_command(200)
        by_id = {s["id"]: s["value"] for s in signals}
        assert by_id[SIGNALS["charge_from_ac"]] == "0"

    def test_sets_initial_power(self):
        signals = build_start_command(200)
        by_id = {s["id"]: s["value"] for s in signals}
        assert by_id[SIGNALS["max_charge_power"]] == "200"

    def test_custom_power(self):
        signals = build_start_command(1500)
        by_id = {s["id"]: s["value"] for s in signals}
        assert by_id[SIGNALS["max_charge_power"]] == "1500"


class TestBuildPowerUpdateCommand:
    def test_single_signal(self):
        signals = build_power_update_command(1200)
        assert len(signals) == 1

    def test_updates_max_charge_power(self):
        signals = build_power_update_command(1200)
        assert signals[0]["id"] == SIGNALS["max_charge_power"]
        assert signals[0]["value"] == "1200"


class TestBuildRestoreCommand:
    def test_signal_count(self):
        signals = build_restore_command()
        assert len(signals) == 4

    def test_restores_tou_mode(self):
        signals = build_restore_command()
        by_id = {s["id"]: s["value"] for s in signals}
        assert by_id[SIGNALS["operation_mode"]] == "5"

    def test_enables_ac_charge(self):
        signals = build_restore_command()
        by_id = {s["id"]: s["value"] for s in signals}
        assert by_id[SIGNALS["charge_from_ac"]] == "1"

    def test_restores_max_power(self):
        signals = build_restore_command()
        by_id = {s["id"]: s["value"] for s in signals}
        assert by_id[SIGNALS["max_charge_power"]] == "2500"

    def test_includes_tou_windows(self):
        signals = build_restore_command()
        by_id = {s["id"]: s["value"] for s in signals}
        windows_val = by_id[SIGNALS["tou_windows"]]
        windows = json.loads(windows_val)
        assert len(windows) == 2
        assert windows[0]["startTime"] == "02:05"
        assert windows[0]["endTime"] == "04:55"
