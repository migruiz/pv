"""Pure drawing code for the 800x600 1-bit Kindle solar dashboard."""

import io
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 800, 600
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
    """Largest bold reading that fits the power column, with a small 'k' suffix."""
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


def draw_battery(draw, box, soc):
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


def render(data: dict, updated_at: datetime, stale: bool = False) -> Image.Image:
    """Draw the dashboard. `updated_at` is shown as-is, so pass a Dublin-local time."""
    image = Image.new("1", (WIDTH, HEIGHT), 1)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH - 1, HEIGHT - 1), outline="black", width=4)
    draw.line((500, 24, 500, HEIGHT - 52), fill="black", width=3)

    # Left: battery state. The empty time is a visual placeholder until the
    # prediction method has been agreed.
    soc = max(0.0, min(100.0, value(data, "battery_soc")))
    reading_with_symbols(draw, (250, 185), f"{soc:.0f}", font(184, True), after=("%", font(43)))
    draw_battery(draw, (44, 253, 431, 351), soc)
    reading_with_symbols(draw, (250, 522), "11:40", font(112, True),
                         before=("↓", font(38)), after=("p", font(38)))

    # Right: icon-only live power readings.
    power_reading(draw, (650, 127), f"{value(data, 'pv_kw'):.1f}")
    draw_sun(draw, (650, 235))
    draw.line((522, 295, 776, 295), fill="black", width=3)
    power_reading(draw, (650, 400), f"{value(data, 'home_kw'):.1f}")
    draw_bolt(draw, (650, 500))

    centered(draw, (WIDTH / 2, 568), updated_at.strftime("Updated %H:%M:%S"), font(17))

    if stale:
        draw.rectangle((4, 544, WIDTH - 5, HEIGHT - 5), fill="black")
        centered(draw, (WIDTH / 2, 570), "STALE DATA", font(21, True), fill="white")
    return image


def render_png(data: dict, updated_at: datetime, stale: bool = False) -> bytes:
    output = io.BytesIO()
    render(data, updated_at, stale).save(output, format="PNG", optimize=True)
    return output.getvalue()
