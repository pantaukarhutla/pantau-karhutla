"""Alerts as subscribable feeds (docs/research/prevention.md: alerts).

A static site cannot push, but it can publish Atom feeds, which any feed
reader, email digest or chat bot (IFTTT, Zapier, n8n, Telegram RSS bots)
can follow. One national feed and one per province, rebuilt every run from
the last ALERT_DAYS of data, so there is no state to keep: an alert's id is
stable (kind + subject + day), so readers show each one once.

Kinds:
- fire: a new fire that reached NEW_MIN_HOTSPOTS detections (peat / other)
  within its first 48 h; the national feed only takes the bigger ones
  (NATIONAL_MIN_HOTSPOTS). In Oct 2026 five detections in 48 h happened
  ~340 times a day nationwide; these thresholds give ~45 (provinces) and
  ~17 (national) a day;
- growth: a fire whose detected area grew >= GROWTH_MIN_PIXELS 375 m pixels
  in one WIB day;
- danger: a province with >= DANGER_MIN_SHARE of its land at "Ekstrem" fire
  danger tomorrow (danger.json). In a bad El Nino year that is most of the
  country, so the national feed gets one daily digest instead;
- air: a city whose forecast 24 h mean PM2.5 is "Tidak sehat" or worse
  (smoke/cities.json; Indonesian cities only).
Text is Bahasa Indonesia, the language of the people who act on it.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

import duckdb
import numpy as np
import pandas as pd

from haze.config import CELL_HA
from haze.io import utc_minute, wib_date, write_json, write_text_if_changed
from haze.regions import Tagger, slug
from haze.sql import PUBLIC

log = logging.getLogger(__name__)

ALERT_DAYS = 7
NEW_MIN_HOTSPOTS = {"peat": 10, "other": 20}
NATIONAL_MIN_HOTSPOTS = {"peat": 20, "other": 50}
GROWTH_MIN_PIXELS = 50  # ~700 ha of detected footprint in a day
DANGER_MIN_SHARE = 0.25
AIR_LEVELS = {"tidak_sehat": "Tidak sehat", "sangat_tidak_sehat": "Sangat tidak sehat", "berbahaya": "Berbahaya"}
MAX_FEED = 200
WIB = timedelta(hours=7)


def _iso(t) -> str:
    return pd.Timestamp(t).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def _wib(t) -> str:
    return (pd.Timestamp(t).tz_convert("UTC") + WIB).strftime("%d/%m %H.%M WIB")


def _id_int(v: float) -> str:
    """12345.6 -> '12.300' (Indonesian thousands separator, 2-3 significant figures)."""
    return f"{round(v, -2):,.0f}".replace(",", ".")


def fire_alerts(con: duckdb.DuckDBPyConnection, season: int, now: datetime) -> list[dict]:
    since = now - timedelta(days=ALERT_DAYS)
    # New fires: when the threshold-th public detection arrived, within 48 h
    # of the first; n48 decides whether it also goes to the national feed.
    new = con.execute(
        f"""
        WITH h AS (
            SELECT event_id, acq_time, row_number() OVER (PARTITION BY event_id ORDER BY acq_time) AS n
            FROM hotspots
            WHERE event_id IS NOT NULL AND {PUBLIC}
        ),
        e AS (
            SELECT *, CASE WHEN coalesce(on_peat, false) THEN {NEW_MIN_HOTSPOTS["peat"]}
                           ELSE {NEW_MIN_HOTSPOTS["other"]} END AS need,
                      CASE WHEN coalesce(on_peat, false) THEN {NATIONAL_MIN_HOTSPOTS["peat"]}
                           ELSE {NATIONAL_MIN_HOTSPOTS["other"]} END AS need_national
            FROM fire_events WHERE season = ? AND NOT coalesce(near_static, false)
        )
        SELECT e.id, e.name, e.provinsi, e.kabupaten, e.centroid_lat AS lat, e.centroid_lon AS lon,
               e.on_peat, e.first_seen, e.need, e.need_national,
               min(h.acq_time) FILTER (WHERE h.n = e.need) AS reached_at,
               count(*) FILTER (WHERE h.acq_time <= e.first_seen + INTERVAL 48 HOUR) AS n48
        FROM e JOIN h ON h.event_id = e.id
        GROUP BY ALL
        HAVING reached_at >= ? AND reached_at <= e.first_seen + INTERVAL 48 HOUR
        """,
        [season, since],
    ).df()
    out = []
    for r in new.itertuples(index=False):
        peat = " di lahan gambut" if r.on_peat else ""
        out.append(
            {
                "id": f"fire-{r.id}",
                "kind": "fire",
                "time": _iso(r.reached_at),
                "provinsi": r.provinsi,
                "kabupaten": r.kabupaten,
                "event": r.id,
                "lat": round(float(r.lat), 4),
                "lon": round(float(r.lon), 4),
                "peat": bool(r.on_peat),
                "name": r.name,
                "national": bool(r.n48 >= r.need_national),
                "hotspots": int(r.n48),
                "title": f"Kebakaran baru{peat}: {r.name}",
                "text": f"{int(r.n48)} titik panas dalam 48 jam sejak {_wib(r.first_seen)} "
                f"di {r.kabupaten}, {r.provinsi}.",
            }
        )
    grow = con.execute(
        """
        SELECT s.event_id, CAST(s.date AS VARCHAR) AS day, s.growth_ha, e.name, e.provinsi, e.kabupaten,
               e.centroid_lat AS lat, e.centroid_lon AS lon, e.on_peat, e.last_seen
        FROM event_snapshots s JOIN fire_events e ON e.id = s.event_id
        WHERE e.season = ? AND s.date >= CAST(? AS DATE) AND s.growth_ha >= ?
        """,
        [season, wib_date(now) - timedelta(days=ALERT_DAYS), GROWTH_MIN_PIXELS * CELL_HA],
    ).df()
    for r in grow.itertuples(index=False):
        px = round(r.growth_ha / CELL_HA)
        # Stamp at the end of that WIB day (or now, for today).
        at = min(pd.Timestamp(f"{r.day}T23:59:00+07:00"), pd.Timestamp(now))
        out.append(
            {
                "id": f"growth-{r.event_id}-{r.day}",
                "kind": "growth",
                "time": _iso(at),
                "provinsi": r.provinsi,
                "kabupaten": r.kabupaten,
                "event": r.event_id,
                "lat": round(float(r.lat), 4),
                "lon": round(float(r.lon), 4),
                "peat": bool(r.on_peat),
                "pixels": px,
                "name": r.name,
                "title": f"Kebakaran meluas: {r.name}",
                "text": f"+{px} piksel 375 m baru terdeteksi pada {r.day} "
                f"(≈{_id_int(r.growth_ha)} ha area deteksi, batas atas).",
            }
        )
    return out


def danger_alerts(d: dict | None, now: datetime) -> list[dict]:
    """From danger.json's content `d`."""
    if not d or not d.get("days"):
        return []
    day = d["days"][0]["date"]
    rows = []
    for r in d.get("provinces", []):
        if r["extreme_share"] >= DANGER_MIN_SHARE and r["cells"] >= 4:
            rows.append(
                {
                    "id": f"danger-{slug(r['provinsi'])}-{day}",
                    "kind": "danger",
                    "time": d.get("generated_at", _iso(now)).replace("Z", ":00Z")[:20],
                    "provinsi": r["provinsi"],
                    "share": r["extreme_share"],
                    "date": day,
                    "title": f"Risiko kebakaran ekstrem: {r['provinsi']} ({day})",
                    "text": f"{round(r['extreme_share'] * 100)}% wilayah berisiko Ekstrem untuk {day} "
                    "(model statistik dari kode cuaca kebakaran NASA GFWED, bukan peringatan resmi BMKG).",
                }
            )
    return rows


def air_alerts(d: dict | None, now: datetime, tagger: Tagger | None = None) -> list[dict]:
    """From smoke/cities.json's content `d`; provinces from `tagger`."""
    if not d:
        return []
    day = wib_date(now).isoformat()
    cities = [
        c
        for c in d.get("cities", [])
        if c.get("country", "ID") == "ID" and (c.get("ispu_days") or [None])[0] in AIR_LEVELS
    ]
    provs = [None] * len(cities)
    if tagger is not None and cities:
        lat, lon = np.array([c["lat"] for c in cities]), np.array([c["lon"] for c in cities])
        provs = [p if isinstance(p, str) else None for p in tagger.admin(lat, lon).provinsi]
    rows = []
    for k, c in enumerate(cities):
        cat = c["ispu_days"][0]
        rows.append(
            {
                "id": f"air-{slug(c['name'])}-{day}-{cat}",
                "kind": "air",
                "time": d.get("generated_at", _iso(now)).replace("Z", ":00Z")[:20],
                "city": c["name"],
                "provinsi": provs[k],
                "lat": c["lat"],
                "lon": c["lon"],
                "level": cat,
                "pm25": round(c["pm25_days"][0]),
                "title": f"Udara {AIR_LEVELS[cat]}: {c['name']} (24 jam ke depan)",
                "text": f"Prakiraan rata-rata PM2,5 24 jam ≈{round(c['pm25_days'][0])} µg/m³. "
                "Kurangi aktivitas di luar; kelompok rentan tetap di dalam. Cek ISPU resmi KLH.",
            }
        )
    return rows


def _atom(title: str, feed_id: str, alerts: list[dict], site: str, updated: str) -> str:
    def link(a):
        if a.get("event"):
            return f"{site}#/event/{a['event']}"
        if a.get("lat") is not None:
            return f"{site}#/@{a['lon']},{a['lat']},9"
        return site or "./"

    entries = "".join(
        f"""
  <entry>
    <id>urn:haze:{escape(a["id"])}</id>
    <title>{escape(a["title"])}</title>
    <updated>{a["time"]}</updated>
    <link href="{escape(link(a))}"/>
    <category term="{a["kind"]}"/>
    <summary>{escape(a["text"])}</summary>
  </entry>"""
        for a in alerts
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <id>urn:haze:feed:{escape(feed_id)}</id>
  <title>{escape(title)}</title>
  <subtitle>Peringatan otomatis dari data satelit dan model; bukan peringatan resmi pemerintah.</subtitle>
  <updated>{updated}</updated>
  <author><name>Pantau Karhutla</name></author>{entries}
</feed>
"""


def publish(
    con: duckdb.DuckDBPyConnection,
    season: int,
    out: Path,
    now: datetime | None = None,
    tagger: Tagger | None = None,
    danger: dict | None = None,
    cities: dict | None = None,
) -> dict:
    """Feeds and alerts.json. `danger` and `cities` are the content of
    danger.json and smoke/cities.json (no alerts of that kind when None)."""
    now = now or datetime.now(UTC)
    alerts: list[dict] = []
    for name, fn in (
        ("fire", lambda: fire_alerts(con, season, now)),
        ("danger", lambda: danger_alerts(danger, now)),
        ("air", lambda: air_alerts(cities, now, tagger)),
    ):
        try:
            alerts += fn()
        except Exception as exc:  # noqa: BLE001
            log.warning("alerts %s skipped: %s", name, exc)
    alerts.sort(key=lambda a: a["time"], reverse=True)
    national = [a for a in alerts if a["kind"] != "danger" and a.get("national", True)]
    by_share = sorted((a for a in alerts if a["kind"] == "danger"), key=lambda a: -a["share"])
    if by_share:
        top = ", ".join(f"{a['provinsi']} {round(a['share'] * 100)}%" for a in by_share[:8])
        more = f" dan {len(by_share) - 8} provinsi lain" if len(by_share) > 8 else ""
        national.append(
            {
                "id": f"danger-digest-{by_share[0]['date']}",
                "kind": "danger",
                "time": by_share[0]["time"],
                "title": f"Risiko kebakaran ekstrem {by_share[0]['date']}: {len(by_share)} provinsi",
                "text": f"Bagian wilayah berisiko Ekstrem: {top}{more}. Model statistik, bukan peringatan resmi BMKG.",
            }
        )
        national.sort(key=lambda a: a["time"], reverse=True)
    site = os.environ.get("HAZE_SITE_URL", "").rstrip("/") + ("/" if os.environ.get("HAZE_SITE_URL") else "")
    updated = _iso(now)
    feeds = out / "feeds"
    write_text_if_changed(
        feeds / "indonesia.xml",
        _atom("Pantau Karhutla: peringatan Indonesia", "indonesia", national[:MAX_FEED], site, updated),
    )
    provinces = sorted({a["provinsi"] for a in alerts if a.get("provinsi")})
    for p in provinces:
        sub = [a for a in alerts if a.get("provinsi") == p][:MAX_FEED]
        write_text_if_changed(
            feeds / f"{slug(p)}.xml", _atom(f"Pantau Karhutla: peringatan {p}", slug(p), sub, site, updated)
        )
    obj = {
        "generated_at": utc_minute(now),
        "days": ALERT_DAYS,
        "rules": {
            "new_min_hotspots": NEW_MIN_HOTSPOTS,
            "national_min_hotspots": NATIONAL_MIN_HOTSPOTS,
            "growth_min_pixels": GROWTH_MIN_PIXELS,
            "danger_min_share": DANGER_MIN_SHARE,
        },
        "feeds": {"indonesia": "feeds/indonesia.xml", **{p: f"feeds/{slug(p)}.xml" for p in provinces}},
        "alerts": alerts[:500],
    }
    write_json(out / "alerts.json", obj)
    counts = pd.Series([a["kind"] for a in alerts]).value_counts().to_dict() if alerts else {}
    log.info("alerts: %s across %d provinces", counts, len(provinces))
    return obj
