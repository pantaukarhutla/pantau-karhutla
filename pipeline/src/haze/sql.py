"""SQL fragments shared by queries on `hotspots`, so a filter, a season or a
grid cell means the same thing in every module."""

from __future__ import annotations

from haze.config import CELL_DEG, CLUSTER, CONFIDENCE_RANK

# WIB calendar year of a detection: the fire season it belongs to.
SEASON = "year(acq_time AT TIME ZONE 'Asia/Jakarta')"

# Not a permanent heat source (flare, smelter, volcano). Untagged rows have
# is_static NULL, but so is their in_indonesia, which every filter also tests.
NOT_STATIC = "NOT coalesce(is_static, false)"


def confident(min_confidence: str = CLUSTER.min_confidence) -> str:
    """Detections at or above `min_confidence` (the clustering filter by default)."""
    levels = [c for c, r in CONFIDENCE_RANK.items() if r >= CONFIDENCE_RANK[min_confidence]]
    return "confidence IN ({})".format(", ".join(f"'{c}'" for c in levels))


# Public hotspot counts everywhere on the site: inside Indonesia, not a
# permanent heat source, confidence high enough to join fire events.
PUBLIC = f"in_indonesia AND {NOT_STATIC} AND {confident()}"


def cell_ix(lon: str = "lon", lat: str = "lat") -> str:
    """(ix, iy) of the CELL_DEG grid cell holding each row, as two select columns."""
    return f"CAST(floor({lon} / {CELL_DEG}) AS BIGINT) AS ix, CAST(floor({lat} / {CELL_DEG}) AS BIGINT) AS iy"
