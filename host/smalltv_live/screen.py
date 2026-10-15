"""Screen layout: two frosted cards on a blurred wallpaper.

Top card: clock with seconds, date, temperature, high/low and rain chance, and a weather scene (icon and
the dog). Bottom card: Claude usage rings for the five-hour session and the week, with reset times.

Everything that changes at most once a minute is drawn into a static layer at SCALE times the resolution
and downsampled. Each frame then only adds the seconds and the dog.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from PIL import Image, ImageDraw

from . import art, dog, usage as usage_mod
from .config import Config
from .i18n import strings
from .weather import Weather

W = H = 240
SCALE = 3
CARD_TOP = (8, 8, 232, 118)
CARD_BOTTOM = (8, 126, 232, 232)
SCENE_X = 178
DOG_AT = (SCENE_X - dog.SIZE[0] // 2, 58)
SECONDS_COLOUR = (200, 200, 215)


@dataclass
class _Static:
    image: Image.Image
    seconds_at: tuple[float, float]


class Screen:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.text = strings(cfg.display.language)
        self.tz = cfg.tz
        self._wallpaper = art.wallpaper(W * SCALE)
        self._static: dict[datetime, _Static] = {}
        self._seconds_font = art.font(15, "Medium", rounded=True)

    # -------------------------------------------------------------- static layer

    def _reset_label(self, epoch: float | None, now: datetime) -> str:
        if not epoch:
            return ""
        t = datetime.fromtimestamp(epoch, self.tz)
        if t.date() == now.date():
            return f"↻ {t:%H:%M}"
        return f"↻ {self.text.days[t.weekday()]} {t:%H:%M}"

    def _draw_static(self, minute: datetime, weather: Weather | None, use: usage_mod.Usage) -> _Static:
        k, tx = SCALE, self.text
        img = self._wallpaper.copy()
        art.glass(img, CARD_TOP, 16, k)
        art.glass(img, CARD_BOTTOM, 16, k)
        layer, d = art.overlay(img)

        # top card, left: clock, date, temperature
        hm = f"{minute:%H:%M}"
        f_time = art.font(28 * k, "Semibold", rounded=True)
        d.text((20 * k, 14 * k), hm, font=f_time, fill=art.TEXT)
        seconds_at = (20 + f_time.getlength(hm) / k + 2, 26)
        d.text((20 * k, 50 * k), f"{tx.days[minute.weekday()]} {minute.day} {tx.months[minute.month - 1]}",
               font=art.font(12 * k, "Medium"), fill=art.TEXT2)
        if weather:
            f_temp = art.font(24 * k, "Medium", rounded=True)
            temp = f"{weather.temperature}°"
            d.text((20 * k, 74 * k), temp, font=f_temp, fill=art.TEXT)
            x = 20 + f_temp.getlength(temp) / k + 8
            f_small = art.font(11 * k, "Medium")
            d.text((x * k, 78 * k), f"{weather.high}° / {weather.low}°", font=f_small, fill=art.TEXT2)
            art.raindrop(d, (x + 3) * k, 99 * k, k)
            d.text(((x + 9) * k, 92 * k), f"{weather.rain_chance}%", font=f_small, fill=art.TEXT2)
            art.composite(img, layer)
            art.weather_icon(img, SCENE_X * k, 31 * k, 30 * k, weather.code, weather.is_day)
            layer, d = art.overlay(img)
        else:
            d.text((20 * k, 74 * k), "--°", font=art.font(24 * k, "Medium", rounded=True), fill=art.TEXT3)

        # bottom card: usage rings with the title in between
        stale = use.is_stale(self.cfg.usage.stale_after_minutes * 60)
        art.spark(d, 120 * k, 160 * k, 7 * k, art.ACCENT)
        d.text((120 * k, 180 * k), tx.usage_title, font=art.font(12 * k, "Semibold"), fill=art.TEXT, anchor="mm")
        note_font = art.font(10 * k, "Medium")
        if use.age_seconds is None:
            d.text((120 * k, 195 * k), tx.no_data, font=note_font, fill=art.TEXT3, anchor="mm")
        elif stale:
            d.text((120 * k, 195 * k), tx.minutes_ago.format(n=int(use.age_seconds // 60)),
                   font=note_font, fill=art.AMBER, anchor="mm")
        for cx, limit, label in ((62, use.five_hour, tx.session), (178, use.seven_day, tx.week)):
            pct = limit.used_percentage
            col = art.TEXT3 if pct is None or stale else art.usage_colour(pct)
            art.ring(d, cx * k, 169 * k, 30 * k, 7 * k, pct, col)
            d.text((cx * k, 169 * k), "--" if pct is None else f"{pct:.0f}%",
                   font=art.font(19 * k, "Semibold", rounded=True), fill=art.TEXT, anchor="mm")
            d.text((cx * k, 210 * k), label, font=art.font(12 * k, "Semibold"), fill=art.TEXT, anchor="mm")
            d.text((cx * k, 224 * k), self._reset_label(limit.resets_at, minute),
                   font=note_font, fill=art.TEXT2, anchor="mm")
        art.composite(img, layer)
        return _Static(img.resize((W, H), Image.LANCZOS), seconds_at)

    def static(self, minute: datetime, weather: Weather | None) -> _Static:
        if minute not in self._static:
            use = usage_mod.read(self.cfg.usage.cache_path)
            self._static = {m: s for m, s in self._static.items() if m >= minute}
            self._static[minute] = self._draw_static(minute, weather, use)
        return self._static[minute]

    def prepare_next_minute(self, now: float, weather: Weather | None) -> None:
        """Draw the next minute's static layer ahead of time so the minute change doesn't stall."""
        t = datetime.fromtimestamp(now, self.tz)
        if t.second >= 56:
            self.static(t.replace(second=0, microsecond=0) + timedelta(minutes=1), weather)

    # -------------------------------------------------------------- frames

    def frame(self, now: float | None = None, weather: Weather | None = None) -> Image.Image:
        now = time.time() if now is None else now
        t = datetime.fromtimestamp(now, self.tz)
        st = self.static(t.replace(second=0, microsecond=0), weather)
        img = st.image.copy()
        spr = dog.sprite(dog.mood_for(weather.code if weather else None, weather.is_day if weather else False), now)
        img.paste(spr, DOG_AT, spr)
        ImageDraw.Draw(img).text(st.seconds_at, f":{t.second:02d}", font=self._seconds_font, fill=SECONDS_COLOUR)
        return img
