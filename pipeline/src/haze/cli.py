"""`haze` command line. `run` is the 30-minute job (pipeline.STEPS); the other
subcommands run one part of it, or a maintenance task."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from haze import (
    backfill,
    db,
    evaluate,
    fire_history,
    history,
    land,
    mask,
    openmeteo,
    pipeline,
    publish,
    regions,
    spread,
)
from haze.config import DB_PATH, PUBLIC_DIR
from haze.io import wib_date
from haze.regions import Tagger

log = logging.getLogger("haze")


def _now() -> datetime:
    return datetime.now(UTC)


def cmd_regions(args) -> None:
    con = db.connect(args.db)
    regions.load_admin(con)
    log.info("peat source: %s", regions.fetch_peat(con))
    regions.load_towns()


def cmd_archive(args) -> None:
    con = db.connect(args.db)
    for year in args.years:
        pipeline.ingest_archive(con, year)


def cmd_static_mask(args) -> None:
    con = db.connect(args.db)
    src = mask.derive(con, args.years)
    if args.merge and mask.DERIVED_CSV.exists():
        # Add newly persistent cells (e.g. the current year) to the committed list.
        old = pd.read_csv(mask.DERIVED_CSV)
        src = pd.concat([old, src], ignore_index=True).drop_duplicates(["lat", "lon", "kind"])
    mask.write_derived(src)
    mask.load_sources(con)
    log.info("wrote %s (%d sources)", mask.DERIVED_CSV, len(src))


def cmd_backfill(args) -> None:
    """Refill every archived source from --since, then rebuild every event and page."""
    con = db.connect(args.db)
    started = _now()
    until = args.until or wib_date(started)
    counts = backfill.fires(con, args.since, until)
    if not args.fires_only:
        backfill.nea(con, args.since, until)
    if args.refresh_pm25:
        backfill.forget_pm25_history()
    pipeline.record_run(con, "backfill", started, sum(counts.values()), True, f"{args.since}..{until}: {counts}")
    if not args.no_rebuild:
        # The scheduled job on top: new NRT, then every event reclustered and every page rewritten.
        pipeline.scheduled(
            con, _now(), args.out, backfill=False, rebuild=True, only=pipeline.FAST_STEPS if args.fires_only else None
        )


def cmd_build(args) -> None:
    con = db.connect(args.db)
    tagger = pipeline.ensure_reference(con)
    if args.reload_mask:
        mask.load_sources(con)
    pipeline.tag_hotspots(con, tagger, retag=args.retag or args.reload_mask)
    now = args.now or _now()
    seasons = args.seasons or pipeline.seasons_touched(con)
    pipeline.build_events(con, tagger, seasons, now)


def cmd_publish(args) -> None:
    con = db.connect(args.db)
    now = args.now or _now()
    for season in args.seasons:
        extras = pipeline.event_extras(con, season)
        publish.publish_season(con, season, args.out, days=args.days, now=now, extras=extras)
    publish.recent_hotspots(con, now, args.out)
    publish.boundaries(con, args.out)
    publish.tables(con, max(args.seasons), now, args.out)
    publish.dashboard(con, max(args.seasons), now, args.out)


def cmd_run(args) -> None:
    pipeline.scheduled(
        db.connect(args.db),
        _now(),
        args.out,
        day_range=args.day_range,
        days=args.days,
        backfill=not args.no_backfill,
        only=pipeline.FAST_STEPS if args.fast else None,
    )


def _single_step(args, only: set[str], season: int | None = None, force: bool = False) -> None:
    """Run some steps of the scheduled job on their own (no regions needed)."""
    now = args.now or _now()
    ctx = pipeline.RunContext(
        con=db.connect(args.db),
        tagger=None,
        season=season or wib_date(now).year,
        now=now,
        out=args.out,
        force=force,
    )
    pipeline.run(ctx, only=only)


def cmd_smoke(args) -> None:
    _single_step(args, {"smoke"}, force=args.force)


def cmd_stations(args) -> None:
    _single_step(args, {"stations_fetch", "stations"})


def cmd_history(args) -> None:
    _single_step(args, {"history"})


def cmd_fire_history(args) -> None:
    if args.build:
        fire_history.build_static(fire_history.download())
    _single_step(args, {"fire_history"}, season=args.season)


def cmd_land(args) -> None:
    land.update(db.connect(args.db), args.season, max_queries=args.max_queries)


def cmd_spread(args) -> None:
    con = db.connect(args.db)
    tagger = pipeline.ensure_reference(con)
    now = args.now or _now()
    spread.forecast_all(con, tagger, args.out / "spread", now, openmeteo.read_cache()[1] or None, top=args.top)


def cmd_spread_eval(args) -> None:
    con = db.connect(args.db)
    tagger = Tagger.from_db(con)
    fit_cases = spread.prepare_cases(con, tagger, spread.hindcast_cases(con, args.fit_season, args.cases, seed=1))
    test_cases = spread.prepare_cases(con, tagger, spread.hindcast_cases(con, args.test_season, args.cases, seed=2))
    log.info("hindcast cases: fit %d, test %d", len(fit_cases), len(test_cases))
    log.info("defaults on test: %s", spread.evaluate(test_cases, spread.DEFAULT))
    params, trials = spread.calibrate(fit_cases)
    fit = spread.evaluate(fit_cases, params)
    test = spread.evaluate(test_cases, params)
    log.info("fitted %s", params)
    log.info("fit %s: %s", args.fit_season, fit)
    log.info("test %s: %s", args.test_season, test)
    if args.save:
        spread.save_params(params, {"season": args.fit_season, **fit}, {"season": args.test_season, **test})
        pd.DataFrame(trials).to_csv(spread.PARAMS_FILE.with_suffix(".trials.csv"), index=False)


def cmd_baselines(args) -> None:
    publish.write_baselines(db.connect(args.db), args.seasons)
    log.info("wrote %s", publish.BASELINES_CSV)


def cmd_evaluate(args) -> None:
    con = db.connect(args.db)
    report = evaluate.run(con, args.season, args.out, sheets=not args.no_sheets)
    log.info("report: %s", args.out / "report.json")
    for k in ("partition", "split_suspects", "merge_suspects"):
        log.info("%s: %s", k, report[k])


def _date(s: str) -> date:
    return date.fromisoformat(s)


def _datetime(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="haze", description=__doc__)
    p.add_argument("--db", default=os.environ.get("HAZE_DB", DB_PATH), help="DuckDB file")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("regions", help="download and load boundaries, peat, towns")
    s.set_defaults(func=cmd_regions)

    s = sub.add_parser("archive", help="load FIRMS yearly country archives")
    s.add_argument("years", type=int, nargs="+")
    s.set_defaults(func=cmd_archive)

    s = sub.add_parser("static-mask", help="derive static/static_sources_firms.csv from archive years")
    s.add_argument("--years", type=int, nargs="+", required=True)
    s.add_argument("--merge", action="store_true", help="add to the committed list instead of replacing it")
    s.set_defaults(func=cmd_static_mask)

    s = sub.add_parser("backfill", help="refill fires (FIRMS SP/NRT, DEA) and station history, rebuild everything")
    s.add_argument("--since", type=_date, default=history.HISTORY_START)
    s.add_argument("--until", type=_date, help="last day (default: today, WIB)")
    s.add_argument("--out", type=Path, default=PUBLIC_DIR)
    s.add_argument("--fires-only", action="store_true", help="skip station history; rebuild fires and pages only")
    s.add_argument("--refresh-pm25", action="store_true", help="refetch the daily CAMS PM2.5 history too")
    s.add_argument("--no-rebuild", action="store_true", help="load data only")
    s.set_defaults(func=cmd_backfill)

    s = sub.add_parser("build", help="tag hotspots and recompute events")
    s.add_argument("--seasons", type=int, nargs="*")
    s.add_argument("--retag", action="store_true", help="recompute tags for every hotspot")
    s.add_argument("--reload-mask", action="store_true", help="reload static sources, then retag")
    s.add_argument("--now", type=_datetime, help="reference time for event status (default: now)")
    s.set_defaults(func=cmd_build)

    s = sub.add_parser("publish", help="write public/ files")
    s.add_argument("--seasons", type=int, nargs="+", required=True)
    s.add_argument("--out", type=Path, default=PUBLIC_DIR)
    s.add_argument("--days", type=int, help="only rewrite day files / event pages for recent days")
    s.add_argument("--now", type=_datetime)
    s.set_defaults(func=cmd_publish)

    s = sub.add_parser("run", help="scheduled job: ingest NRT, build, publish")
    s.add_argument("--day-range", type=int, default=2)
    s.add_argument("--days", type=int, default=10)
    s.add_argument("--out", type=Path, default=PUBLIC_DIR)
    s.add_argument("--no-backfill", action="store_true")
    s.add_argument("--fast", action="store_true", help="fires only: ingest, events, publish (no models)")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("land", help="tag fires with the forest permit (PBPH) they burn in")
    s.add_argument("--season", type=int, default=_now().year)
    s.add_argument("--max-queries", type=int, default=1200)
    s.set_defaults(func=cmd_land)
    s = sub.add_parser("history", help="daily fires + CAMS PM2.5 since 1 July -> public/history/")
    s.add_argument("--out", type=Path, default=PUBLIC_DIR)
    s.add_argument("--now", type=_datetime)
    s.set_defaults(func=cmd_history)
    s = sub.add_parser("fire-history", help="where this season burns land that burned in 2012-2025")
    s.add_argument("--build", action="store_true", help="download S-NPP archives and rebuild the static grid")
    s.add_argument("--season", type=int)
    s.add_argument("--out", type=Path, default=PUBLIC_DIR)
    s.add_argument("--now", type=_datetime)
    s.set_defaults(func=cmd_fire_history)
    s = sub.add_parser("stations", help="ISPU / Malaysia DOE / Singapore NEA PM2.5 -> public/smoke/stations.json")
    s.add_argument("--out", type=Path, default=PUBLIC_DIR)
    s.add_argument("--now", type=_datetime)
    s.set_defaults(func=cmd_stations)
    s = sub.add_parser("smoke", help="CAMS smog + wind grids, puff model, city outlook -> public/smoke/")
    s.add_argument("--out", type=Path, default=PUBLIC_DIR)
    s.add_argument("--now", type=_datetime)
    s.add_argument("--force", action="store_true", help="refetch even if the cache is fresh")
    s.set_defaults(func=cmd_smoke)

    s = sub.add_parser("spread", help="spread forecasts for the most active fires -> public/spread/")
    s.add_argument("--out", type=Path, default=PUBLIC_DIR)
    s.add_argument("--now", type=_datetime)
    s.add_argument("--top", type=int, default=40)
    s.set_defaults(func=cmd_spread)

    s = sub.add_parser("spread-eval", help="fit spread model on one season, test on another (hindcast)")
    s.add_argument("--fit-season", type=int, default=2019)
    s.add_argument("--test-season", type=int, default=2023)
    s.add_argument("--cases", type=int, default=80)
    s.add_argument("--save", action="store_true", help="write static/spread_params.json")
    s.set_defaults(func=cmd_spread_eval)

    s = sub.add_parser("baselines", help="write static/season_baselines.csv from archive seasons")
    s.add_argument("--seasons", type=int, nargs="+", default=list(publish.BASELINE_SEASONS))
    s.set_defaults(func=cmd_baselines)

    s = sub.add_parser("evaluate", help="clustering heuristics + contact sheets for review")
    s.add_argument("--season", type=int, required=True)
    s.add_argument("--out", type=Path, default=Path("eval"))
    s.add_argument("--no-sheets", action="store_true")
    s.set_defaults(func=cmd_evaluate)

    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        args.func(args)
    except Exception:
        log.exception("%s failed", args.cmd)
        sys.exit(1)
