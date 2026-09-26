"""Pure drawing code for the 800x600 1-bit Kindle solar dashboard."""

import io
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from discharge.power import remaining_energy_kwh
from kindle_dashboard.estimate import clock_text, estimate_battery

WIDTH, HEIGHT = 800, 600
HISTORY_HOURS = 12
FLOW_ICON_MIN_KW = 0.1
FONT_DIR = Path(__file__).parent / "fonts"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(str(FONT_DIR / name), size)


def value(data: dict, name: str, default: float = 0.0) -> float:
    try:
        return float(data.get(name, default))
    except (TypeError, ValueError):
        return default


def centered(draw, xy, text, face, fill="black"):
    left, top, right, bottom = draw.textbbox((0, 0), text, font=face)
    x, y = xy
    draw.text((x - (right - left) / 2, y - (bottom - top) / 2 - top), text, font=face, fill=fill)


def reading_with_symbols(draw, center, text, face, before=None, after=None, gap=8):
    """Center the main reading independently of its smaller side symbols."""
    left, top, right, bottom = draw.textbbox((0, 0), text, font=face)
    x = center[0] - (right - left) / 2
    draw.text((x - left, center[1] - bottom), text, font=face, fill="black")
    for symbol, is_before in ((before, True), (after, False)):
        if symbol is None:
            continue
        label, symbol_font = symbol
        sl, st, sr, sb = draw.textbbox((0, 0), label, font=symbol_font)
        sx = x - gap - (sr - sl) if is_before else x + (right - left) + gap
        draw.text((sx - sl, center[1] - sb), label, font=symbol_font, fill="black")


def power_reading(draw, xy, reading):
    """Draw a fitted power reading and return the top of its number's bounds."""
    size = 132
    while size > 32:
        face = font(size, True)
        left, _, right, _ = draw.textbbox((0, 0), reading, font=face)
        if right - left <= 262:
            break
        size -= 2
    left, top, right, bottom = draw.textbbox((0, 0), reading, font=face)
    suffix_font = font(24)
    kl, _, kr, _ = draw.textbbox((0, 0), "k", font=suffix_font)
    x = min(xy[0], WIDTH - 12 - (kr - kl) - 4 - (right - left) / 2)
    reading_with_symbols(draw, (x, xy[1] + (bottom - top) / 2), reading, face,
                         after=("k", suffix_font), gap=4)
    return xy[1] - (bottom - top) / 2


def draw_sun(draw, center, radius=17):
    cx, cy = center
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline="black", width=3)
    for dx, dy in ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)):
        diagonal = dx and dy
        inner = radius + (2 if diagonal else 7)
        outer = radius + (8 if diagonal else 16)
        draw.line((cx + dx * inner, cy + dy * inner, cx + dx * outer, cy + dy * outer),
                  fill="black", width=3)


def draw_bolt(draw, center):
    cx, cy = center
    points = [
        (cx + 12, cy - 82), (cx - 48, cy + 8), (cx - 10, cy + 8),
        (cx - 25, cy + 82), (cx + 52, cy - 20), (cx + 12, cy - 20),
    ]
    points = [(cx + (x - cx) * 0.44, cy + (y - cy) * 0.44) for x, y in points]
    draw.polygon(points, fill="black")


def draw_battery(draw, box, soc, history: Sequence[float | None] = (), positions=None, target: int | None = None):
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=13, outline="black", width=7)
    terminal_width = 18
    terminal_height = int((y2 - y1) * 0.42)
    terminal_top = int((y1 + y2 - terminal_height) / 2)
    draw.rectangle((x2 + 7, terminal_top, x2 + 7 + terminal_width, terminal_top + terminal_height), fill="black")
    inner_left, inner_top = x1 + 12, y1 + 12
    inner_right, inner_bottom = x2 - 12, y2 - 12
    fill_width = round((inner_right - inner_left) * soc / 100)
    if fill_width > 0:
        draw.rectangle((inner_left, inner_top, inner_left + fill_width, inner_bottom), fill="black")
    if len(history) > 1:
        # Past 12 hours from left to right; charge percentage from bottom to top.
        # Anchor the latest sample to the displayed SOC at the positive end.
        samples = [*history[:-1], soc]
        points = [
            None if sample is None else
            (round((positions[i] if positions is not None else i / (len(samples) - 1)) * (inner_right - inner_left)),
             round((1 - max(0, min(100, sample)) / 100) * (inner_bottom - inner_top)))
            for i, sample in enumerate(samples)
        ]
        draw_battery_trace(draw, (inner_left, inner_top, inner_right, inner_bottom), fill_width, points)
    if target:
        draw_target_line(draw, (inner_left, inner_top, inner_right, inner_bottom), fill_width, target)


def draw_trace_segments(draw, points, **kwargs):
    """Leave missing intervals blank instead of connecting across a data gap."""
    segment = []
    for point in [*points, None]:
        if point is not None:
            segment.append(point)
        else:
            if len(segment) > 1:
                draw.line(segment, **kwargs)
            segment = []


def draw_battery_trace(draw, box, fill_width, points):
    """Clip the trace to the battery interior and invert it over the charge fill."""
    left, top, right, bottom = box
    trace = Image.new("1", (right - left + 1, bottom - top + 1), 0)
    # Over twice the power charts' line, to read from across the room
    draw_trace_segments(ImageDraw.Draw(trace), points, fill=1, width=7, joint="curve")
    draw_inverted(draw, (left, top), trace, fill_width)


def draw_inverted(draw, origin, mask, fill_width):
    """Draw a mask of the battery interior white over the charge fill and black beyond it."""
    left, top = origin
    width, height = mask.size
    # The fill rectangle includes its right edge. At 0% there is no fill.
    split = min(width, fill_width + 1) if fill_width > 0 else 0
    if split:
        draw.bitmap((left, top), mask.crop((0, 0, split, height)), fill="white")
    if split < width:
        draw.bitmap((left + split, top), mask.crop((split, 0, width, height)), fill="black")


def draw_target_line(draw, box, fill_width, target):
    """The daytime target: a dashed vertical line where the charge fill reaches at that %, its value below.

    Inverted over the fill like the history trace. The value sits at the foot of the line, inside the
    battery, in a white box like the chart scale labels.
    """
    left, top, right, bottom = box
    label, face = f"{target}%", font(17)
    ll, lt, lr, lb = draw.textbbox((0, 0), label, font=face, anchor="lt")
    label_top = bottom - (lb - lt) - 4
    x = round((right - left) * max(0, min(100, target)) / 100)
    line = Image.new("1", (right - left + 1, bottom - top + 1), 0)
    for y in range(0, label_top - top - 6, 14):
        ImageDraw.Draw(line).line((x, y, x, min(y + 8, label_top - top - 6)), fill=1, width=3)
    draw_inverted(draw, (left, top), line, fill_width)

    # Centered under the line, kept inside the battery near either end
    label_left = min(max(left + x - (lr - ll) / 2, left + 4), right - 4 - (lr - ll))
    bounds = draw.textbbox((label_left, label_top), label, font=face, anchor="lt")
    draw.rectangle((bounds[0] - 2, bounds[1] - 2, bounds[2] + 2, bounds[3] + 2), fill="white")
    draw.text((label_left, label_top), label, font=face, anchor="lt", fill="black")


def draw_battery_badge(draw, box, charging: bool, power_kw: float):
    """Borderless state icons above or below the terminal, outside the battery, with the battery power.

    The power goes on the far side of the icon from the terminal: above the charging bolt, below the
    discharging arrow, in the same small type as the grid export under the pylon.
    """
    _, top, right, bottom = box
    cx, cy = right + 32, top + 18 if charging else bottom - 18
    if charging:
        shape = [(8, -24), (-19, 5), (-4, 5), (-9, 24),
                 (20, -9), (4, -9)]
    else:
        shape = [(0, 22), (-18, 2), (-7, 2), (-7, -22),
                 (7, -22), (7, 2), (18, 2)]
    draw.polygon([(cx + round(x * 0.75), cy + round(y * 0.75)) for x, y in shape], fill="black")
    # A little left of the icon's center, clear of the column divider
    centered(draw, (cx - 4, cy - 36 if charging else cy + 36), f"{power_kw:.1f}k", font(20))


def draw_empty_battery(draw, box):
    """Small upright, unfilled battery with the positive terminal on top."""
    left, top, right, bottom = box
    draw.rectangle((left + 7, top, right - 7, top + 4), fill="black")
    draw.rounded_rectangle((left, top + 6, right, bottom), radius=3,
                           fill="white", outline="black", width=3)


def draw_sunset_time(draw, center_x, center_y, setting):
    """Small setting sun and today's local sunset time, centered as a group."""
    number, suffix = clock_text(setting)
    label, face = f"{number}{suffix}", font(20)
    left, top, right, bottom = draw.textbbox((0, 0), label, font=face)
    group_left = round(center_x - (36 + 10 + right - left) / 2)
    cx, horizon = group_left + 18, center_y + 8
    draw.arc((cx - 11, horizon - 11, cx + 11, horizon + 11),
             180, 360, fill="black", width=2)
    draw.line((cx - 18, horizon, cx + 18, horizon), fill="black", width=2)
    draw.text((group_left + 46 - left, center_y - (bottom - top) / 2 - top),
              label, font=face, fill="black")


def draw_grid_export(draw, center_x, top, export_kw):
    """A compact electricity pylon with the current export power below it."""
    cx, bottom = center_x, top + 52

    def stroke(coords):
        # Shrink the pylon around its bottom center, keeping the value in place.
        points = [(round(cx + (x - cx) * 0.75),
                   round(bottom + 3 + (y - bottom - 3) * 0.75))
                  for x, y in zip(coords[::2], coords[1::2])]
        draw.line(points, fill="black", width=2)

    stroke((cx - 6, top, cx + 6, top))
    stroke((cx - 6, top, cx - 22, bottom))
    stroke((cx + 6, top, cx + 22, bottom))
    for offset, reach in ((12, 24), (27, 28)):
        y = top + offset
        stroke((cx - reach, y, cx, y - 9, cx + reach, y, cx - reach, y))
        for x in (cx - reach, cx + reach):
            stroke((x, y, x, y + 6))
    for upper, lower in ((12, 27), (27, 40), (40, 52)):
        a, b = round(6 + 16 * upper / 52), round(6 + 16 * lower / 52)
        stroke((cx - a, top + upper, cx + b, top + lower))
        stroke((cx + a, top + upper, cx - b, top + lower))
    stroke((cx - 28, bottom + 3, cx + 28, bottom + 3))
    centered(draw, (cx, bottom + 27), f"{export_kw:.1f}k", font(20))


def draw_power_history(draw, box, samples: Sequence[float | None], *, scale_max=5.5, guide_kw=3, positions=None):
    """Draw twelve hours of power strictly within the plot's bounds."""
    left, top, right, bottom = box
    for level in (0, guide_kw, scale_max):
        y = round(bottom - level / scale_max * (bottom - top))
        for x in range(left, right, 8):
            draw.line((x, y, min(x + 2, right), y), fill="black")
    draw.line((left, bottom, right, bottom), fill="black", width=2)
    if len(samples) > 1:
        # A local mask clips the trace at the plot edge. Keep the true sample
        # values so over-range intervals disappear instead of flattening at max.
        trace = Image.new("1", (right - left + 1, bottom - top + 1), 0)
        points = [
            None if sample is None else
            (round((positions[i] if positions is not None else i / (len(samples) - 1)) * (right - left)),
             round((1 - max(0, sample) / scale_max) * (bottom - top)))
            for i, sample in enumerate(samples)
        ]
        draw_trace_segments(ImageDraw.Draw(trace), points, fill=1, width=3, joint="curve")
        draw.bitmap((left, top), trace, fill="black")
    # Place scale labels inside the plot, just below their dotted guide.
    label_font = font(17)
    for level in (scale_max, guide_kw):
        label = f"{level:g}"
        label_xy = (left + 8, round(bottom - level / scale_max * (bottom - top)) + 7)
        bounds = draw.textbbox(label_xy, label, font=label_font, anchor="lt")
        draw.rectangle((bounds[0] - 2, bounds[1] - 2, bounds[2] + 2, bounds[3] + 2), fill="white")
        draw.text(label_xy, label, font=label_font, anchor="lt", fill="black")


def draw_history_hours(draw, left, right, baseline, updated_at):
    """Label the start, midpoint, and present below the axis."""
    for fraction, anchor in ((0, "lt"), (0.5, "mt")):
        at = updated_at - timedelta(hours=HISTORY_HOURS * (1 - fraction))
        # Round to the closest hour; minutes are intentionally omitted.
        hour = (at + timedelta(minutes=30)).hour
        label = f"{hour % 12 or 12}{'a' if hour < 12 else 'p'}"
        x = round(left + fraction * (right - left))
        draw.text((x, baseline + 7), label, font=font(17), anchor=anchor, fill="black")
    draw.text((right, baseline + 7), "now", font=font(17), anchor="rt", fill="black")


def render(data: dict, updated_at: datetime, stale: bool = False, *,
           history: dict[str, Sequence[float | None]] | None = None, history_positions=None,
           daytime_target: int = 0) -> Image.Image:
    """Draw the dashboard; every history spans now − HISTORY_HOURS through now.

    Samples are ordered oldest to newest; None is a gap. Optional positions
    give true fractions of the 12-hour window for unevenly spaced history.
    Without positions samples are evenly spaced. `updated_at`
    is shown as-is in the legacy layout, so pass a Dublin-local time.
    A daytime target of 1-100% is marked on the battery; 0 is off.
    """
    image = Image.new("1", (WIDTH, HEIGHT), 1)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH - 1, HEIGHT - 1), outline="black", width=4)
    chart_layout = history is not None
    # Center the divider in the gap from the battery terminal (456) to charts (522).
    divider_x = 489 if chart_layout else 500
    draw.line((divider_x, 24, divider_x, HEIGHT - (24 if chart_layout else 52)), fill="black", width=3)

    if history is None:
        draw.line((522, 295, 776, 295), fill="black", width=3)
        power_reading(draw, (650, 127), f"{value(data, 'pv_kw'):.1f}")
        draw_sun(draw, (650, 235))
        power_reading(draw, (650, 400), f"{value(data, 'home_kw'):.1f}")
        draw_bolt(draw, (650, 500))
    else:
        # Two identical reading/chart groups, evenly spaced down the column.
        # The chart baselines remain axes; there is no separator between groups.
        for key, offset in (("pv_kw", 0), ("home_kw", 288)):
            chart_bottom = 270 + offset
            draw_power_history(draw, (522, 148 + offset, 776, chart_bottom), history.get(key, ()),
                               scale_max=5 if key == "pv_kw" else 3,
                               guide_kw=2 if key == "pv_kw" else 1, positions=history_positions)
            draw_history_hours(draw, 522, 776, chart_bottom, updated_at)
            # The current reading has its own space above the clipped chart.
            number_top = power_reading(draw, (650, 80 + offset), f"{value(data, key):.1f}")
            if key == "pv_kw":
                production_top = number_top

    # Left: align the visible battery digits with production, and the bottom
    # of the estimated empty time with the consumption chart's horizontal axis.
    estimate = estimate_battery(data.get("battery_soc"), updated_at)
    time_text, time_suffix = clock_text(estimate.empty_at) if estimate.empty_at else ("--:--", "")
    soc = max(0.0, min(100.0, value(data, "battery_soc")))
    soc_text, soc_font = f"{soc:.0f}", font(184, True)
    exporting = data.get("grid_importing") is False and value(data, "grid_kw") >= FLOW_ICON_MIN_KW
    if chart_layout and exporting:
        # Reserve the pylon's space even when SOC has three digits.
        size = 184
        while 250 - soc_font.getbbox(soc_text)[2] / 2 + soc_font.getmask(soc_text).getbbox()[0] < 112:
            size -= 2
            soc_font = font(size, True)
    soc_baseline, time_baseline = 185, 522
    if chart_layout:
        _, top, _, bottom = draw.textbbox((0, 0), soc_text, font=soc_font)
        soc_baseline = production_top + bottom - top
        time_baseline = chart_bottom + 1  # Text bounds exclude the last row.
    reading_with_symbols(draw, (250, soc_baseline), soc_text,
                         soc_font, after=("%", font(43)))
    if chart_layout:
        if exporting:
            draw_grid_export(draw, 60, 84, value(data, "grid_kw"))
        # Keep the percentage untouched; align the energy label with its left edge.
        number_left, _, number_right, _ = draw.textbbox((0, 0), soc_text, font=soc_font)
        pl, pt, pr, pb = draw.textbbox((0, 0), "%", font=font(43))
        percent_left = 250 + (number_right - number_left) / 2 + 8
        energy_y = (production_top + soc_baseline - (pb - pt)) / 2
        energy_text, energy_font = f"{remaining_energy_kwh(soc, 0):.1f}k", font(28)
        el, et, er, eb = draw.textbbox((0, 0), energy_text, font=energy_font)
        draw.text((percent_left - el, energy_y - (eb - et) / 2 - et),
                  energy_text, font=energy_font, fill="black")
    time_font = font(112, True)
    battery_box = (44, 253, 431, 351)
    if chart_layout:
        # Fill the available gap while preserving equal margins to the text.
        _, time_top, _, time_bottom = draw.textbbox((0, 0), "11:40", font=time_font)
        margin = 70
        battery_box = (44, round(soc_baseline + margin), 431,
                       round(time_baseline - (time_bottom - time_top) - margin))
    target = daytime_target if chart_layout and 0 < daytime_target <= 100 else None
    draw_battery(draw, battery_box, soc, history.get("battery_soc", ()) if chart_layout else (), positions=history_positions,
                 target=target)
    if chart_layout:
        charging = data.get("battery_charging")
        if value(data, "battery_charge_discharge_kw") >= FLOW_ICON_MIN_KW and isinstance(charging, bool):
            draw_battery_badge(draw, battery_box, charging, value(data, "battery_charge_discharge_kw"))
        draw_history_hours(draw, battery_box[0] + 12, battery_box[2] - 12, battery_box[3], updated_at)
    reading_with_symbols(draw, (250, time_baseline), time_text, time_font,
                         before=None if chart_layout else ("↓", font(38)), after=(time_suffix, font(38)))
    if chart_layout:
        text_left, _, text_right, _ = draw.textbbox((0, 0), time_text, font=time_font)
        icon_left = round(250 - (text_right - text_left) / 2 - 8 - 22)
        draw_empty_battery(draw, (icon_left, time_baseline - 38, icon_left + 22, time_baseline - 1))

    draw_sunset_time(draw, 250, time_baseline + 19, estimate.sunset)

    if not chart_layout:
        centered(draw, (WIDTH / 2, 568), updated_at.strftime("Updated %H:%M:%S"), font(17))

    if stale:
        draw.rectangle((4, 544, WIDTH - 5, HEIGHT - 5), fill="black")
        centered(draw, (WIDTH / 2, 570), "STALE DATA", font(21, True), fill="white")
    return image


def render_png(data: dict, updated_at: datetime, stale: bool = False, *,
               history: dict[str, Sequence[float | None]] | None = None, history_positions=None,
               daytime_target: int = 0) -> bytes:
    output = io.BytesIO()
    render(data, updated_at, stale, history=history, history_positions=history_positions,
           daytime_target=daytime_target).save(output, format="PNG", optimize=True)
    return output.getvalue()
