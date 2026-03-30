"""Tests for charge ramp power calculation (pure functions)."""

import pytest

from charge_ramp.ramp_calculator import (
    MIN_POWER,
    MAX_POWER,
    calc_progress,
    calc_ramp_power,
    cosine_interpolate,
)


class TestCosineInterpolate:
    def test_at_zero(self):
        assert cosine_interpolate(100, 200, 0) == pytest.approx(100)

    def test_at_one(self):
        assert cosine_interpolate(100, 200, 1) == pytest.approx(200)

    def test_at_half(self):
        assert cosine_interpolate(100, 200, 0.5) == pytest.approx(150)

    def test_ease_in_out(self):
        # Quarter should be closer to start (ease-in)
        quarter = cosine_interpolate(0, 100, 0.25)
        assert quarter < 50
        assert quarter > 0
        # Three-quarter should be closer to end (ease-out)
        three_quarter = cosine_interpolate(0, 100, 0.75)
        assert three_quarter > 50
        assert three_quarter < 100


class TestCalcRampPower:
    def test_at_start(self):
        assert calc_ramp_power(0.0, 200, 2500, 200) == 200

    def test_at_midpoint(self):
        assert calc_ramp_power(0.5, 200, 2500, 200) == 2500

    def test_at_end(self):
        assert calc_ramp_power(1.0, 200, 2500, 200) == 200

    def test_at_quarter(self):
        # Cosine interpolation: midpoint of first half
        power = calc_ramp_power(0.25, 200, 2500, 200)
        assert 200 < power < 2500
        # Should be at the halfway point of the cosine ease
        assert power == pytest.approx(1350)

    def test_at_three_quarter(self):
        power = calc_ramp_power(0.75, 200, 2500, 200)
        assert 200 < power < 2500
        assert power == pytest.approx(1350)

    def test_symmetric_curve(self):
        # With initial=final, quarter and three-quarter should be equal
        q1 = calc_ramp_power(0.25, 200, 2500, 200)
        q3 = calc_ramp_power(0.75, 200, 2500, 200)
        assert q1 == q3

    def test_asymmetric_curve(self):
        # initial=200, top=2500, final=500
        at_start = calc_ramp_power(0.0, 200, 2500, 500)
        at_mid = calc_ramp_power(0.5, 200, 2500, 500)
        at_end = calc_ramp_power(1.0, 200, 2500, 500)
        assert at_start == 200
        assert at_mid == 2500
        assert at_end == 500

    def test_monotonic_first_half(self):
        powers = [calc_ramp_power(p / 20, 200, 2500, 200) for p in range(11)]
        for i in range(len(powers) - 1):
            assert powers[i] <= powers[i + 1]

    def test_monotonic_second_half(self):
        powers = [calc_ramp_power(0.5 + p / 20, 200, 2500, 200) for p in range(11)]
        for i in range(len(powers) - 1):
            assert powers[i] >= powers[i + 1]

    def test_clamped_to_min(self):
        # Even if initial_power is somehow at boundary
        assert calc_ramp_power(0.0, 200, 200, 200) == 200

    def test_clamped_to_max(self):
        assert calc_ramp_power(0.5, 200, 2500, 200) == 2500

    def test_flat_curve(self):
        # All same values → constant power
        for p in [0.0, 0.25, 0.5, 0.75, 1.0]:
            assert calc_ramp_power(p, 1000, 1000, 1000) == 1000

    def test_negative_progress_clamped(self):
        assert calc_ramp_power(-0.5, 200, 2500, 200) == 200

    def test_over_one_progress_clamped(self):
        assert calc_ramp_power(1.5, 200, 2500, 200) == 200

    def test_returns_integer(self):
        power = calc_ramp_power(0.3, 200, 2500, 200)
        assert isinstance(power, int)


class TestCalcProgress:
    def test_at_start(self):
        assert calc_progress(0, 240) == pytest.approx(0.0)

    def test_at_half(self):
        assert calc_progress(120, 240) == pytest.approx(0.5)

    def test_at_end(self):
        assert calc_progress(240, 240) == pytest.approx(1.0)

    def test_over_duration(self):
        assert calc_progress(300, 240) == pytest.approx(1.0)

    def test_negative_elapsed(self):
        assert calc_progress(-10, 240) == pytest.approx(0.0)

    def test_zero_total(self):
        assert calc_progress(10, 0) == pytest.approx(1.0)
