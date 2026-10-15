"""Configuration, read from a TOML file.

Search order: the --config argument, $SMALLTV_LIVE_CONFIG, then
$XDG_CONFIG_HOME/smalltv-live/config.toml (default ~/.config/smalltv-live/config.toml).
Every key is optional; see config.example.toml for the full list.
"""
from __future__ import annotations

import ipaddress
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


_HOSTNAME = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*\.?$")


def _valid_host(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return bool(_HOSTNAME.match(host))


class ConfigError(ValueError):
    """Raised for a config file that exists but can't be used."""


@dataclass(frozen=True)
class TvConfig:
    host: str = "smalltv.local"
    port: int = 7777


@dataclass(frozen=True)
class LocationConfig:
    latitude: float | None = None
    longitude: float | None = None
    timezone: str = "UTC"

    @property
    def has_coordinates(self) -> bool:
        return self.latitude is not None and self.longitude is not None


@dataclass(frozen=True)
class DisplayConfig:
    language: str = "en"
    fps: int = 10
    brightness_day: int = 170
    brightness_night: int = 35
    night_start: int = 22
    night_end: int = 7


@dataclass(frozen=True)
class PanelConfig:
    invert: bool = True
    bgr: bool = False


@dataclass(frozen=True)
class UsageConfig:
    cache: str = "~/.claude/rate_limits.json"
    stale_after_minutes: int = 20

    @property
    def cache_path(self) -> Path:
        return Path(self.cache).expanduser()


@dataclass(frozen=True)
class Config:
    tv: TvConfig = field(default_factory=TvConfig)
    location: LocationConfig = field(default_factory=LocationConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    panel: PanelConfig = field(default_factory=PanelConfig)
    usage: UsageConfig = field(default_factory=UsageConfig)

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.location.timezone)


def default_path() -> Path:
    if os.environ.get("SMALLTV_LIVE_CONFIG"):
        return Path(os.environ["SMALLTV_LIVE_CONFIG"]).expanduser()
    # The config location comes from the user's own environment; there is no privilege boundary here.
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "smalltv-live" / "config.toml"


def _section(data: dict, name: str, cls):
    raw = data.get(name, {})
    if not isinstance(raw, dict):
        raise ConfigError(f"[{name}] must be a table")
    known = set(cls.__dataclass_fields__)
    unknown = set(raw) - known
    if unknown:
        raise ConfigError(f"unknown key(s) in [{name}]: {', '.join(sorted(unknown))}")
    try:
        return cls(**raw)
    except TypeError as exc:
        raise ConfigError(f"[{name}]: {exc}") from exc


def _validate(cfg: Config) -> None:
    d, loc = cfg.display, cfg.location
    if d.language not in ("en", "ro"):
        raise ConfigError("display.language must be \"en\" or \"ro\"")
    if not 1 <= d.fps <= 30:
        raise ConfigError("display.fps must be between 1 and 30")
    for key in ("brightness_day", "brightness_night"):
        if not 0 <= getattr(d, key) <= 255:
            raise ConfigError(f"display.{key} must be between 0 and 255")
    for key in ("night_start", "night_end"):
        if not 0 <= getattr(d, key) <= 23:
            raise ConfigError(f"display.{key} must be an hour, 0 to 23")
    if loc.has_coordinates and not (-90 <= loc.latitude <= 90 and -180 <= loc.longitude <= 180):
        raise ConfigError("location.latitude/longitude out of range")
    if not isinstance(cfg.tv.host, str) or not _valid_host(cfg.tv.host):
        raise ConfigError("tv.host must be a hostname or an IP address")
    if not 1 <= cfg.tv.port <= 65535:
        raise ConfigError("tv.port must be a TCP port")
    try:
        ZoneInfo(loc.timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ConfigError(f"unknown timezone {loc.timezone!r}") from exc


def load(path: Path | None = None) -> Config:
    """Load the config; a missing file gives the defaults."""
    path = path or default_path()
    data: dict = {}
    if path.exists():
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"{path}: {exc}") from exc
    unknown = set(data) - {"tv", "location", "display", "panel", "usage"}
    if unknown:
        raise ConfigError(f"unknown section(s): {', '.join(sorted(unknown))}")
    cfg = Config(
        tv=_section(data, "tv", TvConfig),
        location=_section(data, "location", LocationConfig),
        display=_section(data, "display", DisplayConfig),
        panel=_section(data, "panel", PanelConfig),
        usage=_section(data, "usage", UsageConfig),
    )
    _validate(cfg)
    return cfg
