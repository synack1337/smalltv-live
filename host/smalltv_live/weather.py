"""Current weather from Open-Meteo (no API key)."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

API = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 10
MAX_BYTES = 256 * 1024


@dataclass(frozen=True)
class Weather:
    temperature: int
    code: int            # WMO weather interpretation code
    is_day: bool
    high: int
    low: int
    rain_chance: int     # percent, current hour


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "smalltv-live"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:   # https only, fixed host
        return json.loads(resp.read(MAX_BYTES))


def fetch(latitude: float, longitude: float, tz: ZoneInfo) -> Weather:
    query = urllib.parse.urlencode({
        "latitude": f"{latitude:.4f}",
        "longitude": f"{longitude:.4f}",
        "timezone": str(tz),
        "forecast_days": 1,
        "current": "temperature_2m,weather_code,is_day",
        "hourly": "precipitation_probability",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
    })
    return parse(_get(f"{API}?{query}"), datetime.now(tz).hour)


def parse(data: dict, hour: int) -> Weather:
    current, daily = data["current"], data["daily"]
    hourly = data.get("hourly", {}).get("precipitation_probability") or []
    rain = hourly[hour] if 0 <= hour < len(hourly) and hourly[hour] is not None else None
    if rain is None:
        rain = (daily.get("precipitation_probability_max") or [0])[0] or 0
    return Weather(
        temperature=round(current["temperature_2m"]),
        code=int(current["weather_code"]),
        is_day=bool(current["is_day"]),
        high=round(daily["temperature_2m_max"][0]),
        low=round(daily["temperature_2m_min"][0]),
        rain_chance=int(rain),
    )
