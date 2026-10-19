"""Write the static files the frontend reads. The web app never queries the DB.

public/
  events/live.geojson          events active, cooling or seen in the last 7 days
  events/live.json             the same, columnar and trimmed: burning now (active, cooling)
  events/live_out.json         ... and out within the last 7 days (loaded after first paint)
  events/{season}.json         every event of the season, columnar (lists, export)
  events/{season}/{id}.json    event page (events with >1 detection): daily curves,
                               per-day footprints and the final footprint
  days/{date}.geojson          that day's footprint of every event seen that WIB day
  dashboard.json               national stats, top growth, freshness, baselines
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import shapely

from haze.config import CELL_HA, LOCAL_TZ, PUBLIC_DIR, STATIC_DIR
from haze.geo import geojson
from haze.io import utc, utc_minute, write_json
from haze.sql import NOT_STATIC, PUBLIC, SEASON

log = logging.getLogger(__name__)

EVENT_PROPS = [
    "id",
    "name",
    "status",
    "first_seen",
    "last_seen",
    "hotspot_count",
    "peak_frp",
    "total_frp",
    "est_area_ha",
    "on_peat",
    "peat_share",
    "provinsi",
    "kabupaten",
    "nearest_town",
    "nearest_town_km",
    "near_static",
    "tier",
]
COORD_DECIMALS = 5
BASELINES_CSV = STATIC_DIR / "season_baselines.csv"
BASELINE_SEASONS = (2015, 2019, 2023)
LIVE_DAYS = 7
LIVE_DECIMALS = {"centroid_lon": 4, "centroid_lat": 4, "total_frp": 0, "peak_frp": 1, "est_area_ha": 0}
LIVE_COLUMNS = [
    "id",
    "centroid_lon",
    "centroid_lat",
    "status",
    "name",
    "provinsi",
    "kabupaten",
    "first_seen",
    "last_seen",
    "hotspot_count",
    "total_frp",
    "peak_frp",
    "est_area_ha",
    "on_peat",
    "near_static",
    "tier",
]


def _clean(v):
    if v is None or v is pd.NA or v is pd.NaT:
        return None
    if isinstance(v, float) and np.isnan(v):
        return None
    if isinstance(v, (pd.Timestamp, datetime)):
        return utc_minute(v)
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, np.generic):
        return v.item()
    if isinstance(v, float):
        return round(v, 2)
    return v


def _props(row, cols: list[str]) -> dict:
    return {c: _clean(row[c]) for c in cols}


def _geojson_geom(wkb) -> dict | None:
    if wkb is None:
        return None
    return geojson(shapely.from_wkb(bytes(wkb)), COORD_DECIMALS)


def _table_rows(df: pd.DataFrame) -> list[list]:
    """JSON-ready rows, vectorised: timestamps as UTC minutes, floats to 2 dp, NaN -> None."""
    out = pd.DataFrame(index=df.index)
    for c in df.columns:
        col = df[c]
        if pd.api.types.is_datetime64_any_dtype(col):
            col = pd.to_datetime(col, utc=True).dt.strftime("%Y-%m-%dT%H:%MZ")
        elif pd.api.types.is_float_dtype(col):
            col = col.round(COORD_DECIMALS if c.startswith(("centroid", "bbox")) else 2)
        out[c] = col.astype(object).where(col.notna(), None)
    return out.to_numpy().tolist()


def season_events(con: duckdb.DuckDBPyConnection, season: int) -> pd.DataFrame:
    return con.execute("SELECT * FROM fire_events WHERE season = ? ORDER BY first_seen", [season]).df()


def _point_feature(r: pd.Series) -> dict:
    return {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [round(r.centroid_lon, COORD_DECIMALS), round(r.centroid_lat, COORD_DECIMALS)],
        },
        "properties": _props(r, EVENT_PROPS),
    }


def _local_date(ts: pd.Series) -> pd.Series:
    return pd.to_datetime(ts, utc=True).dt.tz_convert(LOCAL_TZ).dt.strftime("%Y-%m-%d")


@dataclass
class EventExtras:
    """Per-event additions to event pages from enrichment steps, by event id."""

    land: dict[str, dict] = field(default_factory=dict)  # forest permits (haze.land)
    history: dict[str, dict] = field(default_factory=dict)  # past fire years (haze.fire_history)


# Bump to make every out dir get one full publish (pages hold data that a
# migration changed). 2: provinces regrouped into the 38 of 2022.
# 3: fires named after their desa.
FULL_PUBLISH_VERSION = 3


def publish_season(
    con: duckdb.DuckDBPyConnection,
    season: int,
    out: Path = PUBLIC_DIR,
    days: int | None = None,
    now: datetime | None = None,
    extras: EventExtras | None = None,
) -> int:
    """Write the event lists, event pages and day files for a season.

    `days` limits event pages and day files to events seen in the last N days
    (the frequent live run); the lists are always complete. Until one full
    publish of the season has completed into `out` (fresh or partial public/
    dir), every page is written regardless. Single-detection events get no
    page: the list row holds everything about them.
    """
    ev = season_events(con, season)
    if ev.empty:
        return 0
    complete = out / "events" / f".{season}-complete-{FULL_PUBLISH_VERSION}"
    if not complete.exists():
        days = None
    now = pd.Timestamp(now or pd.Timestamp.now(tz="UTC"))
    last_local = _local_date(ev.last_seen)

    # Map layer: what is burning or burned in the last week.
    week_ago = (now.tz_convert(LOCAL_TZ) - timedelta(days=LIVE_DAYS)).strftime("%Y-%m-%d")
    live = ev[(ev.status != "out") | (last_local >= week_ago)]
    # Compact columnar copy for the web map (~3x smaller than the GeoJSON).
    # The map needs ~10 m positions and whole MW / hectares, not 1 m and 2 dp.
    # Fires out this week are over half the rows but only grey dots on the
    # map, so they get their own file that the map loads after first paint.
    trimmed = live[LIVE_COLUMNS].round(LIVE_DECIMALS)
    burning = (live.status != "out").to_numpy()
    for name, rows in (("live", trimmed[burning]), ("live_out", trimmed[~burning])):
        write_json(out / "events" / f"{name}.json", {"columns": LIVE_COLUMNS, "rows": _table_rows(rows)})
    write_json(
        out / "events" / "live.geojson",
        {"type": "FeatureCollection", "features": [_point_feature(r) for _, r in live.iterrows()]},
    )

    # Whole season, columnar (dashboard, search, export): ~5x smaller than GeoJSON.
    cols = ["id", "centroid_lon", "centroid_lat", *[c for c in EVENT_PROPS if c != "id"]]
    write_json(
        out / "events" / f"{season}.json",
        {"columns": cols, "rows": _table_rows(ev[cols])},
    )

    cutoff = None if days is None else (now.tz_convert(LOCAL_TZ) - timedelta(days=days)).strftime("%Y-%m-%d")
    # Pages and day files only ever need events seen since the cutoff.
    snap = con.execute(
        """
        SELECT s.* EXCLUDE (date, perimeter_geom), CAST(s.date AS VARCHAR) AS date,
               e.hotspot_count AS event_hotspots
        FROM event_snapshots s JOIN fire_events e ON e.id = s.event_id
        WHERE e.season = ?
          AND (CAST(? AS DATE) IS NULL OR CAST(e.last_seen AT TIME ZONE 'Asia/Jakarta' AS DATE) >= CAST(? AS DATE))
        ORDER BY s.event_id, s.date
        """,
        [season, cutoff, cutoff],
    ).df()
    paged = ev[(ev.hotspot_count > 1) & ((last_local >= cutoff) if cutoff else True)]
    final = con.execute(
        """
        SELECT s.event_id, s.perimeter_geom FROM event_snapshots s JOIN fire_events e ON e.id = s.event_id
        WHERE e.season = ? AND e.hotspot_count > 1
        QUALIFY row_number() OVER (PARTITION BY s.event_id ORDER BY s.date DESC) = 1
        """,
        [season],
    ).df()
    final = dict(zip(final.event_id, final.perimeter_geom))

    extras = extras or EventExtras()
    written = 0
    rows = ev.set_index("id").to_dict("index")
    for eid, s in snap[snap.event_id.isin(set(paged.id))].groupby("event_id", sort=False):
        row = rows[eid]
        page = {
            "id": eid,
            **_props(row, [c for c in EVENT_PROPS if c != "id"]),
            "centroid": [round(row["centroid_lon"], COORD_DECIMALS), round(row["centroid_lat"], COORD_DECIMALS)],
            "bbox": [round(row[c], COORD_DECIMALS) for c in ("bbox_w", "bbox_s", "bbox_e", "bbox_n")],
            "footprint": _geojson_geom(final.get(eid)),
            "land": extras.land.get(eid),
            # Share of the event's cells that also burned in 2012-2025 (S-NPP).
            "history": extras.history.get(eid),
            "days": [
                {
                    "date": d.date,
                    "hotspots": int(d.hotspot_count),
                    "frp_sum": _clean(float(d.frp_sum)),
                    "peak_frp": _clean(float(d.peak_frp)),
                    "area_ha": _clean(float(d.cum_area_ha)),
                    "growth_ha": _clean(float(d.growth_ha)),
                    # Only that day's new detections; stack days for the growth animation.
                    "footprint": _geojson_geom(d.day_geom),
                }
                for d in s.itertuples(index=False)
            ],
        }
        written += write_json(out / "events" / str(season) / f"{eid}.json", page)

    day_snap = snap if cutoff is None else snap[snap.date >= cutoff]
    status = dict(zip(ev.id, ev.status))
    for day, s in day_snap.groupby("date"):
        write_json(
            out / "days" / f"{day}.geojson",
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": _geojson_geom(d.day_geom),
                        "properties": {
                            "id": d.event_id,
                            "status": status.get(d.event_id),
                            "hotspots": int(d.hotspot_count),
                            "frp_sum": _clean(float(d.frp_sum)),
                            "area_ha": _clean(float(d.cum_area_ha)),
                        },
                    }
                    for d in s.itertuples(index=False)
                ],
            },
        )
    if days is None:
        complete.touch()
    log.info("published season %s: %d events (%d live), %d event pages changed", season, len(ev), len(live), written)
    return written


def recent_hotspots(
    con: duckdb.DuckDBPyConnection, now: datetime, out: Path = PUBLIC_DIR, hours: int = 48, replay_hours: int = 96
) -> int:
    """Individual detections, columnar [lon, lat, frp_mw, age_h]: the last `hours`
    for the map's fire glow and flames (hotspots_recent.json, loaded at start), and
    the last `replay_hours` for the time slider's past (hotspots_replay.json, loaded
    only when the slider goes back; 96 h keeps a full day behind its -72 h end).
    `generated_at` is the time the ages count from."""
    df = con.execute(
        f"""
        SELECT round(lon, 4) AS lon, round(lat, 4) AS lat, round(coalesce(frp_mw, 1), 1) AS frp,
               round(date_diff('minute', acq_time, ?::TIMESTAMPTZ) / 60.0, 1) AS age_h
        FROM hotspots
        WHERE acq_time > ?::TIMESTAMPTZ - INTERVAL (?) HOUR AND acq_time <= ?::TIMESTAMPTZ
          AND {PUBLIC}
        ORDER BY acq_time
        """,
        [now, now, max(hours, replay_hours), now],
    ).df()
    stamp = now.strftime("%Y-%m-%dT%H:%MZ")
    recent = df[df.age_h < hours]
    for name, part in (("hotspots_recent.json", recent), ("hotspots_replay.json", df)):
        write_json(out / "events" / name, {"generated_at": stamp, "columns": list(part.columns), "rows": part.to_numpy().tolist()})
    return len(recent)


def daily_counts(con: duckdb.DuckDBPyConnection, season: int) -> pd.DataFrame:
    """Per WIB day: hotspots that belong to events, events first seen, and
    S-NPP-only hotspots. S-NPP is the one VIIRS satellite flying in every
    season since 2012 (NOAA-20 from 2018, NOAA-21 from 2023), so only its
    counts compare fairly across seasons."""
    return con.execute(
        f"""
        WITH h AS (
            SELECT CAST(acq_time AT TIME ZONE 'Asia/Jakarta' AS DATE) AS d, count(*) AS hotspots,
                   count(*) FILTER (WHERE satellite = 'SNPP') AS snpp
            FROM hotspots WHERE event_id IS NOT NULL AND {SEASON} = ?
            GROUP BY 1
        ), e AS (
            SELECT CAST(first_seen AT TIME ZONE 'Asia/Jakarta' AS DATE) AS d, count(*) AS new_events
            FROM fire_events WHERE season = ? GROUP BY 1
        )
        SELECT CAST(coalesce(h.d, e.d) AS VARCHAR) AS date, coalesce(hotspots, 0) AS hotspots,
               coalesce(new_events, 0) AS new_events, coalesce(snpp, 0) AS snpp
        FROM h FULL JOIN e ON h.d = e.d ORDER BY 1
        """,
        [season, season],
    ).df()


def write_baselines(con: duckdb.DuckDBPyConnection, seasons=BASELINE_SEASONS, path: Path = BASELINES_CSV) -> None:
    """Daily curves of past bad seasons for the season-vs-baseline chart."""
    frames = [daily_counts(con, s).assign(season=s) for s in seasons]
    pd.concat(frames)[["season", "date", "hotspots", "new_events", "snpp"]].to_csv(path, index=False)


# SiPongi (Kemenhut) counts all confidence levels from these satellites only.
SIPONGI_SATELLITES = ("TERRA", "AQUA", "SNPP", "NOAA20")


def dashboard(con: duckdb.DuckDBPyConnection, season: int, now: datetime, out: Path = PUBLIC_DIR) -> dict:
    now_ts = pd.Timestamp(now)
    ev = season_events(con, season)
    latest = con.execute(f"SELECT max(acq_time) FROM hotspots WHERE {SEASON} = ?", [season]).fetchone()[0]
    latest_by = dict(
        con.execute(
            f"""SELECT sensor, max(acq_time) FROM hotspots
            WHERE {SEASON} = ? GROUP BY 1""",
            [season],
        ).fetchall()
    )
    h24 = con.execute(
        f"""SELECT count(*) FILTER (WHERE {PUBLIC}),
                   count(*) FILTER (WHERE in_indonesia AND {NOT_STATIC} AND satellite IN {SIPONGI_SATELLITES}),
                   count(*) FILTER (WHERE {PUBLIC} AND confidence = 'high')
            FROM hotspots WHERE acq_time >= ? AND acq_time <= ?""",
        [now_ts - pd.Timedelta(hours=24), now_ts],
    ).fetchone()
    live = ev[ev.status != "out"]
    # Headline counts use events with strong evidence (not one daytime pixel).
    multi = ev.tier == "strong"
    first = pd.to_datetime(ev.first_seen, utc=True) if len(ev) else pd.Series(dtype="datetime64[ns, UTC]")
    new24 = first >= now_ts - pd.Timedelta(hours=24)

    latest_growth = con.execute(
        """
        SELECT s.event_id, s.growth_ha, s.date FROM event_snapshots s
        JOIN fire_events e ON e.id = s.event_id
        WHERE e.season = ? AND e.status != 'out'
        QUALIFY row_number() OVER (PARTITION BY s.event_id ORDER BY s.date DESC) = 1
        """,
        [season],
    ).df()
    top = latest_growth.merge(ev, left_on="event_id", right_on="id").nlargest(10, "growth_ha")

    # Rank provinces by hotspots in the last 7 days, not event counts
    # (event counts reward fragmentation).
    h7 = con.execute(
        f"""SELECT provinsi, count(*) AS hotspots_7d FROM hotspots
            WHERE {PUBLIC} AND acq_time >= ? AND provinsi IS NOT NULL GROUP BY 1""",
        [now_ts - pd.Timedelta(days=7)],
    ).df()
    by_prov = (
        live[multi.loc[live.index]]
        .groupby("provinsi")
        .agg(events=("id", "size"))
        .reset_index()
        .merge(h7, on="provinsi", how="outer")
        .fillna(0)
        .sort_values("hotspots_7d", ascending=False)
    )
    daily = daily_counts(con, season)
    baselines = {}
    if BASELINES_CSV.exists():
        b = pd.read_csv(BASELINES_CSV)
        baselines = {
            int(y): [[d[5:], int(n)] for d, n in zip(g.date, g.snpp)] for y, g in b.groupby("season") if y != season
        }

    obj = {
        "generated_at": _clean(now),
        "latest_detection": _clean(latest),
        "latest_viirs": _clean(latest_by.get("VIIRS")),
        "latest_modis": _clean(latest_by.get("MODIS")),
        "lag_hours": None if latest is None else round((utc(now) - utc(latest)).total_seconds() / 3600, 1),
        "season": season,
        "counts": {
            "active": int((ev.status == "active").sum()),
            "active_multi": int(((ev.status == "active") & multi).sum()),
            "cooling": int((ev.status == "cooling").sum()),
            "cooling_multi": int(((ev.status == "cooling") & multi).sum()),
            "new_24h": int(new24.sum()),
            "new_24h_multi": int((new24 & multi).sum()),
            "season_events": len(ev),
            "season_hotspots": int(ev.hotspot_count.sum()) if len(ev) else 0,
        },
        # Last 24 h: our public count, a SiPongi-comparable count (same
        # satellites, all confidence) and the high-confidence subset.
        "hotspots_24h": {"public": int(h24[0]), "sipongi_like": int(h24[1]), "high": int(h24[2])},
        "top_growth": [
            {
                **_props(r, ["id", "name", "status", "provinsi"]),
                "growth_ha": _clean(r.growth_ha),
                "growth_pixels": int(round((r.growth_ha or 0) / CELL_HA)),
                "date": _clean(r.date),
            }
            for _, r in top.iterrows()
        ],
        "by_provinsi": [
            {"provinsi": r.provinsi, "events": int(r.events), "hotspots_7d": int(r.hotspots_7d)}
            for r in by_prov.itertuples()
        ],
        # [date, hotspots, new events, S-NPP hotspots]
        "daily": [
            [d, int(h), int(e), int(n)] for d, h, e, n in zip(daily.date, daily.hotspots, daily.new_events, daily.snpp)
        ],
        # Past seasons as [MM-DD, S-NPP hotspots]: compare with column 4 of `daily`.
        "baselines": baselines,
    }
    write_json(out / "dashboard.json", obj)
    return obj


# Map context layers: simplified shapes, tolerance in degrees (~1 km / 2 km).
BOUNDARY_LAYERS = {"provinsi": 0.02, "kabupaten": 0.01, "peat": 0.005}


def boundaries(con: duckdb.DuckDBPyConnection, out: Path = PUBLIC_DIR) -> dict[str, int]:
    """boundaries/{provinsi,kabupaten,peat}.geojson for the map's GIS layers."""
    written = {}
    labels = []
    target = out / "boundaries"
    target.mkdir(parents=True, exist_ok=True)
    parents = dict(con.execute("SELECT id, name FROM regions WHERE level = 'provinsi'").fetchall())
    for level, tol in BOUNDARY_LAYERS.items():
        rows = con.execute("SELECT id, name, parent, geom FROM regions WHERE level = ?", [level]).fetchall()
        features = []
        for rid, name, parent, wkb in rows:
            geom = shapely.simplify(shapely.from_wkb(wkb), tol, preserve_topology=True)
            geom = shapely.transform(geom, lambda c: np.round(c, 3))
            if geom.is_empty:
                continue
            props = {"id": rid, "name": name}
            if parent:
                props["provinsi"] = parents.get(parent, parent)
            features.append({"type": "Feature", "geometry": shapely.geometry.mapping(geom), "properties": props})
            if level != "peat":
                # One label per region, on its largest part (islands would
                # otherwise repeat the name on every polygon).
                parts = list(getattr(geom, "geoms", [geom]))
                pt = shapely.point_on_surface(max(parts, key=lambda g: g.area))
                labels.append(
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [round(pt.x, 3), round(pt.y, 3)]},
                        "properties": {"name": name, "level": level},
                    }
                )
        write_json(target / f"{level}.geojson", {"type": "FeatureCollection", "features": features})
        written[level] = len(features)
    write_json(target / "labels.geojson", {"type": "FeatureCollection", "features": labels})
    log.info("boundaries: %s", written)
    return written


# ---------------------------------------------------------------- data tables

TABLE_MIN_HOTSPOTS = 5


def tables(con: duckdb.DuckDBPyConnection, season: int, now: datetime, out: Path = PUBLIC_DIR) -> dict[str, int]:
    """Data-view tables for people who want numbers, not maps.

    - tables/fires-{season}.json: every fire of the season with at least
      TABLE_MIN_HOTSPOTS detections (columnar, for filtering and export).
    - tables/regions.json: per provinsi and kabupaten: active fires now,
      detections in the last 24 h / 7 days / season, estimated burned area,
      peat share and a 30-day daily detections series.
    """
    now = pd.Timestamp(now)
    target = out / "tables"
    target.mkdir(parents=True, exist_ok=True)
    cols = [
        "id", "name", "status", "provinsi", "kabupaten", "first_seen", "last_seen", "hotspot_count",
        "peak_frp", "on_peat", "near_static", "centroid_lon", "centroid_lat",
    ]  # fmt: skip
    fires = con.execute(
        f"""
        SELECT {", ".join(cols)} FROM fire_events
        WHERE season = ? AND hotspot_count >= ? AND provinsi IS NOT NULL
        ORDER BY last_seen DESC
        """,
        [season, TABLE_MIN_HOTSPOTS],
    ).df()
    rows = []
    for r in fires.itertuples(index=False):
        rows.append(
            [
                r.id, r.name, r.status, r.provinsi, r.kabupaten,
                utc_minute(r.first_seen),
                utc_minute(r.last_seen),
                int(r.hotspot_count),
                _clean(round(float(r.peak_frp or 0), 1)),
                None if pd.isna(r.on_peat) else bool(r.on_peat), bool(r.near_static),
                round(float(r.centroid_lon), 4), round(float(r.centroid_lat), 4),
            ]
        )  # fmt: skip
    cols = [c if c not in ("centroid_lon", "centroid_lat") else c.split("_")[1] for c in cols]
    write_json(
        target / f"fires-{season}.json",
        {"season": season, "min_hotspots": TABLE_MIN_HOTSPOTS, "columns": cols, "rows": rows},
    )

    day0 = (now.tz_convert(LOCAL_TZ) - timedelta(days=29)).strftime("%Y-%m-%d")
    det = con.execute(
        f"""
        SELECT provinsi, kabupaten,
               count(*) AS season_hotspots,
               count(*) FILTER (WHERE acq_time >= ?) AS h24,
               count(*) FILTER (WHERE acq_time >= ?) AS d7,
               avg(CASE WHEN on_peat THEN 1.0 ELSE 0.0 END) AS peat_share
        FROM hotspots
        WHERE {PUBLIC} AND provinsi IS NOT NULL AND {SEASON} = ?
        GROUP BY ALL
        """,
        [now - pd.Timedelta(hours=24), now - pd.Timedelta(days=7), season],
    ).df()
    daily = con.execute(
        f"""
        SELECT provinsi, kabupaten, strftime(acq_time AT TIME ZONE 'Asia/Jakarta', '%Y-%m-%d') AS day, count(*) AS n
        FROM hotspots
        WHERE {PUBLIC} AND provinsi IS NOT NULL AND acq_time >= ?
        GROUP BY ALL
        """,
        [now - pd.Timedelta(days=31)],
    ).df()
    ev = con.execute(
        """
        SELECT provinsi, kabupaten,
               count(*) FILTER (WHERE status = 'active' AND tier = 'strong') AS active,
               count(*) FILTER (WHERE tier = 'strong') AS season_fires
        FROM fire_events WHERE season = ? AND provinsi IS NOT NULL
        GROUP BY ALL
        """,
        [season],
    ).df()
    days = [(pd.Timestamp(day0) + pd.Timedelta(days=i)).strftime("%Y-%m-%d") for i in range(30)]

    def summarise(keys: list[str]) -> list[dict]:
        d = det.groupby(keys)[["season_hotspots", "h24", "d7"]].sum()
        # Hotspot-weighted peat share.
        w = det.assign(pw=det.peat_share * det.season_hotspots).groupby(keys)["pw"].sum()
        d["peat_share"] = (w / d.season_hotspots).fillna(0)
        e = ev.groupby(keys)[["active", "season_fires"]].sum()
        series = daily.groupby(keys + ["day"])["n"].sum()
        merged = d.join(e, how="outer").fillna(0)
        result = []
        for key, r in merged.iterrows():
            if r.season_hotspots == 0 and r.active == 0:
                continue  # event-only rows from boundary mismatches carry no detections
            key = key if isinstance(key, tuple) else (key,)
            s = series.get(key, pd.Series(dtype=int))
            per_day = s.droplevel(list(range(len(keys)))) if isinstance(s.index, pd.MultiIndex) else s
            result.append(
                {
                    **dict(zip(keys, key, strict=True)),
                    "active": int(r.active),
                    "h24": int(r.h24),
                    "d7": int(r.d7),
                    "season_hotspots": int(r.season_hotspots),
                    "season_fires": int(r.season_fires),
                    "peat_share": round(float(r.peat_share), 2),
                    "daily": [int(per_day.get(day, 0)) for day in days],
                }
            )
        result.sort(key=lambda x: (-x["d7"], -x["season_hotspots"]))
        return result

    regions = {
        "generated_at": utc_minute(now),
        "season": season,
        "days": days,
        "provinsi": summarise(["provinsi"]),
        "kabupaten": summarise(["provinsi", "kabupaten"]),
    }
    write_json(target / "regions.json", regions)
    log.info(
        "tables: %d fires, %d provinsi, %d kabupaten", len(rows), len(regions["provinsi"]), len(regions["kabupaten"])
    )
    return {"fires": len(rows), "kabupaten": len(regions["kabupaten"])}
