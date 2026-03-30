"""Tests for charge window power calculation (pure functions)."""

from datetime import datetime, timedelta

import pytest

from charge_windows.ramp_calculator import (
    MIN_POWER,
    MAX_POWER,
    calc_charge_power,
    calc_progress,
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
        quarter = cosine_interpolate(0, 100, 0.25)
        assert quarter < 50
        assert quarter > 0
        three_quarter = cosine_interpolate(0, 100, 0.75)
        assert three_quarter > 50
        assert three_quarter < 100


class TestCalcChargePower:
    """Tests for the asymmetric cosine bell curve calculator."""

    def _make_times(self, start_h, peak_h, end_h):
        base = datetime(2026, 3, 30)
        return (
            base.replace(hour=start_h),
            base.replace(hour=peak_h),
            base.replace(hour=end_h),
        )

    def test_at_start(self):
        start, peak, end = self._make_times(10, 12, 14)
        assert calc_charge_power(start, start, peak, end, 200, 2500, 200) == 200

    def test_at_peak(self):
        start, peak, end = self._make_times(10, 12, 14)
        assert calc_charge_power(peak, start, peak, end, 200, 2500, 200) == 2500

    def test_at_end(self):
        start, peak, end = self._make_times(10, 12, 14)
        assert calc_charge_power(end, start, peak, end, 200, 2500, 200) == 200

    def test_before_start(self):
        start, peak, end = self._make_times(10, 12, 14)
        before = start - timedelta(minutes=30)
        assert calc_charge_power(before, start, peak, end, 200, 2500, 200) == 200

    def test_after_end(self):
        start, peak, end = self._make_times(10, 12, 14)
        after = end + timedelta(minutes=30)
        assert calc_charge_power(after, start, peak, end, 200, 2500, 200) == 200

    def test_symmetric_curve_quarter(self):
        """With symmetric timing, quarter should equal three-quarter."""
        start, peak, end = self._make_times(10, 12, 14)
        quarter = start + timedelta(hours=1)   # 11:00
        three_quarter = peak + timedelta(hours=1)  # 13:00
        p1 = calc_charge_power(quarter, start, peak, end, 200, 2500, 200)
        p3 = calc_charge_power(three_quarter, start, peak, end, 200, 2500, 200)
        assert p1 == p3

    def test_asymmetric_timing(self):
        """Peak at 1/3 of duration: 1h ramp up, 2h ramp down."""
        base = datetime(2026, 3, 30)
        start = base.replace(hour=10)
        peak = base.replace(hour=11)   # 1h from start
        end = base.replace(hour=13)    # 2h from peak

        # At midpoint of ramp-up (10:30)
        mid_up = start + timedelta(minutes=30)
        p_up = calc_charge_power(mid_up, start, peak, end, 200, 2500, 200)
        assert 200 < p_up < 2500

        # At midpoint of ramp-down (12:00)
        mid_down = peak + timedelta(hours=1)
        p_down = calc_charge_power(mid_down, start, peak, end, 200, 2500, 200)
        assert 200 < p_down < 2500

    def test_monotonic_first_half(self):
        start, peak, end = self._make_times(10, 12, 14)
        powers = []
        for i in range(21):
            t = start + timedelta(minutes=i * 6)  # every 6 min over 2h
            powers.append(calc_charge_power(t, start, peak, end, 200, 2500, 200))
        for i in range(len(powers) - 1):
            assert powers[i] <= powers[i + 1]

    def test_monotonic_second_half(self):
        start, peak, end = self._make_times(10, 12, 14)
        powers = []
        for i in range(21):
            t = peak + timedelta(minutes=i * 6)
            powers.append(calc_charge_power(t, start, peak, end, 200, 2500, 200))
        for i in range(len(powers) - 1):
            assert powers[i] >= powers[i + 1]

    def test_values_always_in_range(self):
        start, peak, end = self._make_times(10, 12, 14)
        for i in range(241):
            t = start + timedelta(minutes=i)
            p = calc_charge_power(t, start, peak, end, 200, 2500, 200)
            assert 200 <= p <= 2500

    def test_flat_curve(self):
        start, peak, end = self._make_times(10, 12, 14)
        for i in range(0, 241, 30):
            t = start + timedelta(minutes=i)
            assert calc_charge_power(t, start, peak, end, 1000, 1000, 1000) == 1000

    def test_returns_integer(self):
        start, peak, end = self._make_times(10, 12, 14)
        mid = start + timedelta(minutes=45)
        p = calc_charge_power(mid, start, peak, end, 200, 2500, 200)
        assert isinstance(p, int)

    def test_different_end_power(self):
        start, peak, end = self._make_times(10, 12, 14)
        assert calc_charge_power(start, start, peak, end, 200, 2500, 500) == 200
        assert calc_charge_power(peak, start, peak, end, 200, 2500, 500) == 2500
        assert calc_charge_power(end, start, peak, end, 200, 2500, 500) == 500


class TestCalcProgress:
    def test_at_start(self):
        base = datetime(2026, 3, 30, 10, 0)
        assert calc_progress(base, base, base + timedelta(hours=4)) == pytest.approx(0.0)

    def test_at_half(self):
        base = datetime(2026, 3, 30, 10, 0)
        mid = base + timedelta(hours=2)
        end = base + timedelta(hours=4)
        assert calc_progress(mid, base, end) == pytest.approx(0.5)

    def test_at_end(self):
        base = datetime(2026, 3, 30, 10, 0)
        end = base + timedelta(hours=4)
        assert calc_progress(end, base, end) == pytest.approx(1.0)

    def test_over_duration(self):
        base = datetime(2026, 3, 30, 10, 0)
        end = base + timedelta(hours=4)
        assert calc_progress(end + timedelta(hours=1), base, end) == pytest.approx(1.0)

    def test_before_start(self):
        base = datetime(2026, 3, 30, 10, 0)
        end = base + timedelta(hours=4)
        assert calc_progress(base - timedelta(hours=1), base, end) == pytest.approx(0.0)
