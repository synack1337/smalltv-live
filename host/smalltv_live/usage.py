"""Claude plan usage limits.

Claude Code passes a JSON object to status line commands; it includes `rate_limits` with `five_hour`
and `seven_day` entries (`used_percentage`, `resets_at` as a Unix time). The `statusline` command of
this package stores that object in a small cache file, which the renderer reads. No credentials are
involved: only those percentages and reset times are stored.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Limit:
    used_percentage: float | None
    resets_at: float | None


@dataclass(frozen=True)
class Usage:
    five_hour: Limit
    seven_day: Limit
    age_seconds: float | None        # None: no data at all

    def is_stale(self, after_seconds: float) -> bool:
        return self.age_seconds is None or self.age_seconds > after_seconds


EMPTY = Usage(Limit(None, None), Limit(None, None), None)


def _number(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _limit(raw) -> Limit:
    if not isinstance(raw, dict):
        return Limit(None, None)
    pct = _number(raw.get("used_percentage"))
    if pct is not None:
        pct = min(max(pct, 0.0), 100.0)
    return Limit(pct, _number(raw.get("resets_at")))


def read(cache: Path, now: float | None = None) -> Usage:
    """Read the cache written by `write`; anything missing or malformed reads as no data."""
    try:
        data = json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return EMPTY
    if not isinstance(data, dict) or not isinstance(data.get("rate_limits"), dict):
        return EMPTY
    captured = _number(data.get("captured_at"))
    rl = data["rate_limits"]
    age = None if captured is None else max(0.0, (now or time.time()) - captured)
    return Usage(_limit(rl.get("five_hour")), _limit(rl.get("seven_day")), age)


def write(cache: Path, rate_limits: dict, now: float | None = None) -> None:
    """Atomically replace the cache (mode 0600)."""
    cache.parent.mkdir(parents=True, exist_ok=True)
    payload = {"captured_at": now or time.time(), "rate_limits": {
        key: {k: rate_limits[key].get(k) for k in ("used_percentage", "resets_at")}
        for key in ("five_hour", "seven_day") if isinstance(rate_limits.get(key), dict)
    }}
    fd, tmp = tempfile.mkstemp(dir=cache.parent, prefix=".rate_limits.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        os.chmod(tmp, 0o600)
        os.replace(tmp, cache)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def statusline(cache: Path, then: str | None) -> int:
    """Status line entry point: cache the limits from stdin, then run the next status line command.

    `then` is split like a shell command line but not run through a shell; wrap pipelines in a script.
    Its output is passed through unchanged, so an existing status line keeps working.
    """
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and isinstance(data.get("rate_limits"), dict):
            write(cache, data["rate_limits"])
    except (ValueError, OSError):
        pass                     # never break the status line over the cache
    if then:
        try:
            out = subprocess.run(shlex.split(then), input=raw, capture_output=True, text=True, timeout=10)
            sys.stdout.write(out.stdout)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    return 0
