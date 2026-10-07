"""The minute history: what is recorded, kept and served by GET /history."""

from datetime import datetime, timedelta, timezone

import pytest

from history.store import HistoryStore

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def reading(at=NOW, pv=2, home=0.25, soc=73):
    return dict(updated_at=at.isoformat(), pv_kw=pv, home_kw=home, battery_soc=soc)


@pytest.fixture
def store(tmp_path):
    result = HistoryStore(tmp_path / 'history.sqlite3')
    yield result
    result.close()


def test_every_poll_averages_power_and_keeps_latest_soc(store):
    store.record(reading())
    store.record(reading(NOW + timedelta(seconds=3), pv=4, home=0.75, soc=74))
    store.record(reading())  # duplicate/out-of-order doesn't dilute the average
    assert store.samples(0) == [((NOW + timedelta(seconds=3)).timestamp(), 3, 0.5, 74)]
    assert store.status()['minutes'] == 1


def test_database_survives_restart(tmp_path):
    path = tmp_path / 'history.sqlite3'
    first = HistoryStore(path)
    first.record(reading())
    first.close()
    second = HistoryStore(path)
    assert second.status()['minutes'] == 1
    second.close()


def test_retention_prunes_old_history(store):
    store.record(reading(NOW - timedelta(days=31)))
    store.record(reading())
    assert store.status()['minutes'] == 1


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
    assert rows == [((NOW - timedelta(seconds=57)).timestamp(), 5, 0.25, 74)]
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
        {"observed_at": (now - timedelta(minutes=1)).timestamp(), "pv_kw": 4, "home_kw": 0.5, "battery_soc": 80},
    ]}
    assert len((await api.get("/history")).json()["minutes"]) == 2  # the last 12 hours


async def test_history_goes_back_48_hours_at_most(api, store):
    now = datetime.now(timezone.utc)
    store.record(reading(now - timedelta(hours=49)))
    store.record(reading(now - timedelta(hours=47)))
    assert len((await api.get("/history", params={"since": 0})).json()["minutes"]) == 1
    assert (await api.get("/history", params={"since": "inf"})).json() == {"minutes": []}
