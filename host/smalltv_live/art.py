"""Drawing primitives: fonts, wallpaper, frosted glass cards, weather icons, usage rings."""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SANS = Path("/System/Library/Fonts/SFNS.ttf")
ROUNDED = Path("/System/Library/Fonts/SFNSRounded.ttf")

WHITE = (255, 255, 255)
TEXT = (255, 255, 255, 242)
TEXT2 = (235, 235, 245, 165)
TEXT3 = (235, 235, 245, 110)
ACCENT = (217, 119, 87)
AMBER = (255, 179, 64)
RED = (255, 105, 97)
SUN = (255, 214, 10)
RAIN = (100, 210, 255)
CLOUD = (235, 235, 240)


@lru_cache(maxsize=64)
def font(size: int, weight: str = "Regular", rounded: bool = False) -> ImageFont.FreeTypeFont:
    """San Francisco (macOS system font) when available, else Pillow's bundled font."""
    path = ROUNDED if rounded else SANS
    if path.exists():
        f = ImageFont.truetype(str(path), size)
        try:
            f.set_variation_by_name(weight)
        except (OSError, ValueError):
            pass
        return f
    return ImageFont.load_default(size)


def composite(img: Image.Image, layer: Image.Image) -> None:
    img.paste(Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB"))


def overlay(img: Image.Image) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    return layer, ImageDraw.Draw(layer)


def wallpaper(size: int) -> Image.Image:
    """Dark wallpaper of soft colour blobs, heavily blurred."""
    img = Image.new("RGB", (size, size), (12, 14, 30))
    d = ImageDraw.Draw(img)
    for cx, cy, r, col in ((0.15, 0.10, 0.55, (88, 64, 220)), (0.95, 0.35, 0.45, (40, 110, 230)),
                           (0.80, 1.00, 0.60, (235, 110, 80)), (0.10, 0.85, 0.40, (150, 60, 170))):
        d.ellipse(((cx - r) * size, (cy - r) * size, (cx + r) * size, (cy + r) * size), fill=col)
    return img.filter(ImageFilter.GaussianBlur(size / 10))


def glass(img: Image.Image, box: tuple[int, int, int, int], radius: int, scale: int) -> None:
    """Frosted card: soft shadow, blurred and lightened background, hairline edge."""
    x0, y0, x1, y1 = (v * scale for v in box)
    r = radius * scale
    shadow, sd = overlay(img)
    sd.rounded_rectangle((x0, y0 + 2 * scale, x1, y1 + 4 * scale), r, fill=(0, 0, 0, 70))
    composite(img, shadow.filter(ImageFilter.GaussianBlur(6 * scale)))
    region = img.crop((x0, y0, x1, y1)).filter(ImageFilter.GaussianBlur(10 * scale))
    region = Image.blend(region, Image.new("RGB", region.size, WHITE), 0.13)
    mask = Image.new("L", region.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, region.size[0] - 1, region.size[1] - 1), r, fill=255)
    img.paste(region, (x0, y0), mask)
    edge, ed = overlay(img)
    ed.rounded_rectangle((x0, y0, x1 - 1, y1 - 1), r, outline=(255, 255, 255, 60), width=scale)
    composite(img, edge)


# ------------------------------------------------------------------ weather icons

SNOW_CODES = {71, 73, 75, 77, 85, 86}


def _cloud(d, cx, cy, s, col=CLOUD):
    d.ellipse((cx - 0.55 * s, cy - 0.05 * s, cx - 0.05 * s, cy + 0.45 * s), fill=col)
    d.ellipse((cx - 0.30 * s, cy - 0.40 * s, cx + 0.25 * s, cy + 0.15 * s), fill=col)
    d.ellipse((cx + 0.00 * s, cy - 0.20 * s, cx + 0.50 * s, cy + 0.30 * s), fill=col)
    d.rounded_rectangle((cx - 0.30 * s, cy + 0.05 * s, cx + 0.30 * s, cy + 0.45 * s), 0.2 * s, fill=col)


def _sun(d, cx, cy, s):
    r = 0.26 * s
    for k in range(8):
        a = k * math.pi / 4
        d.line((cx + math.cos(a) * r * 1.45, cy + math.sin(a) * r * 1.45,
                cx + math.cos(a) * r * 1.95, cy + math.sin(a) * r * 1.95),
               fill=SUN, width=max(2, int(0.08 * s)))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=SUN)


def _moon(img, cx, cy, s):
    layer, d = overlay(img)
    mask = Image.new("L", img.size, 0)
    md = ImageDraw.Draw(mask)
    r = 0.32 * s
    md.ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    md.ellipse((cx - r + 0.24 * s, cy - r - 0.10 * s, cx + r + 0.24 * s, cy + r - 0.10 * s), fill=0)
    d.bitmap((0, 0), mask, fill=(235, 235, 210))
    composite(img, layer)


def weather_icon(img: Image.Image, cx: float, cy: float, s: float, code: int, is_day: bool) -> None:
    """Weather glyph for a WMO code, drawn with primitives. Coordinates in image pixels."""
    if code in (0, 1, 2):
        sx, sy, ss = (cx, cy, s) if code == 0 else (cx - 0.2 * s, cy - 0.2 * s, 0.8 * s)
        if is_day:
            layer, d = overlay(img)
            _sun(d, sx, sy, ss)
            composite(img, layer)
        else:
            _moon(img, sx, sy, ss)
        if code == 0:
            return
    layer, d = overlay(img)
    if code in (1, 2):
        _cloud(d, cx + 0.08 * s, cy + 0.12 * s, 0.85 * s)
    elif code in (45, 48):
        for i, w in enumerate((0.8, 0.6, 0.8)):
            y = cy - 0.25 * s + i * 0.25 * s
            d.rounded_rectangle((cx - w / 2 * s, y - 0.05 * s, cx + w / 2 * s, y + 0.05 * s), 0.05 * s, fill=CLOUD)
    else:
        precip = code >= 51
        _cloud(d, cx, cy - (0.15 * s if precip else 0), 0.9 * s if precip else s)
        if code in SNOW_CODES:
            for dx in (-0.25, 0, 0.25):
                d.ellipse((cx + dx * s - 0.06 * s, cy + 0.40 * s, cx + dx * s + 0.06 * s, cy + 0.52 * s), fill=WHITE)
        elif code >= 95:
            pts = [(0.05, 0.22), (-0.12, 0.48), (0.02, 0.48), (-0.06, 0.70), (0.16, 0.40), (0.02, 0.40), (0.10, 0.22)]
            d.polygon([(cx + x * s, cy + y * s) for x, y in pts], fill=SUN)
        elif precip:
            for dx in (-0.25, 0, 0.25):
                x = cx + dx * s
                d.line((x + 0.05 * s, cy + 0.34 * s, x - 0.04 * s, cy + 0.56 * s),
                       fill=RAIN, width=max(2, int(0.08 * s)))
    composite(img, layer)


def raindrop(d: ImageDraw.ImageDraw, x: float, y: float, k: float) -> None:
    d.polygon([(x, y - 6 * k), (x - 3 * k, y - 1 * k), (x + 3 * k, y - 1 * k)], fill=RAIN)
    d.ellipse((x - 3 * k, y - 3.5 * k, x + 3 * k, y + 2.5 * k), fill=RAIN)


# ------------------------------------------------------------------ usage

def ring(d: ImageDraw.ImageDraw, cx: float, cy: float, r: float, width: int, pct: float | None, col) -> None:
    box = (cx - r, cy - r, cx + r, cy + r)
    d.ellipse(box, outline=(255, 255, 255, 38), width=width)
    if pct is None or pct <= 0:
        return
    end = -90 + 360 * min(pct, 100) / 100
    d.arc(box, -90, end, fill=col, width=width)
    rr = r - width / 2
    for a in (-90, end):    # round caps
        x, y = cx + rr * math.cos(math.radians(a)), cy + rr * math.sin(math.radians(a))
        d.ellipse((x - width / 2, y - width / 2, x + width / 2, y + width / 2), fill=col)


def spark(d: ImageDraw.ImageDraw, cx: float, cy: float, r: float, col) -> None:
    """Six-spoke spark mark."""
    for k in range(6):
        a = k * math.pi / 6
        d.line((cx - math.cos(a) * r, cy - math.sin(a) * r, cx + math.cos(a) * r, cy + math.sin(a) * r),
               fill=col, width=max(2, int(r / 3)))


def usage_colour(pct: float):
    return RED if pct >= 90 else AMBER if pct >= 70 else ACCENT
