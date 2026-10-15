"""Animated Boston terrier whose mood follows the weather.

`sprite(mood, t)` returns an RGBA image of SIZE for time t in seconds. Shapes are drawn at SCALE times
the size and downsampled for smooth edges.

Moods:
  happy   sunny day: hops around a small circle, tongue out, tail wagging
  sit     partly cloudy: sits, tilts its head, blinks, wags
  cuddle  overcast or fog: curled up, nuzzling and breathing
  sleep   rain or a clear night: curled up asleep, breathing, with floating z's
  shiver  snow or thunderstorm: asleep and shivering now and then
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFilter

from . import art

SIZE = (64, 56)
SCALE = 4

BLACK = (30, 30, 34, 255)
WHITE = (244, 244, 246, 255)
PINK = (255, 128, 150, 255)
EAR = (90, 60, 66, 255)
EYE = (8, 8, 10, 255)
RIM = 70          # alpha of the light outline that separates the dog from dark backgrounds

MOODS = ("happy", "sit", "cuddle", "sleep", "shiver")


class _Pen:
    """Draws in sprite units (SIZE) onto a SCALE-times canvas."""

    def __init__(self, d: ImageDraw.ImageDraw):
        self.d = d

    def ellipse(self, cx, cy, rx, ry, fill):
        k = SCALE
        self.d.ellipse(((cx - rx) * k, (cy - ry) * k, (cx + rx) * k, (cy + ry) * k), fill=fill)

    def polygon(self, pts, fill):
        self.d.polygon([(x * SCALE, y * SCALE) for x, y in pts], fill=fill)

    def line(self, pts, fill, width):
        self.d.line([(x * SCALE, y * SCALE) for x, y in pts], fill=fill, width=int(width * SCALE), joint="curve")


def _sitting(p: _Pen, ox, oy, tilt=0.0, blink=False, tongue=False, wag=0.0):
    """Front view, sitting. (ox, oy) moves the whole dog; tilt moves the head sideways."""
    p.line([(ox + 41, oy + 46), (ox + 46 + wag * 3, oy + 40 - abs(wag))], BLACK, 3)      # tail
    p.ellipse(ox + 30, oy + 42, 14, 12, BLACK)                                           # body
    p.ellipse(ox + 30, oy + 43, 7, 9, WHITE)                                             # chest
    p.ellipse(ox + 23, oy + 53, 4.5, 2.6, WHITE)                                         # paws
    p.ellipse(ox + 37, oy + 53, 4.5, 2.6, WHITE)
    hx, hy = ox + 30 + tilt, oy + 22
    lean = tilt * 0.3
    p.polygon([(hx - 11, hy - 5), (hx - 16 - lean, hy - 22), (hx - 4, hy - 10)], BLACK)   # ears
    p.polygon([(hx + 11, hy - 5), (hx + 16 - lean, hy - 22), (hx + 4, hy - 10)], BLACK)
    p.polygon([(hx - 10, hy - 7), (hx - 14 - lean, hy - 18), (hx - 6, hy - 10)], EAR)
    p.polygon([(hx + 10, hy - 7), (hx + 14 - lean, hy - 18), (hx + 6, hy - 10)], EAR)
    p.ellipse(hx, hy, 13, 11, BLACK)                                                     # head
    p.polygon([(hx - 1.6, hy - 11), (hx + 1.6, hy - 11), (hx + 3, hy + 2), (hx - 3, hy + 2)], WHITE)
    p.ellipse(hx, hy + 5, 7, 5, WHITE)                                                   # muzzle
    p.ellipse(hx, hy + 2.6, 2.6, 1.8, BLACK)                                             # nose
    if tongue:
        p.ellipse(hx, hy + 9, 2.2, 2.6, PINK)
    for ex in (hx - 6, hx + 6):
        if blink:
            p.line([(ex - 2.6, hy - 1), (ex, hy), (ex + 2.6, hy - 1)], EYE, 1.1)
        else:
            p.ellipse(ex, hy - 1.5, 3.2, 3.2, EYE)
            p.ellipse(ex + 1, hy - 2.6, 1.0, 1.0, WHITE)


def _curled(p: _Pen, breath=0.0, nuzzle=0.0, shiver=0.0):
    """Side view, curled up on the ground. breath 0..1 inflates the body slightly."""
    sx = shiver
    p.ellipse(34 + sx, 45, 20, 9 + breath * 1.2, BLACK)                                  # body
    p.ellipse(26 + sx, 49, 7, 3.5 + breath * 0.5, WHITE)                                 # chest
    p.ellipse(51 + sx, 41, 3, 2, BLACK)                                                  # tail
    hx, hy = 17 + sx + nuzzle, 43 - abs(nuzzle) * 0.4
    p.ellipse(16 + sx, 52, 9, 3, WHITE)                                                  # paws
    p.polygon([(hx - 5, hy - 5), (hx - 9, hy - 15), (hx - 1, hy - 7)], BLACK)            # ears
    p.polygon([(hx + 3, hy - 6), (hx + 6, hy - 15), (hx + 7, hy - 4)], BLACK)
    p.ellipse(hx, hy, 10, 8, BLACK)                                                      # head
    p.polygon([(hx - 1, hy - 8), (hx + 1.4, hy - 8), (hx - 1.5, hy + 1), (hx - 4, hy + 1)], WHITE)
    p.ellipse(hx - 5, hy + 3, 5, 3.4, WHITE)                                             # muzzle
    p.ellipse(hx - 9, hy + 1.6, 1.8, 1.4, BLACK)                                         # nose
    for ex in (hx - 4.5, hx + 3):                                                        # closed eyes
        p.line([(ex - 2, hy - 2), (ex, hy - 1), (ex + 2, hy - 2)], EYE, 1.0)


def _zzz(d: ImageDraw.ImageDraw, t: float):
    for i in range(3):
        phase = (t / 3.0 + i / 3.0) % 1.0          # each z rises and fades over 3 s
        x, y = 40 + phase * 14, 30 - phase * 26
        size = int(9 * SCALE * (0.6 + phase * 0.6))
        d.text((x * SCALE, y * SCALE), "z", font=art.font(size, "Semibold", rounded=True),
               fill=(235, 235, 245, int(230 * (1 - phase))))


def sprite(mood: str, t: float) -> Image.Image:
    img = Image.new("RGBA", (SIZE[0] * SCALE, SIZE[1] * SCALE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    p = _Pen(d)
    if mood == "happy":
        a = t * math.pi                            # one lap every 2 s
        _sitting(p, math.cos(a) * 8, 2 - abs(math.sin(a * 2)) * 7, tilt=math.sin(a) * 3,
                 tongue=True, wag=math.sin(t * 12))
    elif mood == "sit":
        _sitting(p, 0, 2, tilt=math.sin(t * 0.8) * 3, blink=(t % 4.0) < 0.3, wag=math.sin(t * 6))
    elif mood == "cuddle":
        _curled(p, breath=(math.sin(t * 1.6) + 1) / 2, nuzzle=math.sin(t * 2.2) * 2.2)
    else:
        shiver = math.sin(t * 25) * 0.8 if mood == "shiver" and (t % 3.0) < 1.0 else 0.0
        _curled(p, breath=(math.sin(t * 1.4) + 1) / 2, shiver=shiver)
        _zzz(d, t)
    rim = img.getchannel("A").filter(ImageFilter.MaxFilter(2 * SCALE + 1)).point(lambda v: RIM if v else 0)
    out = Image.new("RGBA", img.size, (255, 255, 255, 0))
    out.putalpha(rim)
    out.alpha_composite(img)
    return out.resize(SIZE, Image.LANCZOS)


def mood_for(code: int | None, is_day: bool) -> str:
    """Mood for a WMO weather code; None (no weather) sleeps."""
    if code is None:
        return "sleep"
    if code in (0, 1):
        return "happy" if is_day else "sleep"
    if code == 2:
        return "sit" if is_day else "sleep"
    if code in (3, 45, 48):
        return "cuddle"
    if code in art.SNOW_CODES or code >= 95:
        return "shiver"
    return "sleep"
