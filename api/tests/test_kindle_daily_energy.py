"""Today's running solar and home energy for the chart layout, and the switch between chart kinds."""

from datetime import date, datetime, time, timezone

import pytest
from PIL import Image, ImageChops, ImageDraw

import mock_clock
from kindle_dashboard import renderer
from kindle_dashboard.daily_energy import (chart_history, charts_at, energy_chart, running_totals,
                                           solar_today_kwh, values_at)
from kindle_dashboard.estimate import daylight
from kindle_dashboard.history import HistoryStore

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)  # 13:00 in Dublin
MIDNIGHT = datetime(2026, 9, 14, 23, 0, tzinfo=timezone.utc).timestamp()  # Dublin midnight


def at(hours_after_midnight):
    return MIDNIGHT + hours_after_midnight * 3600


def record(store, start, end, every_minutes=5):
    """A constant 1 kW solar and 0.5 kW home between two timestamps; returns the reading at `end`."""
    for stamp in range(int(start), int(end) + 1, every_minutes * 60):
        reading = dict(updated_at=datetime.fromtimestamp(stamp, timezone.utc).isoformat(),
                       pv_kw=1, home_kw=0.5, battery_soc=73)
        store.record(reading)
    return reading


@pytest.fixture
def store(tmp_path):
    result = HistoryStore(tmp_path / 'history.sqlite3')
    yield result
    result.close()


@pytest.fixture
def seeded(store):
    """From Dublin midnight until 13:00."""
    return store, record(store, MIDNIGHT, NOW.timestamp())


def test_trapezoids_add_up_power_into_energy():
    totals = running_totals([(at(1), 0), (at(2), 2), (at(3), 2)])
    assert [total for _, total in totals] == [0, 1, 3]


def test_totals_are_scaled_to_the_inverter_counter():
    totals = running_totals([(at(1), 2), (at(1.5), 2), (at(2), 2)], today_kwh=3)
    assert [total for _, total in totals] == [0, 1.5, 3]


def test_values_interpolate_and_keep_gaps():
    totals = [(at(1), 0), (at(2), 4)]
    assert values_at(totals, [at(0.5), at(1.5), None, at(3)]) == [None, 2, None, 4]


def test_solar_today_excludes_battery_discharge_counted_in_daily_yield():
    # Inverter readings at 20:49 on 15 September 2026; FusionSolar reported 22.46 kWh produced.
    assert solar_today_kwh({'energy_today_kwh': 25.18, 'discharged_today_kwh': 2.7}) == pytest.approx(22.48)
    assert solar_today_kwh({'energy_today_kwh': 25.18}) is None


def test_energy_chart_runs_from_midnight_to_midnight(seeded):
    store, current = seeded
    chart = energy_chart(store, NOW, current, 'pv_kw')
    assert (chart.positions[0], chart.samples[0]) == (0, 0)
    assert (chart.positions[-1], chart.samples[-1]) == (pytest.approx(13 / 24), pytest.approx(13))
    assert chart.hours == [(0, '12a'), (0.5, '12p'), (1, '12a')]
    assert chart.mark is None
    assert energy_chart(store, NOW, current, 'pv_kw', today_kwh=26).samples[-1] == pytest.approx(26)


def test_production_chart_leaves_out_the_night(seeded):
    # 15 September 2026 in Dublin: sunrise 06:58, sunset 19:40, so the chart runs 05:58 to 20:40
    store, current = seeded
    rise, setting = daylight(date(2026, 9, 15))
    first, last = rise.timestamp() - 3600, setting.timestamp() + 3600
    chart = energy_chart(store, NOW, current, 'pv_kw', daylight_only=True)
    assert (chart.hours[0][1], chart.hours[2][1]) == ('6a', '9p')
    assert chart.hours[1] == (pytest.approx((at(12) - first) / (last - first)), '12p')
    assert chart.positions[-1] == pytest.approx((NOW.timestamp() - first) / (last - first))
    assert chart.positions[0] < 0  # the total still starts at midnight, off the left edge
    assert chart.samples[-1] == pytest.approx(13)


def test_home_chart_marks_its_total_when_the_night_rate_ends(seeded):
    store, current = seeded
    chart = energy_chart(store, NOW, current, 'home_kw', mark=time(5))
    assert chart.samples[-1] == pytest.approx(6.5)
    assert chart.mark == (pytest.approx(5 / 24), '5a', pytest.approx(2.5))


def test_mark_has_no_total_before_its_time(store):
    current = record(store, MIDNIGHT, at(3))
    now = datetime.fromtimestamp(at(3), timezone.utc)
    assert energy_chart(store, now, current, 'home_kw', mark=time(5)).mark == (pytest.approx(5 / 24), '5a', None)


def test_yesterday_is_left_out(store):
    current = record(store, at(-6), at(6))
    now = datetime.fromtimestamp(at(6), timezone.utc)
    chart = energy_chart(store, now, current, 'pv_kw')
    assert (chart.positions[0], chart.samples[0], chart.samples[-1]) == (0, 0, pytest.approx(6))


def test_daylight_saving_day_keeps_its_hours_in_place(store):
    # 25 October 2026 has 25 hours: midnight is 23:00 UTC the day before, 05:00 and noon are UTC hours.
    midnight = datetime(2026, 10, 24, 23, 0, tzinfo=timezone.utc).timestamp()
    now = datetime(2026, 10, 25, 13, 0, tzinfo=timezone.utc)
    current = record(store, midnight, now.timestamp())
    chart = energy_chart(store, now, current, 'home_kw', mark=time(5))
    assert chart.hours[1] == (pytest.approx(13 / 25), '12p')
    assert chart.mark == (pytest.approx(6 / 25), '5a', pytest.approx(3))
    assert chart.samples[-1] == pytest.approx(7)


def test_energy_charts_only_when_the_charts_show_energy(seeded):
    store, current = seeded
    assert chart_history(store, NOW, current, 'power')[2] is None
    history, positions, energy = chart_history(store, NOW, current, 'energy')
    assert history['battery_soc'] and positions  # the battery keeps its 12-hour history
    assert (energy['pv_kw'].mark, energy['home_kw'].mark[1]) == (None, '5a')
    assert (energy['pv_kw'].hours[0][1], energy['home_kw'].hours[0][1]) == ('6a', '12a')  # daylight, whole day


def test_charts_switch_every_10_seconds():
    assert [charts_at(seconds) for seconds in (0, 9.9, 10, 19.9, 20)] == [
        'power', 'power', 'energy', 'energy', 'power']


def test_energy_scale_keeps_the_line_in_the_lower_60_percent():
    assert renderer.energy_scale([]) == 10
    assert renderer.energy_scale([None, 6]) == 10
    assert renderer.energy_scale([6.1]) == 20
    assert renderer.energy_scale([None, 25.05]) == 50


BOX = (10, 10, 290, 140)


def draw(chart_or_samples, total=False):
    image = Image.new('1', (300, 170), 1)
    canvas = ImageDraw.Draw(image)
    if isinstance(chart_or_samples, renderer.EnergyChart):
        renderer.draw_energy_chart(canvas, BOX, chart_or_samples)
    else:
        renderer.draw_power_history(canvas, BOX, chart_or_samples, scale_max=30, guide_kw=15)
        if total:
            renderer.draw_latest_total(canvas, BOX, chart_or_samples)
    return image.convert('L')


def changed(a, b):
    return ImageChops.difference(a, b).getbbox()


def test_latest_total_sits_top_right_clear_of_the_line():
    # The highest line the energy scale allows: 60% of the way up
    left, top, right, bottom = changed(draw([18, 18], total=True), draw([18, 18]))
    line_top = round(140 - 0.6 * 130) - 1
    assert right > 280 and top > 10 and bottom < line_top - 3
    assert left > 100  # the scale labels on the left stay as they are


def test_mark_reads_off_the_total_from_both_axes():
    chart = renderer.EnergyChart(samples=[0, 3, 4], positions=[0, 5 / 24, 0.5], hours=[(0, '12a')])
    marked = renderer.EnergyChart(**{**chart.__dict__, 'mark': (5 / 24, '5a', 3.0)})
    left, top, right, bottom = changed(draw(marked), draw(chart))
    mark_x = 10 + round(5 / 24 * 280)
    assert left <= 12 and right < mark_x + 15  # from the y axis to the 5a label under the mark
    assert bottom > 140  # the bold 5a below the axis
    assert top > 140 - 130 * 3 / 10 - 25  # the total written just above its dashed line


def test_before_the_mark_only_its_time_is_marked():
    chart = renderer.EnergyChart(samples=[0, 1], positions=[0, 3 / 24], hours=[(0, '12a')])
    marked = renderer.EnergyChart(**{**chart.__dict__, 'mark': (5 / 24, '5a', None)})
    left, top, right, bottom = changed(draw(marked), draw(chart))
    mark_x = 10 + round(5 / 24 * 280)
    assert mark_x - 15 < left and right < mark_x + 15 and top <= 12 and bottom > 140


def test_energy_charts_only_on_request():
    history = {'pv_kw': [0, 2.5], 'home_kw': [0.2, 0.3], 'battery_soc': [70, 73]}
    energy = {'pv_kw': renderer.EnergyChart([0, 25.05], [0, 0.5], [(0, '12a')]),
              'home_kw': renderer.EnergyChart([0, 9.4], [0, 0.5], [(0, '12a')], (5 / 24, '5a', 4.0))}
    reading = dict(pv_kw=2.5, home_kw=0.3, battery_soc=73)
    now = mock_clock.get_now()
    image = renderer.render(reading, now, history=history, energy=energy)
    assert (image.size, image.mode) == ((800, 600), '1')
    assert (renderer.render_png(reading, now, history=history)
            != renderer.render_png(reading, now, history=history, energy=energy))
