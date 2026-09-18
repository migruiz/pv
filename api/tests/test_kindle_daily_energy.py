"""Running daily solar and home energy for the chart layout."""

from datetime import datetime, timezone

import pytest
from PIL import Image, ImageDraw

import mock_clock
from kindle_dashboard import renderer
from kindle_dashboard.daily_energy import energy_history, running_totals, solar_today_kwh, values_at
from kindle_dashboard.history import HistoryStore

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)  # 13:00 in Dublin
MIDNIGHT = datetime(2026, 9, 14, 23, 0, tzinfo=timezone.utc).timestamp()  # Dublin midnight


def at(hours_after_midnight):
    return MIDNIGHT + hours_after_midnight * 3600


@pytest.fixture
def store(tmp_path):
    result = HistoryStore(tmp_path / 'history.sqlite3')
    yield result
    result.close()


@pytest.fixture
def seeded(store):
    """A constant 1 kW solar and 0.5 kW home from Dublin midnight until now."""
    store.seed([dict(timestamp=MIDNIGHT + minutes * 60, pv_kw=1, home_kw=0.5, battery_soc=73)
                for minutes in range(0, 13 * 60 + 1, 5)], NOW)
    current = dict(updated_at=NOW.isoformat(), pv_kw=1, home_kw=0.5, battery_soc=73)
    history, positions = store.chart(NOW, current)
    return store, current, history, positions


def test_trapezoids_add_up_power_into_energy():
    totals = running_totals([(at(1), 0), (at(2), 2), (at(3), 2)])
    assert [total for _, total in totals] == [0, 1, 3]


def test_total_restarts_after_dublin_midnight():
    totals = running_totals([(at(-1), 2), (at(-0.5), 2), (at(0.5), 2)])
    assert [total for _, total in totals] == [0, 1, 0]


def test_only_the_last_day_is_scaled_to_the_inverter_counter():
    totals = running_totals([(at(-1), 2), (at(-0.5), 2), (at(0.5), 2), (at(1), 2)], today_kwh=3)
    assert [total for _, total in totals] == [0, 1, 0, 3]


def test_values_interpolate_within_a_day_and_keep_gaps():
    totals = [(at(1), 0), (at(2), 4)]
    assert values_at(totals, [at(0.5), at(1.5), None, at(3)]) == [None, 2, None, 4]


def test_solar_today_excludes_battery_discharge_counted_in_daily_yield():
    # Inverter readings at 20:49 on 15 September 2026; FusionSolar reported 22.46 kWh produced.
    assert solar_today_kwh({'energy_today_kwh': 25.18, 'discharged_today_kwh': 2.7}) == pytest.approx(22.48)
    assert solar_today_kwh({'energy_today_kwh': 25.18}) is None


def test_solar_totals_include_energy_from_before_the_window(seeded):
    # The 12-hour chart starts an hour after midnight.
    store, current, history, positions = seeded
    energy = energy_history(store, NOW, current, history, positions, 'pv_kw')
    assert energy[0] == pytest.approx(1)
    assert energy[-1] == pytest.approx(13)
    scaled = energy_history(store, NOW, current, history, positions, 'pv_kw', today_kwh=26)
    assert scaled[0] == pytest.approx(2)
    assert scaled[-1] == pytest.approx(26)


def test_home_totals_use_home_power_without_a_counter(seeded):
    store, current, history, positions = seeded
    energy = energy_history(store, NOW, current, history, positions, 'home_kw')
    assert energy[0] == pytest.approx(0.5)
    assert energy[-1] == pytest.approx(6.5)


def test_energy_scale_rounds_up_to_tens():
    assert renderer.energy_scale([]) == 10
    assert renderer.energy_scale([None, 25.05]) == 30


def test_latest_total_is_labelled_at_the_right_end():
    def chart(show_latest):
        image = Image.new('1', (300, 150), 1)
        renderer.draw_power_history(ImageDraw.Draw(image), (10, 10, 290, 140), [0, 25.05],
                                    scale_max=30, guide_kw=15, unit='kWh', show_latest=show_latest)
        return image

    region = (200, 10, 291, 141)
    assert chart(False).crop(region).tobytes() != chart(True).crop(region).tobytes()
    assert chart(False).crop((0, 0, 150, 150)).tobytes() == chart(True).crop((0, 0, 150, 150)).tobytes()


def test_energy_charts_only_on_request():
    history = {'pv_kw': [0, 2.5], 'pv_kwh': [0, 25.05], 'home_kw': [0.2, 0.3], 'home_kwh': [0, 9.4],
               'battery_soc': [70, 73]}
    reading = dict(pv_kw=2.5, home_kw=0.3, battery_soc=73)
    now = mock_clock.get_now()
    image = renderer.render(reading, now, history=history, charts='energy')
    assert (image.size, image.mode) == ((800, 600), '1')
    assert (renderer.render_png(reading, now, history=history)
            != renderer.render_png(reading, now, history=history, charts='energy'))
