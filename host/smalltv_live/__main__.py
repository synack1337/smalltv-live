"""Command line: `python -m smalltv_live {run,preview,statusline}`."""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

from . import __version__, display, weather as weather_mod
from .config import Config, ConfigError, load
from .screen import Screen
from .usage import statusline

log = logging.getLogger("smalltv_live")
WEATHER_EVERY = 10 * 60
WEATHER_RETRY = 60
RECONNECT_DELAY = 3


class WeatherCache:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.value: weather_mod.Weather | None = None
        self.next_fetch = 0.0

    def get(self) -> weather_mod.Weather | None:
        loc = self.cfg.location
        if not loc.has_coordinates or time.time() < self.next_fetch:
            return self.value
        try:
            self.value = weather_mod.fetch(loc.latitude, loc.longitude, self.cfg.tz)
            self.next_fetch = time.time() + WEATHER_EVERY
        except Exception as exc:          # network or API trouble: keep the last value
            log.warning("weather update failed: %s", exc)
            self.next_fetch = time.time() + WEATHER_RETRY
        return self.value


def _backlight_level(cfg: Config, now: float) -> int:
    d = cfg.display
    hour = datetime.fromtimestamp(now, cfg.tz).hour
    if d.night_start > d.night_end:
        night = hour >= d.night_start or hour < d.night_end
    else:
        night = d.night_start <= hour < d.night_end
    return d.brightness_night if night else d.brightness_day


def run(cfg: Config) -> int:
    screen, weather, link = Screen(cfg), WeatherCache(cfg), display.Link(cfg.tv.host, cfg.tv.port)
    step = 1.0 / cfg.display.fps
    stop = False

    def _stop(*_):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    while not stop:
        try:
            link.open()
            log.info("connected to %s:%d", cfg.tv.host, cfg.tv.port)
            link.send(display.panel_setup(cfg.panel.invert, cfg.panel.bgr))
            prev, level = None, None
            while not stop:
                now = time.time()
                w = weather.get()
                cur = display.to_rgb565(screen.frame(now, w))
                out = b""
                want = _backlight_level(cfg, now)
                if want != level:
                    out += display.backlight(want)
                    level = want
                link.send(out + display.frame_update(cur, prev))
                link.wait_ack()
                prev = cur
                screen.prepare_next_minute(now, w)
                time.sleep(max(0.0, step - (time.time() - now)))
        except (OSError, ConnectionError, TimeoutError) as exc:
            if not stop:
                log.warning("connection to the TV lost: %s; retrying", exc)
                time.sleep(RECONNECT_DELAY)
        finally:
            link.close()
    return 0


def preview(cfg: Config, out: Path, scale: int) -> int:
    img = Screen(cfg).frame(weather=WeatherCache(cfg).get())
    img.resize((240 * scale, 240 * scale), resample=0).save(out)
    print(out)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="smalltv-live", description="Live screen for the SmallTV Live firmware.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", type=Path, help="config file (default ~/.config/smalltv-live/config.toml)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="stream to the TV until stopped")
    p = sub.add_parser("preview", help="render one frame to an image file")
    p.add_argument("output", type=Path, nargs="?", default=Path("preview.png"))
    p.add_argument("--scale", type=int, default=3, choices=range(1, 9), metavar="1-8")
    s = sub.add_parser("statusline", help="Claude Code status line command: cache usage limits from stdin")
    s.add_argument("--then", metavar="COMMAND", help="status line command to run afterwards (no shell)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        cfg = load(args.config)
    except ConfigError as exc:
        if args.command == "statusline":      # never break the status line over a config problem
            return statusline(Config().usage.cache_path, args.then)
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    if args.command == "statusline":
        return statusline(cfg.usage.cache_path, args.then)
    if args.command == "preview":
        return preview(cfg, args.output, args.scale)
    return run(cfg)


if __name__ == "__main__":
    sys.exit(main())
