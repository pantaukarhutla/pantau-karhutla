"""Writing published files and formatting the times in them."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from haze.config import LOCAL_TZ

# Timestamps in published files: UTC to the minute.
MINUTE = "%Y-%m-%dT%H:%MZ"


def write_text_if_changed(path: Path, text: str) -> bool:
    """Write `text` (UTF-8) unless the file already holds it, so CDN syncs
    upload only what changed. Creates parent directories. True if written."""
    data = text.encode()
    if path.exists() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return True


def write_json(path: Path, obj, default=None) -> bool:
    """Compact UTF-8 JSON (no ASCII escapes), written only when it changed.
    `default` is json.dumps' fallback for values it cannot encode."""
    return write_text_if_changed(path, json.dumps(obj, separators=(",", ":"), ensure_ascii=False, default=default))


def read_json(path: Path):
    """The parsed file, or None if it does not exist."""
    return json.loads(path.read_text()) if path.exists() else None


def utc(t) -> pd.Timestamp:
    """Timestamp in UTC; naive values (DuckDB fetchone) are taken as UTC."""
    t = pd.Timestamp(t)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def utc_minute(t) -> str:
    """'2026-09-10T12:00Z'."""
    return utc(t).strftime(MINUTE)


def wib_date(t) -> date:
    """Calendar day in WIB (UTC+7), the day boundary used for seasons and snapshots."""
    return utc(t).tz_convert(LOCAL_TZ).date()
