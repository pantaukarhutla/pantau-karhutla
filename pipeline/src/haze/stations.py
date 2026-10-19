"""Observed air quality from ground stations (keyless, hourly).

- ISPU (KLH, Indonesia): ~119 stations, ~29 in Kalimantan. Latest hour only,
  so we poll and keep the history ourselves. `a_pm25` is µg/m³.
- Malaysia DOE APIMS (MyEQMS portal JSON): last 24 h of the Malaysian API
  index per station; no raw PM2.5, so PM2.5 is estimated by inverting the
  DOE PM2.5 table (flagged `estimated`).
- Singapore NEA (data.gov.sg): hourly PM2.5 per region.
- BMKG (Indonesia's met agency): ~26 stations with hourly PM2.5, the latest hour
  on one page (bmkg.go.id/kualitas-udara/pm25) behind a bot check, so it is read
  through Cloudflare Browser Run (~1.3 browser-seconds a call; needs
  CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN). Hourly, unlike ISPU's 24 h mean:
  on 19 Oct 2026 BMKG Pangkalanbun read 500-1,050 µg/m³ every hour while the
  nearest ISPU station's 24 h mean was 54.

Each run upserts readings into `obs_aq` and publishes `stations.json`
(latest reading + 72 h history per station) with a CAMS comparison, since
CAMS is known to run low in peat haze (Grosvenor et al. 2024).
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import httpx
import numpy as np
import pandas as pd

from haze import http, openmeteo
from haze.cams_correction import cams_at_stations
from haze.config import CACHE_DIR
from haze.io import utc_minute, write_json

log = logging.getLogger(__name__)

ISPU_URL = "https://ispu.kemenlh.go.id/apimobile/v1/getStations"
DOE_URL = "https://eqms.doe.gov.my/api3/publicportalapims/apitablehourly"
NEA_URL = "https://api-open.data.gov.sg/v2/real-time/api/pm25"
BMKG_URL = "https://www.bmkg.go.id/kualitas-udara/pm25"
BROWSER_RUN = "https://api.cloudflare.com/client/v4/accounts/{account}/browser-rendering/content"
# States with haze-relevant stations: Johor, Selangor, Sabah, Sarawak, KL, Labuan.
DOE_STATES = (1, 10, 12, 13, 14, 16)

# Indonesian provinces by time zone (ISPU `waktu` is local time).
WITA = {
    "Kalimantan Selatan", "Kalimantan Timur", "Kalimantan Utara", "Bali", "Nusa Tenggara Barat",
    "Nusa Tenggara Timur", "Sulawesi Utara", "Sulawesi Tengah", "Sulawesi Selatan", "Sulawesi Tenggara",
    "Sulawesi Barat", "Gorontalo",
}  # fmt: skip
WIT = {
    "Maluku",
    "Maluku Utara",
    "Papua",
    "Papua Barat",
    "Papua Barat Daya",
    "Papua Tengah",
    "Papua Pegunungan",
    "Papua Selatan",
}

# DOE (Malaysia) PM2.5 24 h breakpoints -> API (USEPA-modified table).
DOE_PM25 = [(0, 0), (12.0, 50), (50.4, 100), (55.4, 150), (150.4, 200), (250.4, 300), (350.4, 400), (500.4, 500)]


def _num(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if np.isfinite(x) else None


def _utc_offset(provinsi: str | None) -> int:
    if provinsi in WIT:
        return 9
    if provinsi in WITA:
        return 8
    return 7


def parse_ispu(payload: dict) -> pd.DataFrame:
    rows = []
    for r in payload.get("rows", []):
        if str(r.get("is_maintenance")) == "1" or str(r.get("stasiun_uji")) == "1":
            continue
        pm = _num(r.get("a_pm25"))
        if pm is None or pm <= 1 or pm > 2000:  # stuck / zero sensors, absurd spikes
            pm = None
        if r.get("c_pm25") in (None, ""):
            pm = None  # KLH itself left this PM2.5 reading out of the official index
        pm10 = _num(r.get("a_pm10"))
        if pm is not None and pm10 is not None and pm10 > 1 and pm > pm10 * 1.1:
            pm = None  # PM2.5 is a fraction of PM10: a reading above it is a sensor fault
        lat, lon = _num(r.get("lat")), _num(r.get("lon"))
        if lat is None or lon is None or not r.get("waktu"):
            continue
        local = pd.Timestamp(r["waktu"])
        ts = (local - pd.Timedelta(hours=_utc_offset(r.get("provinsi")))).tz_localize("UTC")
        rows.append(
            {
                "network": "ISPU",
                "station_id": str(r["id_stasiun"]),
                "name": r.get("nama") or r.get("kota"),
                "region": r.get("provinsi"),
                "lat": lat,
                "lon": lon,
                "ts_utc": ts,
                "pm25": pm,
                "pm25_estimated": False,
                "index_value": _num(r.get("val")),
                "index_kind": "ISPU",
            }
        )
    return pd.DataFrame(rows)


def doe_api_to_pm25(api: float) -> float:
    """Invert the DOE PM2.5 -> API table (piecewise linear)."""
    for (c0, a0), (c1, a1) in zip(DOE_PM25, DOE_PM25[1:], strict=False):
        if api <= a1:
            return c0 + (c1 - c0) * (api - a0) / (a1 - a0)
    return DOE_PM25[-1][0]


def parse_doe(payload: dict) -> pd.DataFrame:
    rows = []
    for r in payload.get("api_table_hourly", []):
        api = _num(r.get("API"))
        if api is None or api < 0 or r.get("LATITUDE") is None:
            continue
        # The API is driven by the worst pollutant; only PM2.5-driven values
        # ("**" in the portal) say something about smoke concentration.
        pm25_driven = r.get("PARAM_SYMBOL") == "**"
        local = pd.Timestamp(r["DATETIME"])  # MYT = UTC+8
        loc = str(r.get("STATION_LOCATION") or r["STATION_ID"])
        rows.append(
            {
                "network": "DOE",
                "station_id": str(r["STATION_ID"]),
                "name": loc.split(",")[0].strip(),
                "region": loc.split(",")[-1].strip().title(),
                "lat": float(r["LATITUDE"]),
                "lon": float(r["LONGITUDE"]),
                "ts_utc": (local - pd.Timedelta(hours=8)).tz_localize("UTC"),
                "pm25": doe_api_to_pm25(api) if pm25_driven else None,
                "pm25_estimated": True,
                "index_value": api,
                "index_kind": "API",
            }
        )
    return pd.DataFrame(rows)


def parse_nea(payload: dict) -> pd.DataFrame:
    data = payload.get("data", {})
    where = {m["name"]: m["labelLocation"] for m in data.get("regionMetadata", [])}
    rows = []
    for item in data.get("items", []):
        ts = pd.Timestamp(item["timestamp"]).tz_convert("UTC")
        for region, v in item.get("readings", {}).get("pm25_one_hourly", {}).items():
            if region not in where or _num(v) is None:
                continue
            rows.append(
                {
                    "network": "NEA",
                    "station_id": f"SG-{region}",
                    "name": f"Singapore ({region})",
                    "region": "Singapore",
                    "lat": where[region]["latitude"],
                    "lon": where[region]["longitude"],
                    "ts_utc": ts,
                    "pm25": float(v),
                    "pm25_estimated": False,
                    "index_value": None,
                    "index_kind": "none",
                }
            )
    return pd.DataFrame(rows)


def parse_bmkg(html: str, now: datetime) -> pd.DataFrame:
    """The BMKG overview page's Nuxt payload: per station file, name, hour (WIB),
    PM2.5, category, lat, lon. The page carries no date: the hour is today's in
    WIB, or yesterday's if it is later than the current WIB hour (just after midnight)."""
    m = re.search(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise ValueError("BMKG page without its data payload")
    data = json.loads(m.group(1))
    wib = pd.Timestamp(now).tz_convert("Asia/Jakarta")
    rows = []
    for d in data:
        if not (isinstance(d, dict) and "nama_file" in d):
            continue
        st = {k: data[v] for k, v in d.items()}
        pm, hour = _num(st.get("PM25")), int(st["JAM"])
        if pm is None:
            continue
        day = wib.normalize() - pd.Timedelta(days=1 if hour > wib.hour else 0)
        rows.append(
            {
                "network": "BMKG",
                "station_id": "BMKG-" + str(st["nama_file"]).removeprefix("pm25_").removesuffix(".xml"),
                "name": f"{st['LOKASI']} (BMKG)",
                "region": None,
                "lat": float(st["LAT"]),
                "lon": float(st["LON"]),
                "ts_utc": (day + pd.Timedelta(hours=hour)).tz_convert("UTC"),
                "pm25": pm,
                "pm25_estimated": False,
                "index_value": None,
                "index_kind": "none",
            }
        )
    return pd.DataFrame(rows)


def fetch_bmkg(client: httpx.Client) -> str:
    """The overview page rendered by Cloudflare Browser Run (BMKG blocks plain HTTP clients).
    Images, fonts and styles are skipped: the data is in the server-rendered HTML."""
    r = client.post(
        BROWSER_RUN.format(account=os.environ["CLOUDFLARE_ACCOUNT_ID"]),
        headers={"Authorization": f"Bearer {os.environ['CLOUDFLARE_API_TOKEN']}"},
        json={
            "url": BMKG_URL,
            "gotoOptions": {"waitUntil": "domcontentloaded", "timeout": 30000},
            "rejectResourceTypes": ["image", "font", "stylesheet", "media"],
        },
        timeout=90.0,
    ).raise_for_status()
    log.info("BMKG via Browser Run: %s browser-ms", r.headers.get("x-browser-ms-used"))
    return r.json()["result"]


def fetch_all(client: httpx.Client) -> pd.DataFrame:
    """Every network is optional: one outage must not lose the others."""
    frames = []

    def attempt(name, fn):
        try:
            df = fn()
            log.info("stations %s: %d readings", name, len(df))
            frames.append(df)
        except Exception as exc:  # noqa: BLE001
            log.warning("stations %s failed: %s", name, exc)

    attempt("ISPU", lambda: parse_ispu(client.get(ISPU_URL).raise_for_status().json()))

    def doe():
        parts = []
        for k, state in enumerate(DOE_STATES):
            if k:
                time.sleep(2)  # be gentle with an undocumented endpoint
            parts.append(parse_doe(client.get(DOE_URL, params={"stateid": state}).raise_for_status().json()))
        return pd.concat(parts, ignore_index=True)

    attempt("DOE", doe)
    attempt("NEA", lambda: parse_nea(client.get(NEA_URL).raise_for_status().json()))
    if os.environ.get("CLOUDFLARE_ACCOUNT_ID") and os.environ.get("CLOUDFLARE_API_TOKEN"):
        attempt("BMKG", lambda: parse_bmkg(fetch_bmkg(client), datetime.now(UTC)))
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def upsert(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    df = df.drop_duplicates(["network", "station_id", "ts_utc"], keep="last")
    con.register("obs_new", df)
    con.execute(
        """INSERT OR REPLACE INTO obs_aq
        SELECT network, station_id, name, region, lat, lon, ts_utc, pm25, pm25_estimated, index_value, index_kind
        FROM obs_new"""
    )
    con.unregister("obs_new")
    return len(df)


def publish(con: duckdb.DuckDBPyConnection, now: datetime, out: Path, cache_dir: Path = CACHE_DIR) -> dict:
    since = now - timedelta(hours=72)
    obs = con.execute(
        "SELECT * FROM obs_aq WHERE ts_utc >= ? AND ts_utc <= ? ORDER BY ts_utc", [since, now + timedelta(hours=1)]
    ).df()
    result = {"generated_at": now.isoformat(timespec="minutes"), "stations": [], "cams_vs_obs": None}
    if not obs.empty:
        obs["ts_utc"] = pd.to_datetime(obs["ts_utc"], utc=True)
        latest = obs.sort_values("ts_utc").groupby(["network", "station_id"]).tail(1).reset_index(drop=True)
        smog, _ = openmeteo.read_cache(cache_dir)
        latest["cams"] = cams_at_stations(latest, smog)
        fresh = latest["ts_utc"] >= pd.Timestamp(now) - pd.Timedelta(hours=6)
        ok = fresh & latest["pm25"].notna() & ~latest["pm25_estimated"] & (latest["cams"] > 0)
        if ok.sum() >= 5:
            ratio = latest.loc[ok, "cams"] / latest.loc[ok, "pm25"]
            haze = ok & (latest["pm25"] > 100)
            hratio = latest.loc[haze, "cams"] / latest.loc[haze, "pm25"]
            result["cams_vs_obs"] = {
                "stations": int(ok.sum()),
                "median_ratio": round(float(ratio.median()), 2),
                "haze_stations": int(haze.sum()),
                "haze_median_ratio": round(float(hratio.median()), 2) if haze.sum() else None,
            }
            log.info("CAMS / observed PM2.5: %s", result["cams_vs_obs"])
        t0 = pd.Timestamp(since).floor("h")
        for (net, sid), g in obs.groupby(["network", "station_id"], sort=False):
            last = latest[(latest.network == net) & (latest.station_id == sid)].iloc[0]
            hours = ((g["ts_utc"] - t0).dt.total_seconds() // 3600).astype(int)
            series = [
                [int(h), None if pd.isna(v) else round(float(v), 1)] for h, v in zip(hours, g["pm25"], strict=True)
            ]
            result["stations"].append(
                {
                    "network": net,
                    "id": sid,
                    "name": last["name"],
                    "region": last["region"],
                    "lat": round(float(last["lat"]), 4),
                    "lon": round(float(last["lon"]), 4),
                    "time": utc_minute(last["ts_utc"]),
                    "pm25": None if pd.isna(last["pm25"]) else round(float(last["pm25"]), 1),
                    "estimated": bool(last["pm25_estimated"]),
                    "index": None if pd.isna(last["index_value"]) else float(last["index_value"]),
                    "index_kind": last["index_kind"],
                    "cams": None if pd.isna(last["cams"]) else round(float(last["cams"]), 1),
                    "stale": bool(last["ts_utc"] < pd.Timestamp(now) - pd.Timedelta(hours=6)),
                    "series": series,
                }
            )
        result["series_t0"] = utc_minute(t0)
    write_json(out / "stations.json", result)
    log.info("stations: published %d", len(result["stations"]))
    return result


def update(con: duckdb.DuckDBPyConnection) -> int:
    """Fetch the latest readings of every network into obs_aq."""
    with http.client(timeout=60.0) as client:
        n = upsert(con, fetch_all(client))
    log.info("stations: upserted %d readings", n)
    return n
