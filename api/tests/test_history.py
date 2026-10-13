"""The minute history: what is recorded, kept and served by GET /history."""

from datetime import datetime, timedelta, timezone

import pytest

from history.store import HistoryStore

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def reading(at=NOW, pv=2, home=0.25, soc=73, bought=1500.0, sold=2500.0):
    return dict(updated_at=at.isoformat(), pv_kw=pv, home_kw=home, battery_soc=soc,
                grid_import_total_kwh=bought, grid_export_total_kwh=sold)


@pytest.fixture
def store(tmp_path):
    result = HistoryStore(tmp_path / 'history.sqlite3')
    yield result
    result.close()


def test_every_poll_averages_power_and_keeps_latest_soc_and_meter_totals(store):
    store.record(reading())
    store.record(reading(NOW + timedelta(seconds=3), pv=4, home=0.75, soc=74, bought=1500.01, sold=2500.02))
    store.record(reading())  # duplicate/out-of-order doesn't dilute the average
    assert store.samples(0) == [((NOW + timedelta(seconds=3)).timestamp(), 3, 0.5, 74, 1500.01, 2500.02)]
    assert store.status()['minutes'] == 1


def test_a_reading_without_meter_totals_is_still_recorded(store):
    store.record(reading(bought=None, sold=float('nan')))
    assert store.samples(0) == [(NOW.timestamp(), 2, 0.25, 73, None, None)]


def test_an_older_database_gets_the_meter_columns_and_keeps_its_minutes(tmp_path):
    import sqlite3

    path = tmp_path / 'history.sqlite3'
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE samples (minute INTEGER PRIMARY KEY, observed_at REAL NOT NULL, pv_sum REAL, "
                "home_sum REAL, battery_soc REAL, sample_count INTEGER NOT NULL, source TEXT NOT NULL)")
    before = NOW - timedelta(minutes=1)
    old.execute("INSERT INTO samples VALUES (?,?,?,?,?,?,?)",
                (int(before.timestamp() // 60), before.timestamp(), 2, 0.25, 73, 1, "inverter"))
    old.commit()
    old.close()
    store = HistoryStore(path)
    store.record(reading())
    assert store.samples(0) == [(before.timestamp(), 2, 0.25, 73, None, None),
                                (NOW.timestamp(), 2, 0.25, 73, 1500.0, 2500.0)]
    store.close()


def test_database_survives_restart(tmp_path):
    path = tmp_path / 'history.sqlite3'
    first = HistoryStore(path)
    first.record(reading())
    first.close()
    second = HistoryStore(path)
    assert second.status()['minutes'] == 1
    second.close()


def test_old_history_is_kept_for_good(store):
    store.record(reading(NOW - timedelta(days=400)))
    store.record(reading())
    assert store.status()['minutes'] == 2


def test_samples_can_stop_before_a_time(store):
    start = NOW - timedelta(hours=1)
    for m in range(5):
        store.record(reading(start + timedelta(minutes=m)))
    rows = store.samples(start.timestamp(), until=(start + timedelta(minutes=3)).timestamp())
    assert [at for at, *_ in rows] == [(start + timedelta(minutes=m)).timestamp() for m in range(3)]


def test_minutes_keep_their_true_times_and_an_outage_stays_missing(store):
    start = NOW - timedelta(hours=12)
    for m in (0, 1, 20):
        store.record(reading(start + timedelta(minutes=m, seconds=7)))
    assert [at for at, *_ in store.samples(0)] == [
        (start + timedelta(minutes=m, seconds=7)).timestamp() for m in (0, 1, 20)]


def test_invalid_readings_are_not_recorded(store):
    store.record(reading(pv=float('nan')))
    assert store.status()['minutes'] == 0



def test_samples_are_whole_minutes_from_the_one_holding_since(store):
    store.record(reading(NOW - timedelta(minutes=2)))
    store.record(reading(NOW - timedelta(minutes=1), pv=4))
    store.record(reading(NOW - timedelta(seconds=57), pv=6, soc=74))
    rows = store.samples((NOW - timedelta(seconds=30)).timestamp())  # half way through the last minute
    assert rows == [((NOW - timedelta(seconds=57)).timestamp(), 5, 0.25, 74, 1500.0, 2500.0)]
    assert len(store.samples(0)) == 2


# ---------------------------------------------------------------------------
# GET /history
# ---------------------------------------------------------------------------

@pytest.fixture
async def api(store, monkeypatch):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from history.router import router

    monkeypatch.setenv("READ_API_KEY", "read-key")
    app = FastAPI()
    app.state.history = store
    app.include_router(router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           headers={"X-API-Key": "read-key"}) as client:
        yield client


async def test_history_needs_a_key(api):
    assert (await api.get("/history", headers={"X-API-Key": "wrong"})).status_code == 401
    assert (await api.get("/history", headers={"X-API-Key": "test-key"})).status_code == 200  # the full key too


async def test_history_since_a_time(api, store):
    now = datetime.now(timezone.utc).replace(second=30, microsecond=0)
    store.record(reading(now - timedelta(minutes=5)))
    store.record(reading(now - timedelta(minutes=1), pv=4, home=0.5, soc=80))
    since = (now - timedelta(minutes=2)).timestamp()
    assert (await api.get("/history", params={"since": since})).json() == {"minutes": [
        {"observed_at": (now - timedelta(minutes=1)).timestamp(), "pv_kw": 4, "home_kw": 0.5, "battery_soc": 80,
         "grid_import_total_kwh": 1500.0, "grid_export_total_kwh": 2500.0},
    ]}
    assert len((await api.get("/history")).json()["minutes"]) == 2  # the last 12 hours


async def test_history_goes_back_8_days_at_most(api, store):
    now = datetime.now(timezone.utc)
    store.record(reading(now - timedelta(days=8, hours=1)))
    store.record(reading(now - timedelta(days=7, hours=23)))
    assert len((await api.get("/history", params={"since": 0})).json()["minutes"]) == 1
    assert (await api.get("/history", params={"since": "inf"})).json() == {"minutes": []}


def test_steps_average_their_minutes_and_keep_the_latest_battery_and_meter_totals(store):
    start = NOW.replace(minute=5)  # a 5-minute boundary
    store.record(reading(start + timedelta(minutes=0, seconds=10), pv=1, home=0.5, soc=70))
    store.record(reading(start + timedelta(minutes=0, seconds=40), pv=3, home=0.5, soc=70))  # minute averages 2
    store.record(reading(start + timedelta(minutes=3, seconds=20), pv=4, home=1.5, soc=71, sold=2500.1))
    store.record(reading(start + timedelta(minutes=5, seconds=5), pv=6, home=0.2, soc=72, sold=2500.2))  # the next step
    assert store.samples(0, 5) == [
        ((start + timedelta(minutes=3, seconds=20)).timestamp(), 3, 1, 71, 1500.0, 2500.1),
        ((start + timedelta(minutes=5, seconds=5)).timestamp(), 6, 0.2, 72, 1500.0, 2500.2),
    ]


def test_a_step_starts_on_its_boundary_even_when_since_does_not(store):
    start = NOW.replace(minute=5)
    store.record(reading(start + timedelta(minutes=1), pv=2))
    store.record(reading(start + timedelta(minutes=3), pv=4))
    since = (start + timedelta(minutes=2)).timestamp()  # in the middle of the step
    assert [round(pv, 6) for _, pv, *_ in store.samples(since, 5)] == [3]


async def test_history_in_steps(api, store):
    now = datetime.now(timezone.utc).replace(second=30, microsecond=0)
    for m in range(1, 31):
        store.record(reading(now - timedelta(minutes=m)))
    rows = (await api.get("/history", params={"since": 0, "step": 5})).json()["minutes"]
    assert 6 <= len(rows) <= 7
    assert all(row["pv_kw"] == 2 and row["battery_soc"] == 73 for row in rows)
    assert (await api.get("/history", params={"step": 0})).status_code == 422
    assert (await api.get("/history", params={"step": 61})).status_code == 422
