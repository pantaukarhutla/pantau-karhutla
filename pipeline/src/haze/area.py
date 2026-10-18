"""Season burned-area estimate from VIIRS fire pixels, as a range between two
independent calibrations (docs/research/audit-burned-area.md).

Fire pixels are not burned area: small fires fill only part of a 375 m
pixel, positions scatter between overpasses, and every extra satellite adds
cells. So:
1. per VIIRS satellite, count the season's unique 0.0034 deg (~375 m) cells
   with a public hotspot (once per season, not per event);
2. average over the satellites flying that season (single-satellite
   equivalent, so NOAA-21's arrival does not inflate 2026);
3. x 14.06 ha, then x k.

k is fitted two ways, and both are shown:
- K_OFFICIAL = 0.49: KLHK/SiPongi official totals for 2019 and 2023 (it
  reproduces each year from the other within ~4%);
- K_INDEPENDENT = 0.90: the Sentinel-2 burned-area map of Gaveau et al. 2021
  (ESSD 13, 5353) for 2019, > 3.11 M ha, almost twice the official figure.
The official SiPongi figure is fetched and shown next to ours, not used as
truth.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import duckdb
import httpx
import pandas as pd

from haze import http
from haze.config import CELL_HA
from haze.io import utc_minute
from haze.sql import PUBLIC, SEASON, cell_ix

log = logging.getLogger(__name__)

K_OFFICIAL = 0.49  # official / single-satellite pixel area, 2019 + 2023 (range 0.40-0.57)
K_INDEPENDENT = 0.90  # Gaveau et al. 2021 Sentinel-2, 2019: 3.11 M ha / 3.44 M ha pixel area
MIN_SATELLITE_SHARE = 0.05  # a satellite counts as "flying" with >= 5% of the season's VIIRS detections
SIPONGI_AREA_URL = "https://opsroom.sipongidata.my.id/api/list/luas-kebakaran/provinsi"


def pixel_area(con: duckdb.DuckDBPyConnection, season: int) -> pd.DataFrame:
    """Single-satellite-equivalent fire-pixel area (ha) per province, and the satellites used."""
    df = con.execute(
        f"""
        WITH c AS (
            SELECT DISTINCT satellite, provinsi, {cell_ix()}
            FROM hotspots
            WHERE sensor = 'VIIRS' AND {PUBLIC} AND provinsi IS NOT NULL AND {SEASON} = ?
        )
        SELECT satellite, provinsi, count(*) AS cells FROM c GROUP BY ALL
        """,
        [season],
    ).df()
    if df.empty:
        return pd.DataFrame(columns=["provinsi", "pixel_ha"])
    share = df.groupby("satellite").cells.sum() / df.cells.sum()
    sats = share[share >= MIN_SATELLITE_SHARE].index.tolist()
    per = df[df.satellite.isin(sats)].pivot_table(index="provinsi", columns="satellite", values="cells", fill_value=0)
    out = pd.DataFrame({"provinsi": per.index, "pixel_ha": per.mean(axis=1).to_numpy() * CELL_HA})
    out.attrs["satellites"] = sats
    return out


def _id_number(s: str) -> float:
    """'38.310,89' -> 38310.89 (Indonesian number format)."""
    return float(str(s).replace(".", "").replace(",", "."))


def official_area(season: int, client: httpx.Client | None = None) -> dict[str, float] | None:
    """SiPongi official burned area (ha) per province for `season`, or None."""
    own = client is None
    client = client or http.client(timeout=30.0)
    try:
        r = client.get(SIPONGI_AREA_URL, params={"tahunAwal": season, "tahunAkhir": season})
        r.raise_for_status()
        rows = r.json()
        rows = rows.get("data", rows) if isinstance(rows, dict) else rows
        out = {}
        for p in rows:
            for d in p.get("data_luas", []):
                if str(d.get("tahun")) == str(season) and d.get("luas") not in (None, ""):
                    out[p["nama_provinsi"]] = _id_number(d["luas"])
        return out or None
    except Exception as exc:  # noqa: BLE001
        log.warning("SiPongi official area unavailable: %s", exc)
        return None
    finally:
        if own:
            client.close()


def estimate(con: duckdb.DuckDBPyConnection, season: int, official: dict[str, float] | None = None) -> dict:
    px = pixel_area(con, season)
    rows = []
    norm = {k.lower(): v for k, v in (official or {}).items()}
    for r in px.sort_values("pixel_ha", ascending=False).itertuples():
        rows.append(
            {
                "provinsi": r.provinsi,
                "low_ha": round(r.pixel_ha * K_OFFICIAL, -2),
                "high_ha": round(r.pixel_ha * K_INDEPENDENT, -2),
                "official_ha": norm.get(str(r.provinsi).lower()),
            }
        )
    total = float(px.pixel_ha.sum()) if len(px) else 0.0
    return {
        "season": season,
        "computed_at": utc_minute(datetime.now(UTC)),
        "satellites": px.attrs.get("satellites", []),
        "national": {
            "low_ha": round(total * K_OFFICIAL, -3),
            "high_ha": round(total * K_INDEPENDENT, -3),
            "official_ha": round(sum(official.values())) if official else None,
        },
        "by_provinsi": rows,
        "k": {"official": K_OFFICIAL, "independent": K_INDEPENDENT},
        # Sample-based checks from satellite imagery (research/burned_area/).
        "validation": _validation(season),
        "method": "unique 375 m VIIRS fire pixels (single-satellite average) x 14.06 ha x k; "
        "k fitted to KLHK 2019/2023 (low) and to Gaveau et al. 2021 Sentinel-2 2019 (high)",
    }


def _validation(season: int) -> list[dict]:
    from haze.config import STATIC_DIR

    path = STATIC_DIR / "independent_area.json"
    if not path.exists():
        return []
    import json

    return [e for e in json.loads(path.read_text())["estimates"] if e["season"] == season]
