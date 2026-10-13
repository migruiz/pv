"""The usage report: the meter's readings shared out by price window, corrected and priced, and GET /usage."""

from datetime import date, datetime, time, timedelta

import pytest

from mock_clock import TZ
from usage import tariff
from usage.report import at, report

DAY = date(2026, 10, 14)
B, S = tariff.CORRECTION_BOUGHT, tariff.CORRECTION_SOLD


def steady(start, end, bought_kw=0.0, sold_kw=0.0, every=60, bought=1000.0, sold=2000.0):
    """Readings every `every` seconds from `start` to `end` (Unix seconds) at a steady flow."""
    rows, t = [], start
    while t <= end:
        hours = (t - start) / 3600
        rows.append((t, bought + bought_kw * hours, sold + sold_kw * hours))
        t += every
    return rows


def kwh(entry, band):
    return entry["bought"][band]["kwh"]


def test_a_steady_kilowatt_all_day_falls_into_each_window_by_its_hours():
    [entry] = report(steady(at(DAY, time(0, 0)), at(DAY, None), bought_kw=1), [DAY])
    assert kwh(entry, "boost") == pytest.approx(2 * B, abs=1e-3)
    assert kwh(entry, "night") == pytest.approx(7 * B, abs=1e-3)   # 00-02, 04-08, 23-24
    assert kwh(entry, "day") == pytest.approx(15 * B, abs=1e-3)
    assert entry["bought"]["boost"]["eur"] == pytest.approx(2 * B * 0.1088, abs=1e-3)
    assert entry["bought_total"]["kwh"] == pytest.approx(24 * B, abs=1e-3)
    assert (entry["measured_hours"], entry["complete"]) == (24, True)
    assert entry["sold"] == {"kwh": 0, "eur": 0}


def test_selling_is_counted_and_priced_and_the_net_takes_it_off():
    start = at(DAY, time(12, 0))
    [entry] = report(steady(start, start + 3600, sold_kw=2), [DAY])
    assert entry["sold"]["kwh"] == pytest.approx(2 * S, abs=1e-3)
    assert entry["sold"]["eur"] == pytest.approx(2 * S * 0.195, abs=1e-3)
    assert entry["net_eur"] == pytest.approx(-2 * S * 0.195, abs=1e-3)
    assert entry["bought_total"]["kwh"] == 0


def test_a_reading_across_the_start_of_a_window_is_split_at_it():
    two = at(DAY, time(2, 0))
    [entry] = report([(two - 60, 1000.0, 0.0), (two + 180, 1000.4, 0.0)], [DAY])
    assert kwh(entry, "night") == pytest.approx(0.1 * B, abs=1e-3)
    assert kwh(entry, "boost") == pytest.approx(0.3 * B, abs=1e-3)


def test_a_gap_still_counts_its_energy_shared_by_time_but_not_as_measured():
    one = at(DAY, time(1, 0))
    [entry] = report([(one, 1000.0, 0.0), (one + 4 * 3600, 1004.0, 0.0)], [DAY])  # 01:00 to 05:00
    assert kwh(entry, "night") == pytest.approx(2 * B, abs=1e-3)  # 01-02 and 04-05
    assert kwh(entry, "boost") == pytest.approx(2 * B, abs=1e-3)
    assert (entry["measured_hours"], entry["complete"]) == (0, False)


def test_a_reading_from_before_midnight_starts_the_day_and_the_night_before_is_not_in_it():
    midnight = at(DAY, time(0, 0))
    yesterday = DAY - timedelta(days=1)
    rows = steady(midnight - 3600, midnight + 3600, bought_kw=1)
    before, entry = report(rows, [yesterday, DAY])
    assert kwh(before, "night") == pytest.approx(1 * B, abs=1e-3)
    assert kwh(entry, "night") == pytest.approx(1 * B, abs=1e-3)
    assert report(rows, [DAY])[0]["bought_total"]["kwh"] == pytest.approx(1 * B, abs=1e-3)


def test_a_meter_going_backwards_is_ignored():
    t = at(DAY, time(12, 0))
    [entry] = report([(t, 1000.0, 50.0), (t + 60, 10.0, 50.0), (t + 120, 10.5, 50.1)], [DAY])
    assert kwh(entry, "day") == pytest.approx(0.5 * B, abs=1e-3)
    assert entry["sold"]["kwh"] == pytest.approx(0.1 * S, abs=1e-3)


def test_the_day_the_clocks_go_back_has_25_hours_and_its_first_window_three():
    back = date(2026, 10, 25)
    [entry] = report(steady(at(back, time(0, 0)), at(back, None), bought_kw=1), [back])
    assert kwh(entry, "night") == pytest.approx(8 * B, abs=1e-3)  # 00:00-02:00 lasts 3 hours
    assert entry["bought_total"]["kwh"] == pytest.approx(25 * B, abs=1e-3)
    assert (entry["measured_hours"], entry["complete"]) == (25, True)


def test_a_day_without_readings_is_empty():
    [entry] = report([], [DAY])
    assert (entry["date"], entry["measured_hours"], entry["complete"]) == ("2026-10-14", 0, False)
    assert entry["bought_total"] == {"kwh": 0, "eur": 0}
    assert set(entry["bought"]) == {"boost", "night", "day"}


def test_the_windows_cover_every_minute_of_the_day_once():
    minutes = []
    for w in tariff.WINDOWS:
        end = 1440 if w.end is None else w.end.hour * 60 + w.end.minute
        minutes += range(w.start.hour * 60 + w.start.minute, end)
    assert sorted(minutes) == list(range(1440))
    assert {w.band for w in tariff.WINDOWS} == {b.id for b in tariff.BANDS}


# ---------------------------------------------------------------------------
# GET /usage
# ---------------------------------------------------------------------------

@pytest.fixture
async def api(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from history.store import HistoryStore
    from usage.router import router

    monkeypatch.setenv("READ_API_KEY", "read-key")
    store = HistoryStore(tmp_path / "history.sqlite3")
    app = FastAPI()
    app.state.history = store
    app.include_router(router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           headers={"X-API-Key": "read-key"}) as client:
        yield client, store
    store.close()


def record(store, when, bought, sold):
    store.record({"updated_at": when.isoformat(), "pv_kw": 0, "home_kw": 0.3, "battery_soc": 50,
                  "grid_import_total_kwh": bought, "grid_export_total_kwh": sold})


async def test_usage_lists_the_days_oldest_first_ending_today(api):
    import mock_clock

    client, store = api
    mock_clock.set_time(9, 0)
    today = mock_clock.get_now().date()
    two = datetime.combine(today, time(2, 0), TZ)
    for minute in range(121):  # 02:00 to 04:00 at 3 kW
        record(store, two + timedelta(minutes=minute), 2000 + 0.05 * minute, 5000.0)
    body = (await client.get("/usage", params={"days": 3})).json()
    assert [d["date"] for d in body["days"]] == [(today - timedelta(days=n)).isoformat() for n in (2, 1, 0)]
    assert body["days"][-1]["bought"]["boost"]["kwh"] == pytest.approx(6 * B, abs=1e-3)
    assert body["days"][0]["measured_hours"] == 0
    assert body["days"][-1]["used_kwh"] == pytest.approx(121 * 0.3 / 60, abs=1e-3)
    assert [b["id"] for b in body["tariff"]["bands"]] == ["boost", "night", "day"]
    assert body["tariff"]["windows"][-1] == {"band": "night", "start": "23:00", "end": "24:00"}


async def test_usage_needs_a_key_and_a_sensible_number_of_days(api):
    client, _ = api
    assert (await client.get("/usage", headers={"X-API-Key": "wrong"})).status_code == 401
    assert (await client.get("/usage", headers={"X-API-Key": "test-key"})).status_code == 200
    assert len((await client.get("/usage")).json()["days"]) == 7
    assert (await client.get("/usage", params={"days": 0})).status_code == 422
    assert (await client.get("/usage", params={"days": 31})).status_code == 422


def halves(entry):
    return {h["start"]: h for h in entry["half_hours"]}


def test_every_day_has_its_half_hours_in_order_with_their_band_and_price():
    [entry] = report(steady(at(DAY, time(0, 0)), at(DAY, None), bought_kw=1), [DAY])
    rows = entry["half_hours"]
    assert [h["start"] for h in rows[:5]] == ["00:00", "00:30", "01:00", "01:30", "02:00"]
    assert len(rows) == 48 and rows[-1]["start"] == "23:30"
    assert [h["band"] for h in rows[3:9]] == ["night", "boost", "boost", "boost", "boost", "night"]
    assert rows[16]["band"] == "day" and rows[46]["band"] == "night"
    assert rows[4]["bought_kwh"] == pytest.approx(0.5 * B, abs=1e-3)
    assert rows[4]["bought_eur"] == pytest.approx(0.5 * B * 0.1088, abs=1e-3)
    assert sum(h["bought_kwh"] for h in rows) == pytest.approx(entry["bought_total"]["kwh"], abs=0.03)  # each rounded to 1 Wh


def test_a_reading_across_a_half_hour_is_split_between_the_two():
    t = at(DAY, time(12, 20))
    [entry] = report([(t, 1000.0, 50.0), (t + 1200, 1000.0, 50.4)], [DAY])  # 12:20 to 12:40, 0.4 kWh sold
    assert halves(entry)["12:00"]["sold_kwh"] == pytest.approx(0.2 * S, abs=1e-3)
    assert halves(entry)["12:30"]["sold_kwh"] == pytest.approx(0.2 * S, abs=1e-3)
    assert halves(entry)["12:30"]["sold_eur"] == pytest.approx(0.2 * S * 0.195, abs=1e-3)


def test_clock_change_days_have_50_and_46_half_hours():
    back = date(2026, 10, 25)
    [entry] = report([], [back])
    starts = [h["start"] for h in entry["half_hours"]]
    assert len(starts) == 50 and starts[:8] == ["00:00", "00:30", "01:00", "01:30", "01:00", "01:30", "02:00", "02:30"]
    assert [h["band"] for h in entry["half_hours"][4:7]] == ["night", "night", "boost"]
    forward = date(2027, 3, 28)
    [entry] = report([], [forward])
    starts = [h["start"] for h in entry["half_hours"]]
    assert len(starts) == 46 and starts[:4] == ["00:00", "00:30", "02:00", "02:30"]


def test_what_the_house_used_comes_from_its_minute_averages_whatever_the_source():
    noon = at(DAY, time(12, 0))
    home = [(noon + 60 * m + 55, 2.0) for m in range(60)]  # 2 kW for an hour, each minute's last reading at :55
    [entry] = report([], [DAY], home)
    assert halves(entry)["12:00"]["used_kwh"] == pytest.approx(1.0, abs=1e-3)
    assert halves(entry)["12:30"]["used_kwh"] == pytest.approx(1.0, abs=1e-3)
    assert entry["used_kwh"] == pytest.approx(2.0, abs=1e-3)
    assert entry["bought_total"]["kwh"] == 0  # the battery or solar covered it
