"""The usage report: the meter's readings shared out by price window, corrected and priced, and GET /usage."""

from datetime import date, datetime, time, timedelta

import pytest

from mock_clock import TZ
from usage import tariff
from usage.report import at, months, report

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


# ---------------------------------------------------------------------------
# Months
# ---------------------------------------------------------------------------

def test_days_are_gathered_into_their_months_with_totals_and_without_half_hours():
    sep30, oct1 = date(2026, 9, 30), date(2026, 10, 1)
    rows = steady(at(sep30, time(12, 0)), at(oct1, time(12, 0)), bought_kw=1)
    days = report(rows, [date(2026, 9, 29), sep30, oct1, date(2026, 10, 2)])
    september, october = months(days)
    assert (september["month"], october["month"]) == ("2026-09", "2026-10")
    assert [d["date"] for d in september["days"]] == ["2026-09-29", "2026-09-30"]
    assert all("half_hours" not in d for d in september["days"] + october["days"])
    assert september["bought_total"]["kwh"] == pytest.approx(12 * B, abs=2e-3)
    assert september["bought"]["day"]["kwh"] == pytest.approx(11 * B, abs=2e-3)  # 12:00-23:00
    assert october["bought"]["night"]["kwh"] == pytest.approx(6 * B, abs=2e-3)  # 00-02, 04-08
    assert october["net_eur"] == pytest.approx(october["bought_total"]["eur"], abs=1e-3)
    assert october["measured_hours"] == pytest.approx(12, abs=0.05)
    assert not september["complete"]  # it starts on the 29th


def test_months_before_the_first_readings_are_left_out_and_a_whole_measured_month_is_complete():
    feb = [date(2026, 2, 1) + timedelta(days=n) for n in range(28)]
    jan31 = date(2026, 1, 31)
    rows = steady(at(feb[0], time(0, 0)), at(feb[-1], None), bought_kw=1, every=300)
    [february] = months(report(rows, [jan31] + feb))
    assert february["month"] == "2026-02" and len(february["days"]) == 28
    assert february["complete"]
    assert february["bought_total"]["kwh"] == pytest.approx(28 * 24 * B, abs=0.05)


async def test_usage_months_ends_with_this_month_so_far(api):
    import mock_clock

    client, store = api
    mock_clock.set_time(9, 0)
    today = mock_clock.get_now().date()
    last_month = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    two = datetime.combine(last_month, time(2, 0), TZ)
    for minute in range(61):  # 02:00 to 03:00 on the 1st of last month, at 3 kW
        record(store, two + timedelta(minutes=minute), 2000 + 0.05 * minute, 5000.0)
    record(store, datetime.combine(today, time(8, 0), TZ), 2003.0, 5000.0)
    body = (await client.get("/usage/months", params={"months": 3})).json()
    assert [m["month"] for m in body["months"]] == [last_month.isoformat()[:7], today.isoformat()[:7]]
    earlier, this = body["months"]
    assert earlier["bought"]["boost"]["kwh"] == pytest.approx(3 * B, abs=1e-3)
    assert earlier["days"][0]["date"] == last_month.isoformat() and "half_hours" not in earlier["days"][0]
    assert this["days"][-1]["date"] == today.isoformat() and not this["complete"]
    assert [b["id"] for b in body["tariff"]["bands"]] == ["boost", "night", "day"]
    assert (await client.get("/usage/months", params={"months": 0})).status_code == 422
    assert (await client.get("/usage/months", params={"months": 37})).status_code == 422


async def test_usage_can_end_on_an_earlier_day_and_never_after_today(api):
    import mock_clock

    client, store = api
    mock_clock.set_time(9, 0)
    today = mock_clock.get_now().date()
    end = today - timedelta(days=10)
    body = (await client.get("/usage", params={"days": 2, "end": end.isoformat()})).json()
    assert [d["date"] for d in body["days"]] == [(end - timedelta(days=1)).isoformat(), end.isoformat()]
    body = (await client.get("/usage", params={"days": 1, "end": (today + timedelta(days=5)).isoformat()})).json()
    assert [d["date"] for d in body["days"]] == [today.isoformat()]


async def test_a_settled_day_is_worked_out_once_and_today_every_time(api):
    import mock_clock

    client, store = api
    mock_clock.set_time(9, 0)
    today = mock_clock.get_now().date()
    old = today - timedelta(days=3)
    noon = datetime.combine(old, time(12, 0), TZ)
    record(store, noon, 2000.0, 5000.0)
    record(store, noon + timedelta(minutes=1), 2001.0, 5000.0)
    eight = datetime.combine(today, time(8, 0), TZ)
    record(store, eight, 2001.0, 5000.0)
    record(store, eight + timedelta(minutes=1), 2002.0, 5000.0)

    def bought(body, day):
        return next(d for d in body["days"] if d["date"] == day.isoformat())["bought_total"]["kwh"]

    first = (await client.get("/usage", params={"days": 4})).json()
    assert bought(first, old) == pytest.approx(B, abs=1e-3)
    # More readings turn up for both days: only today's are seen
    record(store, noon + timedelta(minutes=2), 2001.5, 5000.0)
    record(store, eight + timedelta(minutes=2), 2002.5, 5000.0)
    second = (await client.get("/usage", params={"days": 4})).json()
    assert bought(second, old) == pytest.approx(B, abs=1e-3)
    assert bought(second, today) == pytest.approx(1.5 * B, abs=1e-3)


async def test_the_months_are_worked_out_in_the_background_after_startup(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import mock_clock
    from history.store import HistoryStore
    from usage import router

    mock_clock.set_time(9, 0)
    today = mock_clock.get_now().date()
    store = HistoryStore(tmp_path / "history.sqlite3")
    old = datetime.combine(today - timedelta(days=3), time(12, 0), TZ)
    record(store, old, 2000.0, 5000.0)
    record(store, old + timedelta(minutes=1), 2001.0, 5000.0)
    monkeypatch.setattr(router, "WARM_AFTER", 0)
    state = SimpleNamespace(history=store)
    await router.warm_up(state)
    assert state.usage_days[old.date()]["bought_total"]["kwh"] == pytest.approx(B, abs=1e-3)
    assert today not in state.usage_days  # today is still going
    store.close()
