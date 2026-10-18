"""Pipeline-wide constants and tunable parameters."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta, timezone
from pathlib import Path

# Indonesia bounding box: west, south, east, north. Includes neighbouring
# countries; points outside Indonesian boundaries are dropped at tagging.
BBOX = (94.5, -11.5, 141.5, 6.5)

# Day boundaries for snapshots and naming use WIB (UTC+7).
LOCAL_TZ = timezone(timedelta(hours=7))

ROOT = Path(os.environ.get("HAZE_ROOT", Path(__file__).resolve().parents[3]))
DATA_DIR = Path(os.environ.get("HAZE_DATA_DIR", ROOT / "data"))
CACHE_DIR = DATA_DIR / "cache"
DB_PATH = Path(os.environ.get("HAZE_DB", DATA_DIR / "haze.duckdb"))
PUBLIC_DIR = Path(os.environ.get("HAZE_PUBLIC_DIR", ROOT / "public"))
STATIC_DIR = ROOT / "pipeline" / "static"
# Season seeds (hotspots_<year>.parquet) for a cold start without a FIRMS MAP_KEY.
SEED_DIR = ROOT / "pipeline" / "seed"

EARTH_RADIUS_KM = 6371.0088


# Detection confidence levels, lowest first (VIIRS l/n/h; MODIS < 30 / < 80 / >= 80).
CONFIDENCE_RANK = {"low": 0, "nominal": 1, "high": 2}


@dataclass(frozen=True)
class ClusterParams:
    # Two hotspots belong to the same event if they are within radius_km of
    # each other AND within gap_hours of each other (single linkage).
    radius_km: float = 1.5
    gap_hours: float = 48.0
    # VIIRS 'l' / MODIS < 30 confidence detections are kept in `hotspots` but
    # do not seed or join events.
    min_confidence: str = "nominal"


@dataclass(frozen=True)
class StatusParams:
    active_hours: float = 24.0
    cooling_hours: float = 72.0


@dataclass(frozen=True)
class MaskParams:
    # A hotspot within this distance of a static source is masked.
    match_km: float = 0.75
    # Persistence: FIRMS-flagged cells must be flagged in at least min_months
    # calendar months; the recurrence rule needs min_days distinct days over
    # min_months months of one year. Fire season is ~3-4 months, so 6 keeps
    # seasonal vegetation fires out of the mask.
    min_days: int = 30
    min_months: int = 6
    cell_deg: float = 0.0035


CLUSTER = ClusterParams()
STATUS = StatusParams()
MASK = MaskParams()

# Fire pixels are counted as unique cells of one fixed ~375 m grid (the VIIRS
# I-band pixel at nadir): area estimates, event footprints, spread, progression
# and fire history all share it.
CELL_DEG = 0.0034
# Nominal VIIRS I-band pixel at nadir (375 m x 375 m) in hectares: 14.0625 ha per cell.
CELL_HA = 0.375 * 0.375 * 100
