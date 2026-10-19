import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from haze import cli, db, firms, pipeline
from haze.pipeline import RunContext, Step
from tests.conftest import raw_viirs

NOW = datetime(2026, 9, 10, 12, tzinfo=UTC)
# Steps that call upstream services (SiPongi, ISPU/DOE/NEA, Open-Meteo, GFWED, NOAA/BoM, JAXA P-Tree).
NETWORK_STEPS = {"area", "stations_fetch", "smoke", "history", "danger", "outlook", "spread", "himawari"}


def offline_steps() -> list[Step]:
    return [replace(s, fn=lambda ctx: None) if s.name in NETWORK_STEPS else s for s in pipeline.STEPS]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(self, request, **kwargs):
        raise AssertionError(f"network call in a test: {request.url}")

    monkeypatch.setattr(httpx.Client, "send", refuse)


def test_run_cold_start_then_poll(tmp_path, monkeypatch, tagger):
    calls = []

    def fake_range(start, end):
        calls.append(("range", start, end))
        return firms.normalise(raw_viirs([(-1.5, 110.2, "2026-09-09", "0600", "n", 10.0)]), "test")

    def fake_recent(day_range):
        calls.append(("recent", day_range))
        return firms.normalise(raw_viirs([(-1.5, 110.205, "2026-09-10", "0600", "h", 20.0)]), "test")

    monkeypatch.setattr(firms, "fetch_range", fake_range)
    monkeypatch.setattr(firms, "fetch_recent", fake_recent)
    monkeypatch.setenv("FIRMS_MAP_KEY", "test")  # keyed path: API backfill

    con, out = db.connect(tmp_path / "haze.duckdb"), tmp_path / "public"
    ctx = pipeline.scheduled(con, NOW, out, tagger=tagger, steps=offline_steps())
    assert ctx.cold and ctx.new == 2
    assert [c[0] for c in calls] == ["range", "recent"]  # cold start backfills the season first
    dash = json.loads((out / "dashboard.json").read_text())
    assert dash["counts"]["active"] == 1 and dash["counts"]["season_hotspots"] == 2

    ctx = pipeline.scheduled(con, NOW, out, tagger=tagger, steps=offline_steps())
    assert not ctx.cold
    assert [c[0] for c in calls] == ["range", "recent", "recent"]  # warm runs only poll
    live = json.loads((out / "events" / "live.geojson").read_text())
    assert [f["properties"]["id"] for f in live["features"]] == ["west-20260909-1"]
    # Prevention outputs come out of the same run (each step must not skip silently).
    assert json.loads((out / "fire_history.json").read_text())["national"]["cells"] >= 1
    assert (out / "feeds" / "indonesia.xml").exists() and (out / "alerts.json").exists()
    assert json.loads((out / "tables" / "desa.json").read_text())["fire_now"]["rows"]
    assert con.execute("SELECT kind, new_hotspots, ok FROM runs ORDER BY started_at").fetchall() == [
        ("run", 2, True),
        ("run", 0, True),
    ]


def test_cold_start_without_key_uses_seed_and_keyless(tmp_path, monkeypatch, tagger):
    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    raw = firms.normalise(raw_viirs([(-1.5, 110.2, "2026-09-09", "0600", "n", 10.0)]), "test")
    raw.drop(columns=["id", "confidence", "source"]).to_parquet(seed_dir / "hotspots_2026.parquet")
    calls = []

    def fake_keyless(period):
        calls.append(period)
        # The seed's detection again (same id) plus a new one.
        rows = [(-1.5, 110.2, "2026-09-09", "0600", "n", 10.0), (-1.5, 110.205, "2026-09-10", "0600", "h", 20.0)]
        return firms.normalise(raw_viirs(rows), "keyless")

    monkeypatch.delenv("FIRMS_MAP_KEY", raising=False)
    monkeypatch.setattr(pipeline, "SEED_DIR", seed_dir)
    monkeypatch.setattr(firms, "fetch_keyless", fake_keyless)
    monkeypatch.setattr(firms, "fetch_range", lambda *a: (_ for _ in ()).throw(AssertionError("no API")))
    out = tmp_path / "public"
    pipeline.scheduled(db.connect(tmp_path / "h.duckdb"), NOW, out, tagger=tagger, steps=offline_steps())
    assert calls[0] == "7d"  # gap since the seed, then the regular poll
    dash = json.loads((out / "dashboard.json").read_text())
    assert dash["counts"]["season_hotspots"] == 2  # seed + keyless overlap deduped


def test_steps_order_failures_and_throttle(tmp_path, caplog):
    def boom(ctx):
        raise RuntimeError("upstream down")

    ctx = RunContext(con=None, tagger=None, season=2026, now=NOW, out=tmp_path)
    steps = [
        Step("a", lambda ctx: "A"),
        Step("flaky", boom),
        Step("b", lambda ctx: ctx.results["a"] + "B", needs=("a",)),
        Step(
            "slow", lambda ctx: (ctx.out / "slow.json").write_text("{}"), every=timedelta(hours=12), output="slow.json"
        ),
    ]
    pipeline.run(ctx, steps)
    assert ctx.results["b"] == "AB" and "flaky" not in ctx.results  # a non-critical failure is skipped
    assert "flaky step skipped" in caplog.text and "upstream down" in caplog.text
    ctx.results.clear()
    pipeline.run(ctx, steps, only={"slow"})
    assert ctx.results == {}  # its output is fresh: not due
    with pytest.raises(RuntimeError):
        pipeline.run(ctx, [Step("core", boom, critical=True)])
    with pytest.raises(ValueError, match="needs"):
        pipeline.run(ctx, [Step("b", lambda ctx: None, needs=("a",)), Step("a", lambda ctx: None)])


def test_failed_run_is_recorded(tmp_path, tagger):
    def boom(ctx):
        raise RuntimeError("FIRMS down")

    con = db.connect(tmp_path / "h.duckdb")
    with pytest.raises(RuntimeError):
        pipeline.scheduled(con, NOW, tmp_path, tagger=tagger, steps=[Step("ingest", boom, critical=True)])
    ((ok, message),) = con.execute("SELECT ok, message FROM runs").fetchall()
    assert not ok and "FIRMS down" in message


def test_cli_run_passes_options(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(pipeline, "scheduled", lambda con, now, out, **kw: seen.update(out=out, **kw))
    cli.main(["--db", str(tmp_path / "h.duckdb"), "run", "--out", str(tmp_path), "--days", "3", "--no-backfill"])
    assert seen == {"out": tmp_path, "day_range": 2, "days": 3, "backfill": False, "only": None}
    cli.main(["--db", str(tmp_path / "h.duckdb"), "run", "--out", str(tmp_path), "--fast"])
    assert seen["only"] == pipeline.FAST_STEPS == {"ingest", "events", "publish"}


def test_cli_backfill_refills_then_rebuilds_everything(tmp_path, monkeypatch):
    from datetime import date

    from haze import backfill

    seen = {}
    monkeypatch.setattr(backfill, "fires", lambda con, start, end: seen.update(fires=(start, end)) or {"firms": 3})
    monkeypatch.setattr(backfill, "nea", lambda con, start, end: seen.update(nea=(start, end)))
    monkeypatch.setattr(backfill, "forget_pm25_history", lambda: seen.update(pm25=True))
    monkeypatch.setattr(pipeline, "scheduled", lambda con, now, out, **kw: seen.update(run=kw))
    args = ["--db", str(tmp_path / "h.duckdb"), "backfill", "--out", str(tmp_path), "--until", "2026-10-18"]
    cli.main(args)
    assert seen["fires"] == seen["nea"] == (date(2026, 7, 1), date(2026, 10, 18))
    assert seen["run"] == {"backfill": False, "rebuild": True, "only": None}
    assert "pm25" not in seen
    cli.main([*args, "--fires-only", "--refresh-pm25", "--since", "2026-09-01"])
    assert seen["fires"] == (date(2026, 9, 1), date(2026, 10, 18)) and seen["pm25"]
    assert seen["run"]["only"] == pipeline.FAST_STEPS


def test_rebuild_reclusters_and_rewrites_every_page(tmp_path, monkeypatch, tagger):
    monkeypatch.setattr(firms, "fetch_recent", lambda day_range: firms.empty_frame())
    monkeypatch.setattr("haze.dea.fetch", lambda since, client=None, until=None: firms.empty_frame())
    con, out = db.connect(tmp_path / "haze.duckdb"), tmp_path / "public"
    db.upsert_hotspots(con, firms.normalise(raw_viirs([(-1.5, 110.2, "2026-09-09", "0600", "n", 10.0)]), "test"))
    built, published = [], []
    monkeypatch.setattr(pipeline.events, "build", lambda *a, **kw: built.append(kw.get("earliest_new")))
    monkeypatch.setattr(pipeline.publish, "publish_season", lambda *a, **kw: published.append(kw["days"]))
    ctx = pipeline.scheduled(
        con, NOW, out, tagger=tagger, steps=offline_steps(), only=pipeline.FAST_STEPS, rebuild=True
    )
    assert not ctx.cold and ctx.rebuild
    assert built == [None] and published == [None]  # whole season, every page


def _firms_down(day_range):
    raise firms.FirmsError("every FIRMS source failed: VIIRS_SNPP_NRT, VIIRS_NOAA20_NRT, VIIRS_NOAA21_NRT, MODIS_NRT")


def test_firms_down_dea_carries_the_run(tmp_path, monkeypatch, tagger):
    """A runner that cannot reach FIRMS (19 Oct 2026) still takes DEA's pass and publishes."""
    monkeypatch.setattr(firms, "fetch_recent", _firms_down)
    dea_pass = firms.normalise(raw_viirs([(-1.5, 110.205, "2026-09-10", "0600", "h", 20.0)]), "dea:hotspots")
    monkeypatch.setattr("haze.dea.fetch", lambda since, client=None, until=None: dea_pass)
    con, out = db.connect(tmp_path / "haze.duckdb"), tmp_path / "public"
    db.upsert_hotspots(con, firms.normalise(raw_viirs([(-1.5, 110.2, "2026-09-09", "0600", "n", 10.0)]), "test"))
    ctx = pipeline.scheduled(con, NOW, out, tagger=tagger, steps=offline_steps())
    assert ctx.new == 1
    assert json.loads((out / "dashboard.json").read_text())["counts"]["season_hotspots"] == 2


def test_firms_and_dea_down_fails_the_run(tmp_path, monkeypatch, tagger):
    """With no hotspot source at all the run must fail visibly, not publish stale data as fresh."""
    monkeypatch.setattr(firms, "fetch_recent", _firms_down)

    def dea_down(since, client=None, until=None):
        raise httpx.ConnectError("Network is unreachable")

    monkeypatch.setattr("haze.dea.fetch", dea_down)
    con, out = db.connect(tmp_path / "haze.duckdb"), tmp_path / "public"
    db.upsert_hotspots(con, firms.normalise(raw_viirs([(-1.5, 110.2, "2026-09-09", "0600", "n", 10.0)]), "test"))
    with pytest.raises(RuntimeError, match="no hotspot source answered"):
        pipeline.scheduled(con, NOW, out, tagger=tagger, steps=offline_steps())
