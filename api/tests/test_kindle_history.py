"""Persistence, backfill and real-time chart boundaries."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from kindle_dashboard.backfill import fetch_history, seed_history
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


def test_seed_never_overwrites_local_readings(store):
    store.record(reading())
    store.seed([dict(timestamp=NOW.timestamp(), pv_kw=99, home_kw=99, battery_soc=99)], NOW)
    history, _ = store.chart(NOW, {})
    assert history['pv_kw'] == [2]
    assert store.status()['sources'] == {'inverter': 1}


def test_local_poll_replaces_cloud_minute_not_averaged_with_it(store):
    store.seed([dict(timestamp=NOW.timestamp(), pv_kw=99, home_kw=99, battery_soc=99)], NOW)
    store.record(reading(NOW + timedelta(seconds=3)))
    history, _ = store.chart(NOW + timedelta(seconds=3), {})
    assert history['pv_kw'] == [2]


def test_database_and_seed_marker_survive_restart(tmp_path):
    path = tmp_path / 'history.sqlite3'
    first = HistoryStore(path)
    first.record(reading())
    first.seed([], NOW)
    first.close()
    second = HistoryStore(path)
    assert second.seeded()
    assert second.status()['minutes'] == 1
    second.close()


def test_retention_prunes_old_history(store):
    store.record(reading(NOW - timedelta(days=31)))
    store.record(reading())
    assert store.status()['minutes'] == 1


def test_true_timestamps_gaps_and_current_endpoint(store):
    start = NOW - timedelta(hours=12)
    store.seed([dict(timestamp=(start + timedelta(minutes=m)).timestamp(), pv_kw=2,
                     home_kw=0.25, battery_soc=73) for m in (0, 5, 20)], NOW)
    history, positions = store.chart(NOW, reading())
    assert positions[0] == 0
    assert positions[1] == pytest.approx(5 / 720)
    assert positions[-1] == 1
    assert history['pv_kw'] == [2, 2, None, 2, None, 2]


def test_local_outage_is_not_drawn_as_continuous(store):
    store.record(reading(NOW - timedelta(minutes=2)))
    history, _ = store.chart(NOW, reading())
    assert history['battery_soc'] == [73, None, 73]


def test_invalid_readings_are_not_recorded(store):
    store.record(reading(pv=float('nan')))
    assert store.status()['minutes'] == 0


async def test_seeded_database_never_queries_cloud_again(store):
    store.seed([], NOW)
    session = AsyncMock()
    await seed_history(session, store)
    session.get_chart_history.assert_not_called()


class Response:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return {'success': True, 'data': self.data}


def test_cloud_dates_timezone_units_and_missing_values():
    calls = []
    stamp = NOW.timestamp()

    class Client:
        _huawei_subdomain = 'example'

        def get(self, url, params, timeout):
            calls.append(params)
            if 'signalIds' in params:
                signal = params['signalIds'][0]
                assert datetime.fromtimestamp(params['date'] / 1000, timezone.utc).hour == 11  # Dublin noon
                return Response({signal: {'pmDataList': [
                    {'startTime': stamp, 'counterValue': 73 if signal == '30007' else 2.5},
                    {'startTime': stamp + 300, 'counterValue': 1.7976931348623157e308}]}})
            assert params['timeZone'] == 1
            return Response({'clientTimezone': 'Europe/Dublin',
                             'xAxis': ['2026-09-15 13:00', '2026-09-15 13:05'],
                             'usePower': ['0.25', '--']})

    client = Client()
    client._session = client
    samples = fetch_history(client, NOW - timedelta(hours=1), NOW + timedelta(minutes=10))
    assert samples == [dict(timestamp=stamp, pv_kw=2.5, battery_soc=73, home_kw=0.25)]
    assert len(calls) == 3
