"""Battery runtime arithmetic, overnight boundaries and Dublin seasonality."""

from datetime import date, datetime, timedelta, timezone

import pytest

from kindle_dashboard import estimate


def local(value):
    return datetime.fromisoformat(value).replace(tzinfo=estimate.DUBLIN)


@pytest.fixture
def fixed_sun(monkeypatch):
    monkeypatch.setattr(estimate, "daylight", lambda day: (
        local(f"{day}T07:00:00"), local(f"{day}T19:00:00")))


def test_daytime_starts_at_sunset(fixed_sun):
    result = estimate.estimate_battery(73, local("2026-09-15T12:00:00"))
    # 73% of 4.8 kWh = 3.504 kWh, or 14 hours and 57.6 seconds.
    assert result.empty_at == local("2026-09-16T09:00:57.600000")
    assert estimate.clock_text(result.empty_at) == ("9:01", "a")


@pytest.mark.parametrize("at", ["2026-09-15T19:00:00", "2026-09-15T23:00:00",
                                "2026-09-16T00:30:00", "2026-09-16T06:59:00"])
def test_dark_hours_start_now_including_after_midnight(fixed_sun, at):
    now = local(at)
    result = estimate.estimate_battery(25, now)
    assert result.empty_at == now + timedelta(hours=4.8)


def test_new_charge_changes_remaining_runtime(fixed_sun):
    now = local("2026-09-15T22:00:00")
    first = estimate.estimate_battery(50, now)
    second = estimate.estimate_battery(25, now)
    assert first.empty_at - second.empty_at == timedelta(hours=4.8)


def test_zero_is_already_empty_in_daylight(fixed_sun):
    now = local("2026-09-15T12:00:00")
    assert estimate.estimate_battery(0, now).empty_at == now


@pytest.mark.parametrize("soc", [None, "n/a", float("nan"), float("inf"), -1, 101])
def test_unavailable_charge_has_no_made_up_estimate(soc):
    assert estimate.estimate_battery(soc, local("2026-09-15T12:00:00")).empty_at is None


@pytest.mark.parametrize("at", ["2026-03-28T23:00:00", "2026-10-24T23:00:00"])
def test_elapsed_runtime_across_clock_changes(at):
    now = local(at)
    result = estimate.estimate_battery(25, now)
    assert result.empty_at.astimezone(timezone.utc) - now.astimezone(timezone.utc) == timedelta(hours=4.8)


def test_dublin_summer_and_winter_sunset():
    _, summer = estimate.daylight(date(2026, 6, 21))
    _, winter = estimate.daylight(date(2026, 12, 21))
    assert (summer.hour, winter.hour) == (21, 16)
    assert (summer.utcoffset(), winter.utcoffset()) == (timedelta(hours=1), timedelta(0))


def test_utc_and_dublin_times_produce_same_estimate():
    now = local("2026-09-15T19:30:00")
    assert estimate.estimate_battery(73, now) == estimate.estimate_battery(73, now.astimezone(timezone.utc))
