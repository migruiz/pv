"""Tests for discharge power calculation (pure functions)."""

import pytest

from discharge.power_calculator import (
    BATTERY_REAL_CAPACITY_KWH,
    MAX_DISCHARGE_POWER_KW,
    calc_discharge_power,
    remaining_energy_kwh,
)


class TestCalcDischargePower:
    def test_normal_discharge(self):
        # SOC=80, 240min, target=0 → (80/100 * 4.8) / 4.0 = 0.96 kW
        power = calc_discharge_power(80, 240, 0)
        assert power == pytest.approx(0.96)

    def test_max_power_cap(self):
        # SOC=95, 30min, target=0 → huge power, capped at 2.5 kW
        power = calc_discharge_power(95, 30, 0)
        assert power == MAX_DISCHARGE_POWER_KW

    def test_soc_at_target(self):
        assert calc_discharge_power(10, 60, 10) is None

    def test_soc_below_target(self):
        assert calc_discharge_power(5, 60, 10) is None

    def test_zero_time_remaining(self):
        assert calc_discharge_power(80, 0, 0) is None

    def test_negative_time_remaining(self):
        assert calc_discharge_power(80, -5, 0) is None

    def test_small_delta(self):
        # SOC=11, 120min, target=10 → (1/100 * 4.8) / 2.0 = 0.024 kW
        power = calc_discharge_power(11, 120, 10)
        assert power is not None
        assert power == pytest.approx(0.024)

    def test_half_battery_one_hour(self):
        # SOC=50, 60min, target=0 → (50/100 * 4.8) / 1.0 = 2.4 kW
        power = calc_discharge_power(50, 60, 0)
        assert power == pytest.approx(2.4)

    def test_full_battery_short_window(self):
        # SOC=100, 60min, target=0 → 4.8 / 1.0 = 4.8 → capped at 2.5
        power = calc_discharge_power(100, 60, 0)
        assert power == MAX_DISCHARGE_POWER_KW

    def test_non_zero_target(self):
        # SOC=80, 120min, target=20 → (60/100 * 4.8) / 2.0 = 1.44 kW
        power = calc_discharge_power(80, 120, 20)
        assert power == pytest.approx(1.44)


class TestRemainingEnergy:
    def test_full_discharge(self):
        # SOC=80, target=0 → 0.8 * 4.8 = 3.84
        assert remaining_energy_kwh(80, 0) == pytest.approx(3.84)

    def test_at_target(self):
        assert remaining_energy_kwh(10, 10) == pytest.approx(0.0)

    def test_below_target(self):
        # SOC below target returns 0 (clamped by max)
        assert remaining_energy_kwh(5, 10) == pytest.approx(0.0)

    def test_full_battery(self):
        assert remaining_energy_kwh(100, 0) == pytest.approx(BATTERY_REAL_CAPACITY_KWH)

    def test_partial(self):
        # SOC=50, target=20 → (30/100) * 4.8 = 1.44
        assert remaining_energy_kwh(50, 20) == pytest.approx(1.44)
