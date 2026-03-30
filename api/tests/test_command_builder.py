"""Tests for FusionSolar signal payload construction."""

from discharge.command_builder import SIGNALS, build_discharge_command, build_stop_command


class TestBuildDischargeCommand:
    def test_basic_discharge(self):
        signals = build_discharge_command(1.5, 120)
        assert len(signals) == 4

        by_id = {s["id"]: s["value"] for s in signals}
        assert by_id[SIGNALS["charge_discharge_mode"]] == "2"
        assert by_id[SIGNALS["setting_mode"]] == "0"
        assert by_id[SIGNALS["forced_power_kw"]] == "1.500"
        assert by_id[SIGNALS["forced_period_min"]] == "120"

    def test_max_values(self):
        signals = build_discharge_command(2.5, 1440)
        by_id = {s["id"]: s["value"] for s in signals}
        assert by_id[SIGNALS["forced_power_kw"]] == "2.500"
        assert by_id[SIGNALS["forced_period_min"]] == "1440"

    def test_power_formatted_three_decimals(self):
        signals = build_discharge_command(0.1, 60)
        by_id = {s["id"]: s["value"] for s in signals}
        assert by_id[SIGNALS["forced_power_kw"]] == "0.100"

    def test_small_power(self):
        signals = build_discharge_command(0.024, 90)
        by_id = {s["id"]: s["value"] for s in signals}
        assert by_id[SIGNALS["forced_power_kw"]] == "0.024"


class TestBuildStopCommand:
    def test_stop_command(self):
        signals = build_stop_command()
        assert len(signals) == 1
        assert signals[0]["id"] == SIGNALS["charge_discharge_mode"]
        assert signals[0]["value"] == "0"


class TestSignalIDs:
    def test_documented_signal_ids(self):
        """Verify signal IDs match the documented FusionSolar constants."""
        assert SIGNALS["charge_discharge_mode"] == "230320245"
        assert SIGNALS["forced_power_kw"] == "230320259"
        assert SIGNALS["setting_mode"] == "230320257"
        assert SIGNALS["forced_period_min"] == "230320281"
