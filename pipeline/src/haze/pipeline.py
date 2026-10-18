"""Run orchestration: ingest -> tag -> cluster -> publish, then the enrichment
steps. The scheduled job is a declared list of steps (STEPS) run in order."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd

from haze import (
    alerts,
    area,
    compare,
    danger,
    db,
    dea,
    desa,
    events,
    fire_history,
    firms,
    history,
    land,
    mask,
    openmeteo,
    outlook,
    progression,
    publish,
    regions,
    smoke,
    spread,
    stations,
)
from haze.config import SEED_DIR
from haze.io import read_json, wib_date, write_json
from haze.regions import Tagger
from haze.sql import SEASON

log = logging.getLogger(__name__)
# Forest-permit holders are published only when this is set; by default they
# stay hidden (and the permit lookup does not run).
PUBLISH_LAND = os.environ.get("HAZE_PUBLISH_LAND") == "1"


# ---------------------------------------------------------------- core operations


def ensure_reference(con: duckdb.DuckDBPyConnection) -> Tagger:
    """Load regions and the static mask if this DB has never seen them."""
    levels = {r[0] for r in con.execute("SELECT DISTINCT level FROM regions").fetchall()}
    if not {"provinsi", "kabupaten"} <= levels:
        regions.load_admin(con)
    if "peat" not in levels:
        regions.fetch_peat(con)
    if con.execute("SELECT count(*) FROM static_sources").fetchone()[0] == 0:
        mask.load_sources(con)
    return Tagger.from_db(con)


def tag_hotspots(con: duckdb.DuckDBPyConnection, tagger: Tagger, retag: bool = False) -> int:
    """Fill the derived columns (static mask, admin, peat) for untagged rows."""
    where = "" if retag else "WHERE in_indonesia IS NULL OR is_static IS NULL"
    hs = con.execute(f"SELECT id, lat, lon FROM hotspots {where}").df()
    if hs.empty:
        return 0
    sources = con.execute("SELECT lat, lon, kind FROM static_sources").df()
    lat, lon = hs.lat.to_numpy(), hs.lon.to_numpy()
    is_static, reason = mask.classify(lat, lon, sources)
    admin = tagger.admin(lat, lon)
    out = pd.DataFrame(
        {
            "id": hs.id,
            "is_static": is_static,
            "static_reason": reason,
            "provinsi": admin.provinsi,
            "kabupaten": admin.kabupaten,
            "in_indonesia": admin.in_indonesia,
            "on_peat": pd.array(tagger.peat(lat, lon), dtype="boolean"),
        }
    )
    con.register("tag_df", out)
    con.execute(
        """
        UPDATE hotspots SET is_static = t.is_static, static_reason = t.static_reason,
            provinsi = t.provinsi, kabupaten = t.kabupaten,
            in_indonesia = t.in_indonesia, on_peat = t.on_peat
        FROM tag_df t WHERE hotspots.id = t.id
        """
    )
    con.unregister("tag_df")
    log.info(
        "tagged %d hotspots: %d static, %d outside Indonesia",
        len(out),
        int(out.is_static.sum()),
        int((~out.in_indonesia).sum()),
    )
    return len(out)


def record_run(con, kind: str, started: datetime, new: int, ok: bool, message: str = "") -> None:
    latest = con.execute("SELECT max(acq_time) FROM hotspots").fetchone()[0]
    con.execute(
        "INSERT INTO runs VALUES (?, now(), ?, ?, ?, ?, ?)",
        [started, kind, new, latest, ok, message],
    )


def ingest(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    """Store the detections of a FIRMS frame that fall in BBOX; returns how many were new."""
    return db.upsert_hotspots(con, firms.in_bbox(df))


def ingest_archive(con: duckdb.DuckDBPyConnection, year: int) -> int:
    df = firms.read_archive(firms.download_archive(year))
    n = ingest(con, df)
    log.info("archive %s: %d detections, %d new", year, len(df), n)
    return n


def seasons_touched(con: duckdb.DuckDBPyConnection, since: datetime | None = None) -> list[int]:
    q = f"SELECT DISTINCT {SEASON} FROM hotspots"
    args = []
    if since is not None:
        q += " WHERE ingested_at >= ?"
        args.append(since)
    return sorted(r[0] for r in con.execute(q, args).fetchall())


def season_is_empty(con: duckdb.DuckDBPyConnection, season: int) -> bool:
    return con.execute(f"SELECT count(*) = 0 FROM hotspots WHERE {SEASON} = ?", [season]).fetchone()[0]


def build_events(con: duckdb.DuckDBPyConnection, tagger: Tagger, seasons: list[int], now: datetime) -> None:
    for season in seasons:
        events.build(con, season, tagger, now)


def update_events(con: duckdb.DuckDBPyConnection, tagger: Tagger, season: int, now: datetime, since: datetime) -> None:
    """Incremental rebuild for hotspots ingested at or after `since`."""
    earliest = con.execute(
        f"""
        SELECT min(acq_time) FROM hotspots
        WHERE ingested_at >= ? AND {SEASON} = ?
        """,
        [since, season],
    ).fetchone()[0]
    if earliest is None:
        return
    events.build(con, season, tagger, now, earliest_new=earliest)


def refresh_status(con: duckdb.DuckDBPyConnection, now: datetime) -> None:
    """Event status depends on wall-clock time, so update it even without new data."""
    ev = con.execute("SELECT id, last_seen FROM fire_events WHERE status != 'out'").df()
    if ev.empty:
        return
    ev["status"] = events.status_for(ev.last_seen, now)
    con.register("st_df", ev[["id", "status"]])
    con.execute("UPDATE fire_events SET status = s.status FROM st_df s WHERE fire_events.id = s.id")
    con.unregister("st_df")


# ---------------------------------------------------------------- the scheduled job


@dataclass
class RunContext:
    """What every step of a run sees."""

    con: duckdb.DuckDBPyConnection
    tagger: Tagger | None  # None for single-step commands that need no regions
    season: int
    now: datetime
    out: Path  # public/
    cold: bool = False  # the DB held no hotspots of this season when the run started
    new: int = 0  # hotspots added by this run
    day_range: int = 2  # days of NRT detections polled
    days: int = 10  # event pages and day files rewritten for events seen in the last N days
    backfill: bool = True  # rebuild the whole season on a cold start
    rebuild: bool = False  # recluster every event and rewrite every page (after haze backfill)
    force: bool = False  # refetch weather grids even if the cache is fresh
    results: dict[str, object] = field(default_factory=dict)  # step name -> what it returned

    def towns(self) -> pd.DataFrame:
        """GeoNames towns: the tagger's when this run loaded one."""
        return self.tagger.towns if self.tagger is not None else regions.load_towns()

    def produced(self, step: str, path: Path):
        """What `step` returned this run, else the file it published last time
        (a failed or empty step leaves the previous file in place)."""
        return self.results.get(step) or read_json(path)


@dataclass(frozen=True)
class Step:
    name: str
    fn: Callable[[RunContext], object]
    critical: bool = False  # a failure fails the run; otherwise it is logged and the run goes on
    every: timedelta | None = None  # run at most this often, judged by the age of `output`
    output: str | None = None  # file under RunContext.out that `every` looks at
    needs: tuple[str, ...] = ()  # steps whose results this one reads: they must come earlier


def _backfill_season(ctx: RunContext) -> int:
    """Cold start (new DB or evicted cache). With a MAP_KEY the season comes
    from the API; without one, from the committed seed, and the keyless feeds
    (last 7 days) fill the gap up to now."""
    if os.environ.get("FIRMS_MAP_KEY"):
        log.info("no %s hotspots in DB; backfilling the season", ctx.season)
        return ingest(ctx.con, firms.fetch_range(date(ctx.season, 1, 1), ctx.now.date()))
    seed = SEED_DIR / f"hotspots_{ctx.season}.parquet"
    if not seed.exists():
        return 0
    log.info("no %s hotspots in DB and no FIRMS_MAP_KEY; loading %s", ctx.season, seed.name)
    return ingest(ctx.con, firms.read_seed(seed)) + ingest(ctx.con, firms.fetch_recent(7))


def _ingest(ctx: RunContext) -> int:
    if ctx.cold and ctx.backfill:
        ctx.new += _backfill_season(ctx)
    ctx.new += ingest(ctx.con, firms.fetch_recent(ctx.day_range))
    # DEA direct readout has passes 1-3 h before FIRMS; it stands in for a
    # pass until FIRMS delivers it (haze.dea).
    replaced = dea.supersede(ctx.con)
    try:
        fresh = dea.new_passes(ctx.con, dea.fetch(dea.since_for(ctx.day_range, ctx.now)))
        n = ingest(ctx.con, fresh)
        log.info("DEA hotspots: %d new from passes FIRMS doesn't have yet; %d replaced by FIRMS", n, replaced)
        ctx.new += n
    except Exception as exc:  # an extra source: never stops the FIRMS update
        log.warning("DEA hotspots skipped: %s", exc)
    tag_hotspots(ctx.con, ctx.tagger)
    return ctx.new


def _events(ctx: RunContext) -> None:
    if ctx.cold or ctx.rebuild:
        events.build(ctx.con, ctx.season, ctx.tagger, ctx.now)
    elif ctx.new:
        update_events(ctx.con, ctx.tagger, ctx.season, ctx.now, since=ctx.now)
    # Status depends on the clock, so refresh it for untouched events too.
    refresh_status(ctx.con, ctx.now)


def event_extras(con: duckdb.DuckDBPyConnection, season: int) -> publish.EventExtras:
    """What event pages carry besides the event itself."""
    # Permit holders are withheld from public files unless explicitly enabled
    # (legal review pending: naming companies carries defamation risk).
    permits = land.event_land(con) if PUBLISH_LAND else {}
    try:
        burned_before = fire_history.event_history(con, season)
    except Exception as exc:  # noqa: BLE001
        log.warning("fire history per event skipped: %s", exc)
        burned_before = {}
    return publish.EventExtras(land=permits, history=burned_before)


def _publish(ctx: RunContext) -> None:
    # A cold start rebuilt every event, so every page is rewritten.
    days = None if ctx.cold or ctx.rebuild else ctx.days
    extras = event_extras(ctx.con, ctx.season)
    publish.publish_season(ctx.con, ctx.season, ctx.out, days=days, now=ctx.now, extras=extras)
    publish.recent_hotspots(ctx.con, ctx.now, ctx.out)
    publish.dashboard(ctx.con, ctx.season, ctx.now, ctx.out)
    publish.boundaries(ctx.con, ctx.out)
    publish.tables(ctx.con, ctx.season, ctx.now, ctx.out)


def _area(ctx: RunContext) -> dict:
    est = area.estimate(ctx.con, ctx.season, area.official_area(ctx.season))
    write_json(ctx.out / "area.json", est)
    return est


def _compare(ctx: RunContext) -> dict | None:
    """Southeast Asia comparison; Indonesia's year to date from our own S-NPP detections."""
    season = ctx.con.sql(
        f"""SELECT lon, lat, acq_time, confidence_raw, fire_type, satellite FROM hotspots
            WHERE satellite = 'SNPP' AND {SEASON} = ?""",
        params=[ctx.season],
    ).df()
    return compare.publish(ctx.out, ctx.now, season_df=season)


def _alerts(ctx: RunContext) -> dict:
    return alerts.publish(
        ctx.con,
        ctx.season,
        ctx.out,
        ctx.now,
        ctx.tagger,
        danger=ctx.produced("danger", ctx.out / "danger.json"),
        cities=ctx.produced("smoke", ctx.out / "smoke" / "cities.json"),
    )


STEPS = [
    Step("ingest", _ingest, critical=True),
    Step("events", _events, critical=True, needs=("ingest",)),
    # Forest-permit lookup (cached per cell, capped per run): only while the
    # permits are published, since nothing else reads them.
    *([Step("land", lambda ctx: land.update(ctx.con, ctx.season), needs=("events",))] if PUBLISH_LAND else []),
    Step("publish", _publish, critical=True, needs=("events",)),
    Step("area", _area),
    # ISPU only serves the latest hour, so every run counts; smoke corrects CAMS with these.
    Step("stations_fetch", lambda ctx: stations.update(ctx.con)),
    # Weather grids refresh every 6-12 h; a rate limit or outage must not fail the fire update.
    Step(
        "smoke",
        lambda ctx: smoke.build(ctx.con, ctx.towns(), ctx.out / "smoke", now=ctx.now, force=ctx.force),
        needs=("stations_fetch",),
    ),
    # Station page with CAMS at each station, from the grids smoke just cached.
    Step("stations", lambda ctx: stations.publish(ctx.con, ctx.now, ctx.out / "smoke"), needs=("smoke",)),
    Step("history", lambda ctx: history.publish(ctx.con, ctx.now, ctx.out)),
    # Fire danger outlook (GFWED GEOS-5 codes + persistence model).
    Step("danger", lambda ctx: danger.build(ctx.con, ctx.out, ctx.now)),
    # Seasonal outlook (ENSO / IOD / dry-spell chance): twice a day is plenty.
    Step("outlook", lambda ctx: outlook.build(ctx.out, ctx.now), every=timedelta(hours=12), output="outlook.json"),
    Step("fire_history", lambda ctx: fire_history.publish(ctx.con, ctx.season, ctx.out, ctx.now)),
    Step(
        "desa",
        lambda ctx: desa.publish(ctx.con, ctx.out, ctx.now, danger=ctx.produced("danger", ctx.out / "danger.json")),
        needs=("danger",),
    ),
    Step("alerts", _alerts, needs=("danger", "smoke")),
    Step("compare", _compare, needs=("ingest",)),
    Step("progression", lambda ctx: progression.publish_all(ctx.con, ctx.season, ctx.out, ctx.now), needs=("events",)),
    Step(
        "spread",
        lambda ctx: spread.forecast_all(
            ctx.con, ctx.tagger, ctx.out / "spread", ctx.now, openmeteo.read_cache()[1] or None
        ),
        needs=("events", "smoke"),
    ),
]


def check_order(steps: list[Step]) -> None:
    """Step names are unique and every step comes after the steps it needs."""
    seen: set[str] = set()
    for step in steps:
        if step.name in seen:
            raise ValueError(f"step {step.name!r} listed twice")
        missing = [n for n in step.needs if n not in seen]
        if missing:
            raise ValueError(f"step {step.name!r} needs {missing} to run before it")
        seen.add(step.name)


def _due(ctx: RunContext, step: Step) -> bool:
    if step.every is None:
        return True
    path = ctx.out / step.output
    return not path.exists() or time.time() - path.stat().st_mtime > step.every.total_seconds()


def run(ctx: RunContext, steps: list[Step] = STEPS, only: set[str] | None = None) -> RunContext:
    """Run `steps` in order (only those named in `only`, if given). A failing
    critical step raises; any other failure is logged and the run goes on."""
    check_order(steps)
    for step in steps:
        if only is not None and step.name not in only:
            continue
        if not _due(ctx, step):
            log.info("%s step: not due", step.name)
            continue
        t0 = time.monotonic()
        try:
            ctx.results[step.name] = step.fn(ctx)
        except Exception as exc:
            if step.critical:
                raise
            log.warning("%s step skipped after %.1f s: %s", step.name, time.monotonic() - t0, exc)
            continue
        log.info("%s step: %.1f s", step.name, time.monotonic() - t0)
    return ctx


# A fires-only run (haze run --fast): new detections, fires and the map,
# without the models; ~2 min on Actions instead of ~4.
FAST_STEPS = {"ingest", "events", "publish"}


def scheduled(
    con: duckdb.DuckDBPyConnection,
    now: datetime,
    out: Path,
    day_range: int = 2,
    days: int = 10,
    backfill: bool = True,
    tagger: Tagger | None = None,
    steps: list[Step] = STEPS,
    only: set[str] | None = None,
    rebuild: bool = False,
) -> RunContext:
    """The 30-minute job: poll FIRMS NRT (rebuilding the season on a cold
    start), update events, publish, enrich. The outcome is recorded in `runs`."""
    try:
        season = wib_date(now).year
        ctx = RunContext(
            con=con,
            tagger=tagger or ensure_reference(con),
            season=season,
            now=now,
            out=out,
            cold=season_is_empty(con, season),
            day_range=day_range,
            days=days,
            backfill=backfill,
            rebuild=rebuild,
        )
        run(ctx, steps, only=only)
    except Exception as exc:
        record_run(con, "run", now, 0, False, repr(exc)[:500])
        raise
    record_run(con, "run", now, ctx.new, True)
    log.info("run ok: %d new hotspots", ctx.new)
    return ctx
