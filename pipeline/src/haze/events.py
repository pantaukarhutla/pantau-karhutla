"""Turn tagged hotspots into fire events, daily snapshots and stable ids."""

from __future__ import annotations

import logging
from datetime import datetime

import duckdb
import numpy as np
import pandas as pd
import shapely
from scipy.spatial import cKDTree

from haze import cluster, desa
from haze.config import CELL_DEG, CELL_HA, CLUSTER, LOCAL_TZ, STATUS, ClusterParams, StatusParams
from haze.geo import cell_keys, to_xyz
from haze.regions import Tagger, slug
from haze.sql import NOT_STATIC, SEASON, confident

log = logging.getLogger(__name__)

# Footprint buffer per detection, roughly half a pixel, in degrees.
BUFFER_DEG = {"VIIRS": 0.0017, "MODIS": 0.0045}
MODIS_CELL_DEG = 0.009
MODIS_PIXEL_HA = 100.0
PEAT_SHARE_MIN = 0.5


def eligible(
    con: duckdb.DuckDBPyConnection,
    season: int,
    params: ClusterParams = CLUSTER,
    events: list[str] | None = None,
) -> pd.DataFrame:
    """Hotspots that take part in clustering. With `events`, only members of
    those events plus hotspots not yet assigned to any event."""
    subset = ""
    if events is not None:
        con.register("subset_ids", pd.DataFrame({"id": pd.Series(events, dtype=str)}))
        subset = "AND (event_id IS NULL OR event_id IN (SELECT id FROM subset_ids))"
    df = con.execute(
        f"""
        SELECT id, sensor, satellite, daynight, acq_time, lat, lon, frp_mw, confidence, provinsi, kabupaten, on_peat
        FROM hotspots
        WHERE {SEASON} = ? AND in_indonesia AND {NOT_STATIC} AND {confident(params.min_confidence)}
          {subset}
        ORDER BY acq_time, id
        """,
        [season],
    ).df()
    if events is not None:
        con.unregister("subset_ids")
    return df


def affected_events(
    con: duckdb.DuckDBPyConnection, season: int, earliest_new: datetime, params: ClusterParams = CLUSTER
) -> list[str]:
    """Events that new hotspots (none older than `earliest_new`) could touch.

    A link needs two hotspots within gap_hours, so a new hotspot can only join
    events last seen at or after earliest_new - gap_hours. Re-clustering those
    events' hotspots plus the unassigned ones reproduces a full rebuild exactly:
    every other pair of hotspots was already evaluated and is unchanged.
    """
    cutoff = pd.Timestamp(earliest_new) - pd.Timedelta(hours=params.gap_hours)
    rows = con.execute("SELECT id FROM fire_events WHERE season = ? AND last_seen >= ?", [season, cutoff]).fetchall()
    return [r[0] for r in rows]


def status_for(last_seen: pd.Series, now: datetime, params: StatusParams = STATUS) -> np.ndarray:
    age_h = (pd.Timestamp(now) - pd.to_datetime(last_seen, utc=True)).dt.total_seconds().to_numpy() / 3600
    return np.select([age_h < params.active_hours, age_h < params.cooling_hours], ["active", "cooling"], "out")


def pixel_cells(sensor: np.ndarray, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Grid cell per detection: ~375 m for VIIRS, ~1 km for MODIS (negative keys)."""
    v = sensor == "VIIRS"
    return np.where(v, cell_keys(lat, lon, CELL_DEG), -cell_keys(lat, lon, MODIS_CELL_DEG) - 1)


def area_by(group: pd.Series, sensor: pd.Series, cells: np.ndarray) -> pd.Series:
    """Estimated burning area per group: unique VIIRS pixels x nominal pixel
    area, or unique MODIS pixels for groups with no VIIRS detection. This is
    the detected footprint, not burned area."""
    df = pd.DataFrame({"g": group.to_numpy(), "v": (sensor == "VIIRS").to_numpy(), "cell": cells})
    n_viirs = df[df.v].groupby("g").cell.nunique()
    n_modis = df[~df.v].groupby("g").cell.nunique()
    groups = pd.Index(df.g.unique())
    nv = n_viirs.reindex(groups, fill_value=0)
    nm = n_modis.reindex(groups, fill_value=0)
    return pd.Series(np.where(nv > 0, nv * CELL_HA, nm * MODIS_PIXEL_HA), index=groups)


def assign_ids(con: duckdb.DuckDBPyConnection, hs: pd.DataFrame, labels: np.ndarray, now: datetime) -> pd.Series:
    """Map component labels to stable event ids via `event_registry`.

    An event keeps the id of its earliest registered seed; components without
    one get a new `<kabupaten>-<YYYYMMDD>-<n>` id. Seeds of events swallowed
    by a merge are marked merged_into. If detections that joined two events
    go away (e.g. DEA ones replaced by FIRMS), the swallowed event comes back
    under its old id instead of a new one.
    """
    reg = con.execute("SELECT seed_hotspot_id, event_id, merged_into FROM event_registry").df()
    live = reg[reg.merged_into.isna()]
    seed_to_event = dict(zip(live.seed_hotspot_id, live.event_id))
    hs = hs.assign(label=labels)
    registered = hs[hs.id.isin(seed_to_event.keys())]
    # hs is time-ordered, so the first registered member per label is the oldest.
    keep = registered.drop_duplicates("label")
    label_to_event = dict(zip(keep.label, keep.id.map(seed_to_event)))
    merged = registered[~registered.id.isin(keep.id)]
    merges = [(label_to_event[lb], int(sid)) for lb, sid in zip(merged.label, merged.id)]

    # Components with no live seed but a merged one: un-merge the oldest.
    dormant = dict(zip(reg.seed_hotspot_id[reg.merged_into.notna()], reg.event_id[reg.merged_into.notna()]))
    revive = hs[~hs.label.isin(label_to_event.keys()) & hs.id.isin(dormant.keys())].drop_duplicates("label")
    label_to_event.update(zip(revive.label, revive.id.map(dormant)))
    if len(revive):
        con.register("revive_df", pd.DataFrame({"seed": revive.id.astype("int64")}))
        con.execute("UPDATE event_registry SET merged_into = NULL FROM revive_df r WHERE seed_hotspot_id = r.seed")
        con.unregister("revive_df")

    new = hs[~hs.label.isin(label_to_event.keys())].drop_duplicates("label")
    counters = con.execute(
        "SELECT regexp_extract(event_id, '^(.*)-\\d+$', 1) AS prefix, count(*) AS n FROM event_registry GROUP BY 1"
    ).df()
    next_n = dict(zip(counters.prefix, counters.n))
    new_rows = []
    days = pd.to_datetime(new.acq_time, utc=True).dt.tz_convert(LOCAL_TZ).dt.strftime("%Y%m%d")
    slugs = {k: slug(k) for k in new.kabupaten.dropna().unique()}
    for lb, sid, kab, day in zip(new.label, new.id, new.kabupaten, days):
        prefix = f"{slugs.get(kab, 'indonesia')}-{day}"
        next_n[prefix] = next_n.get(prefix, 0) + 1
        eid = f"{prefix}-{next_n[prefix]}"
        label_to_event[lb] = eid
        new_rows.append((int(sid), eid, now))

    if new_rows:
        con.register("reg_df", pd.DataFrame(new_rows, columns=["seed", "event_id", "created_at"]))
        con.execute("INSERT INTO event_registry SELECT seed, event_id, created_at, NULL FROM reg_df")
        con.unregister("reg_df")
    if merges:
        con.register("merge_df", pd.DataFrame(merges, columns=["into", "seed"]))
        con.execute("UPDATE event_registry SET merged_into = m.into FROM merge_df m WHERE seed_hotspot_id = m.seed")
        con.unregister("merge_df")
    log.info(
        "events: %d new, %d merged away, %d split off again, %d total",
        len(new_rows),
        len(merges),
        len(revive),
        len(label_to_event),
    )
    return hs.label.map(label_to_event)


NEAR_STATIC_KM = 2.0


def evidence_tier(hs: pd.DataFrame, index: pd.Index) -> tuple[pd.Series, pd.Series]:
    """(overpasses, tier) per event. A pass = one satellite within 30 min."""
    sat = hs.satellite if "satellite" in hs else hs.sensor
    t = pd.to_datetime(hs.acq_time, utc=True).dt.floor("30min")
    pass_key = sat.astype(str) + "|" + t.astype(str)
    passes = pass_key.groupby(hs.event_id).nunique().reindex(index).fillna(0).astype(int)
    per_pass = pass_key.groupby([hs.event_id, pass_key]).size().groupby(level=0).max().reindex(index).fillna(0)
    night = (
        (hs.daynight == "N").groupby(hs.event_id).any().reindex(index, fill_value=False) if "daynight" in hs else False
    )
    saturated = (
        ((hs.sensor == "VIIRS") & (hs.confidence == "high")).groupby(hs.event_id).any().reindex(index, fill_value=False)
    )
    strong = (passes >= 2) | (per_pass >= 2) | night | saturated
    return passes, pd.Series(np.where(strong, "strong", "single"), index=index)


def fire_names(hs: pd.DataFrame, ev: pd.DataFrame) -> list[str]:
    """'{desa}, {kabupaten}': the desa holding most of the fire's detections.
    Falls back to the nearest town (10k+ people, possibly tens of km away)
    where no desa is known (offshore, or no desa lookup)."""
    villages = desa.village_names(hs.lon.to_numpy(), hs.lat.to_numpy())
    if villages is None:
        place = ev.nearest_town
    else:
        named = pd.DataFrame({"event_id": hs.event_id.to_numpy(), "desa": villages}).dropna()
        top = named.groupby(["event_id", "desa"], sort=False).size().rename("n").reset_index()
        top = top.sort_values(["n", "desa"], ascending=[False, True]).drop_duplicates("event_id").set_index("event_id")
        place = top.desa.reindex(ev.index).fillna(ev.nearest_town)
    return [f"{p}, {k}" if isinstance(k, str) and p != k else str(p) for p, k in zip(place, ev.kabupaten, strict=True)]


def summarise(
    hs: pd.DataFrame, tagger: Tagger, season: int, now: datetime, sources: pd.DataFrame | None = None
) -> pd.DataFrame:
    g = hs.groupby("event_id", sort=False)
    ev = g.agg(
        first_seen=("acq_time", "min"),
        last_seen=("acq_time", "max"),
        centroid_lat=("lat", "mean"),
        centroid_lon=("lon", "mean"),
        bbox_w=("lon", "min"),
        bbox_s=("lat", "min"),
        bbox_e=("lon", "max"),
        bbox_n=("lat", "max"),
        hotspot_count=("id", "size"),
        peak_frp=("frp_mw", "max"),
        total_frp=("frp_mw", "sum"),
    )
    cells = pixel_cells(hs.sensor.to_numpy(), hs.lat.to_numpy(), hs.lon.to_numpy())
    ev["est_area_ha"] = area_by(hs.event_id, hs.sensor, cells).reindex(ev.index)
    peat = hs.on_peat.astype("boolean")
    if peat.notna().any():
        ev["peat_share"] = peat.astype(float).groupby(hs.event_id).mean()
        ev["on_peat"] = ev.peat_share >= PEAT_SHARE_MIN
    else:
        ev["peat_share"] = np.nan
        ev["on_peat"] = pd.NA
    # Province first (most detections), then the most common kabupaten among
    # that province's detections. Taking each mode separately could pair a
    # kabupaten with a province it is not in, for fires on a provincial border.
    prov = hs.groupby(["event_id", "provinsi"], sort=False).size().rename("n").reset_index()
    prov = prov.sort_values(["n", "provinsi"], ascending=[False, True]).drop_duplicates("event_id")
    prov = prov.set_index("event_id")
    ev["provinsi"] = prov.provinsi
    in_prov = hs[hs.provinsi.to_numpy() == ev.provinsi.reindex(hs.event_id).to_numpy()]
    kab = in_prov.groupby(["event_id", "kabupaten"], sort=False).size().rename("n").reset_index()
    kab = kab.sort_values(["n", "kabupaten"], ascending=[False, True]).drop_duplicates("event_id").set_index("event_id")
    ev["kabupaten"] = kab.kabupaten
    town, km = tagger.nearest_town(ev.centroid_lat.to_numpy(), ev.centroid_lon.to_numpy())
    ev["nearest_town"] = town
    ev["nearest_town_km"] = np.round(km, 1)
    ev["name"] = fire_names(hs, ev)
    ev["status"] = status_for(ev.last_seen, now)
    ev["n_passes"], ev["tier"] = evidence_tier(hs, ev.index)
    ev["season"] = season
    # Detections just outside the mask radius of a flare or smelter may be its
    # heat, or a real fire next to it; flag rather than guess.
    ev["near_static"] = False
    if sources is not None and len(sources):
        tree = cKDTree(to_xyz(sources.lat.to_numpy(), sources.lon.to_numpy()))
        d, _ = tree.query(to_xyz(ev.centroid_lat.to_numpy(), ev.centroid_lon.to_numpy()))
        ev["near_static"] = d <= NEAR_STATIC_KM
    return ev.reset_index().rename(columns={"event_id": "id"})


def snapshots(hs: pd.DataFrame) -> pd.DataFrame:
    """One row per event per WIB day: that day's detections and the cumulative footprint."""
    hs = hs.assign(date=pd.to_datetime(hs.acq_time, utc=True).dt.tz_convert(LOCAL_TZ).dt.date)
    hs = hs.sort_values(["event_id", "date"], kind="stable").reset_index(drop=True)

    daily = hs.groupby(["event_id", "date"], sort=True).agg(
        hotspot_count=("id", "size"), frp_sum=("frp_mw", "sum"), peak_frp=("frp_mw", "max")
    )
    # Cumulative area: count each pixel cell on the first day it burned.
    cells = pixel_cells(hs.sensor.to_numpy(), hs.lat.to_numpy(), hs.lon.to_numpy())
    first = pd.DataFrame({"event_id": hs.event_id, "date": hs.date, "cell": cells, "viirs": hs.sensor == "VIIRS"})
    first = first.drop_duplicates(["event_id", "cell"])  # sorted by date, so first sighting
    has_viirs = first.groupby("event_id").viirs.transform("any")
    first = first[first.viirs | ~has_viirs]
    first["ha"] = np.where(first.viirs, CELL_HA, MODIS_PIXEL_HA)
    new_ha = first.groupby(["event_id", "date"]).ha.sum().reindex(daily.index, fill_value=0.0)
    daily["growth_ha"] = new_ha
    daily["cum_area_ha"] = new_ha.groupby(level=0).cumsum()

    # Footprints: buffer every detection once, then union per event-day and
    # accumulate across days. Plain numpy slicing keeps the loop cheap.
    buf = np.where(hs.sensor.to_numpy() == "VIIRS", BUFFER_DEG["VIIRS"], BUFFER_DEG["MODIS"])
    circles = shapely.buffer(shapely.points(hs.lon.to_numpy(), hs.lat.to_numpy()), buf, quad_segs=2)
    key = hs.event_id.astype(str) + "|" + hs.date.astype(str)
    bounds = np.flatnonzero(np.r_[True, key.to_numpy()[1:] != key.to_numpy()[:-1], True])
    ev_ids = hs.event_id.to_numpy()
    geoms, day_geoms = [], []
    cum, cur_event = None, None
    for lo, hi in zip(bounds[:-1], bounds[1:]):
        day_geom = circles[lo] if hi - lo == 1 else shapely.union_all(circles[lo:hi])
        if ev_ids[lo] != cur_event:
            cur_event, cum = ev_ids[lo], day_geom
        else:
            cum = shapely.union(cum, day_geom)
        geoms.append(cum)
        day_geoms.append(day_geom)
    daily["perimeter_geom"] = shapely.to_wkb(shapely.simplify(np.array(geoms, dtype=object), 0.0005))
    daily["day_geom"] = shapely.to_wkb(shapely.simplify(np.array(day_geoms, dtype=object), 0.0005))
    return daily.reset_index()[
        [
            "event_id",
            "date",
            "perimeter_geom",
            "hotspot_count",
            "frp_sum",
            "peak_frp",
            "cum_area_ha",
            "growth_ha",
            "day_geom",
        ]
    ]


def build(
    con: duckdb.DuckDBPyConnection,
    season: int,
    tagger: Tagger,
    now: datetime,
    params: ClusterParams = CLUSTER,
    earliest_new: datetime | None = None,
) -> pd.DataFrame:
    """Recompute the events of a season (WIB calendar year).

    By default every event is rebuilt. With `earliest_new` (the oldest
    acquisition time among hotspots added since the last build) only the
    events those hotspots can reach are rebuilt; see affected_events.
    """
    scope = None if earliest_new is None else affected_events(con, season, earliest_new, params)
    hs = eligible(con, season, params, scope)
    if hs.empty:
        log.info("season %s: no eligible hotspots to cluster", season)
        return pd.DataFrame()
    labels = cluster.cluster_frame(hs, params)
    hs["event_id"] = assign_ids(con, hs, labels, now).to_numpy()
    sources = con.execute("SELECT lat, lon FROM static_sources").df()
    ev = summarise(hs, tagger, season, now, sources)
    snap = snapshots(hs)

    if scope is None:
        con.execute(f"UPDATE hotspots SET event_id = NULL WHERE {SEASON} = ?", [season])
        old = con.execute("SELECT id FROM fire_events WHERE season = ?", [season]).df()
    else:
        old = pd.DataFrame({"id": pd.Series(scope, dtype=str)})
    con.register("ids_df", hs[["id", "event_id"]])
    con.execute("UPDATE hotspots SET event_id = ids_df.event_id FROM ids_df WHERE hotspots.id = ids_df.id")
    con.unregister("ids_df")

    con.register("old_df", old)
    con.execute("DELETE FROM event_snapshots WHERE event_id IN (SELECT id FROM old_df)")
    con.execute("DELETE FROM fire_events WHERE id IN (SELECT id FROM old_df)")
    con.unregister("old_df")
    cols = [r[0] for r in con.execute("DESCRIBE fire_events").fetchall()]
    con.register("ev_df", ev[cols])
    con.execute("INSERT INTO fire_events SELECT * FROM ev_df")
    con.unregister("ev_df")
    snap_cols = [r[0] for r in con.execute("DESCRIBE event_snapshots").fetchall()]
    con.register("snap_df", snap[snap_cols])
    con.execute("INSERT INTO event_snapshots SELECT * FROM snap_df")
    con.unregister("snap_df")
    log.info(
        "season %s: %s %d events from %d hotspots",
        season,
        "rebuilt" if scope is None else f"updated ({len(scope)} touched)",
        len(ev),
        len(hs),
    )
    return ev


def backfill_tier(con: duckdb.DuckDBPyConnection) -> int:
    """Evidence tier for stored events that have none (built before it existed),
    from their member hotspots as `build` computes it. Returns events updated."""
    ids = con.execute("SELECT id FROM fire_events WHERE tier IS NULL ORDER BY id").df().id
    if ids.empty:
        return 0
    con.register("tier_ids", pd.DataFrame({"id": ids}))
    hs = con.execute(
        """SELECT event_id, satellite, sensor, daynight, confidence, acq_time FROM hotspots
           WHERE event_id IN (SELECT id FROM tier_ids)"""
    ).df()
    con.unregister("tier_ids")
    passes, tier = evidence_tier(hs, pd.Index(ids))
    con.register("tier_df", pd.DataFrame({"id": ids, "n_passes": passes.to_numpy(), "tier": tier.to_numpy()}))
    con.execute(
        "UPDATE fire_events SET tier = t.tier, n_passes = t.n_passes FROM tier_df t WHERE fire_events.id = t.id"
    )
    con.unregister("tier_df")
    return len(ids)


def repair_regions(con: duckdb.DuckDBPyConnection, season: int) -> int:
    """Re-pick provinsi, then kabupaten within it, for stored events whose
    pair does not occur in their own detections (events built before the
    pair was chosen hierarchically). Returns the number of events changed."""
    bad = con.execute(
        """
        WITH pairs AS (
            SELECT event_id, provinsi, kabupaten, count(*) AS n FROM hotspots
            WHERE event_id IS NOT NULL GROUP BY ALL
        ),
        prov AS (
            SELECT event_id, provinsi FROM (SELECT event_id, provinsi, sum(n) AS n FROM pairs GROUP BY ALL)
            QUALIFY row_number() OVER (PARTITION BY event_id ORDER BY n DESC, provinsi) = 1
        ),
        top AS (
            SELECT p.event_id, p.provinsi, p.kabupaten FROM pairs p JOIN prov USING (event_id, provinsi)
            QUALIFY row_number() OVER (PARTITION BY p.event_id ORDER BY p.n DESC, p.kabupaten) = 1
        )
        SELECT e.id, t.provinsi, t.kabupaten FROM fire_events e JOIN top t ON t.event_id = e.id
        WHERE e.season = ? AND e.kabupaten IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM pairs p WHERE p.event_id = e.id
                AND p.provinsi IS NOT DISTINCT FROM e.provinsi AND p.kabupaten IS NOT DISTINCT FROM e.kabupaten
          )
        """,
        [season],
    ).df()
    for r in bad.itertuples(index=False):
        con.execute(
            """UPDATE fire_events SET provinsi = ?, kabupaten = ?,
                      name = CASE WHEN nearest_town IS NULL THEN name ELSE nearest_town || ', ' || ? END
               WHERE id = ?""",
            [r.provinsi, r.kabupaten, r.kabupaten, r.id],
        )
    if len(bad):
        log.info("repaired region pair of %d events", len(bad))
    return len(bad)
