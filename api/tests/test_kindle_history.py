"""Persistence and real-time chart boundaries."""

from datetime import datetime, timedelta, timezone

import pytest

from kindle_dashboard.history import HistoryStore

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
    history, positions = store.chart(NOW + timedelta(seconds=3), {})
    assert history == {'pv_kw': [3], 'home_kw': [0.5], 'battery_soc': [74]}
    assert positions == [1]
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


def test_true_timestamps_gaps_and_current_endpoint(store):
    start = NOW - timedelta(hours=12)
    for m in (0, 1, 20):
        store.record(reading(start + timedelta(minutes=m)))
    history, positions = store.chart(NOW, reading())
    assert positions[0] == 0
    assert positions[1] == pytest.approx(1 / 720)
    assert positions[-1] == 1
    assert history['pv_kw'] == [2, 2, None, 2, None, 2]


def test_local_outage_is_not_drawn_as_continuous(store):
    store.record(reading(NOW - timedelta(minutes=2)))
    history, _ = store.chart(NOW, reading())
    assert history['battery_soc'] == [73, None, 73]


def test_invalid_readings_are_not_recorded(store):
    store.record(reading(pv=float('nan')))
    assert store.status()['minutes'] == 0

