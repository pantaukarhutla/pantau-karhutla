"""Early heat signals from JAXA Himawari-9 Wild Fire (L2 WLF v010: 10-minute, 2 km),
fetched over FTPS from the P-Tree system (registration; credit "Himawari Wild Fire
(JAXA P-Tree), from JMA Himawari-9").

Himawari sees each place every 10 minutes but is coarse: it finds only ~27% of the
fire cells VIIRS finds, and most of its points sit on fires VIIRS already shows. A
backtest (2 Sep - 18 Oct 2026, docs/research/audit-himawari.md) found one rule worth
showing, as an opt-in layer of *unconfirmed* signals, never counted as fires:

- reliability 5 (VIIRS confirms 91% of these at the same moment);
- seen twice: another detection (any reliability) within 3 km, 5-60 min earlier;
- new: no VIIRS detection (any confidence) within 5 km in the 72 h before;
- not within 2 km of a static heat source, not on the false-alarm list
  (static/himawari_false_alarms.csv: pixels flagged on 7+ days that VIIRS never saw).

That gives ~16 points a day in peak season; VIIRS confirms 76% at the same moment and
~39% within 24 h, and ~20 new fires a day appear ~6 h before VIIRS. A point leaves
the layer when VIIRS sees fire within 5 km after it, or 12 h after its last scan.
"""

from __future__ import annotations

import ftplib
import io
import logging
import os
import socket
import ssl
from datetime import datetime, timedelta
from pathlib import Path

import certifi
import duckdb
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from haze.compare import assign_country, load_polygons
from haze.config import BBOX, CACHE_DIR, STATIC_DIR
from haze.io import write_json

log = logging.getLogger(__name__)

ROOT = "/pub/himawari/L2/WLF/010"
COLS = ["id", "year", "month", "day", "hhmm", "lat", "lon", "area_km2", "volcano",
        "level", "reliability", "frp_wm2", "qf", "hot_id"]  # fmt: skip
WINDOW_H = 12  # points live this long after their last scan
REPEAT_KM, REPEAT_MIN = 3.0, (5, 60)
NEW_KM, LOOKBACK_H = 5.0, 72
STATIC_KM, FALSE_KM = 2.0, 1.5
CREDIT = "Himawari Wild Fire (JAXA P-Tree), from JMA Himawari-9"


class ImplicitFTPS(ftplib.FTP_TLS):
    """ftplib only speaks explicit TLS; P-Tree's port 990 wants TLS from the first byte."""

    def connect(self, host, port=990, timeout=60):
        self.host, self.port, self.timeout = host, port, timeout
        raw = socket.create_connection((host, port), timeout)
        self.sock = self.context.wrap_socket(raw, server_hostname=host)
        self.af = self.sock.family
        self.file = self.sock.makefile("r", encoding=self.encoding)
        self.welcome = self.getresp()
        return self.welcome

    def ntransfercmd(self, cmd, rest=None):
        # The server wants the data channel to resume the control channel's TLS session.
        conn, size = ftplib.FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            conn = self.context.wrap_socket(conn, server_hostname=self.host, session=self.sock.session)
        return conn, size


def configured() -> bool:
    return all(os.environ.get(k) for k in ("JAXA_FTP_HOST", "JAXA_FTP_USER", "JAXA_FTP_PASS"))


def parse(text: str) -> pd.DataFrame:
    """One WLF file -> rows in BBOX: t (UTC), lon, lat, reliability, frp_mw."""
    df = pd.read_csv(io.StringIO(text), comment="#", header=None, names=COLS)
    w, s, e, n = BBOX
    df = df[(df.lon >= w) & (df.lon <= e) & (df.lat >= s) & (df.lat <= n)]
    t = pd.to_datetime(
        df.year.astype(str) + df.month.astype(str).str.zfill(2) + df.day.astype(str).str.zfill(2)
        + df.hhmm.astype(str).str.zfill(4), format="%Y%m%d%H%M", utc=True,
    )  # fmt: skip
    return pd.DataFrame(
        {"t": t, "lon": df.lon, "lat": df.lat, "reliability": df.reliability, "frp_mw": df.frp_wm2 * df.area_km2}
    ).reset_index(drop=True)


def fetch(now: datetime, cache: Path = CACHE_DIR / "himawari", hours: int = WINDOW_H + 2) -> pd.DataFrame:
    """Detections of the last `hours` (+1 h for the repeat rule). Each file is fetched
    once and kept parsed in `cache`; files older than a day are dropped."""
    cache.mkdir(parents=True, exist_ok=True)
    # certifi's (Mozilla) roots: P-Tree's chain ends at SECOM TLS RSA Root CA 2024, which the
    # Ubuntu runner's system store lacked on 19 Oct 2026 (CERTIFICATE_VERIFY_FAILED).
    c = ImplicitFTPS(context=ssl.create_default_context(cafile=certifi.where()))
    c.connect(os.environ["JAXA_FTP_HOST"])
    c.login(os.environ["JAXA_FTP_USER"], os.environ["JAXA_FTP_PASS"])
    c.prot_p()
    frames, fetched = [], 0
    try:
        for k in range(hours + 1, -1, -1):
            h = pd.Timestamp(now).floor("h") - pd.Timedelta(hours=k)
            path = f"{ROOT}/{h:%Y%m}/{h:%d}/{h:%H}"
            try:
                names = sorted(n for n in c.nlst(path) if n.endswith(".csv"))
            except (ftplib.error_perm, ftplib.error_temp):
                continue  # the hour has no folder yet (P-Tree answers 450, a 'temporary' error)
            for name in (n.rsplit("/", 1)[-1] for n in names):
                local = cache / f"{name}.parquet"
                if not local.exists():
                    buf = io.BytesIO()
                    c.retrbinary(f"RETR {path}/{name}", buf.write)
                    parse(buf.getvalue().decode()).to_parquet(local, index=False)
                    fetched += 1
                frames.append(pd.read_parquet(local))
    finally:
        c.close()
    for f in cache.glob("*.parquet"):
        if f.stat().st_mtime < (now - timedelta(days=1)).timestamp():
            f.unlink()
    log.info("himawari: %d files fetched, %d cached", fetched, len(frames) - fetched)
    return pd.concat(frames, ignore_index=True) if frames else parse("")


def _seconds(t: pd.Series) -> np.ndarray:
    """Unix seconds, whatever unit the timestamps are stored in (pandas 3 uses us)."""
    return ((t - pd.Timestamp(0, tz="UTC")) // pd.Timedelta(seconds=1)).to_numpy(dtype=np.int64)


def _xy(lon, lat) -> np.ndarray:
    """Planar km around 2.5 S (under 2% error over Indonesia)."""
    return np.column_stack([np.asarray(lon) * 111.32 * np.cos(np.radians(-2.5)), np.asarray(lat) * 110.57])


def _near(points: np.ndarray, others: np.ndarray, km: float) -> np.ndarray:
    if not len(points) or not len(others):
        return np.zeros(len(points), bool)
    d, _ = cKDTree(others).query(points, distance_upper_bound=km)
    return np.isfinite(d)


def early(det: pd.DataFrame, viirs: pd.DataFrame, static: pd.DataFrame, false_alarms: pd.DataFrame, now: datetime):
    """The rule above. `viirs`: t, lon, lat (any confidence). Returns one row per signal:
    lon, lat, frp_mw, first, last (UTC)."""
    empty = pd.DataFrame(columns=["lon", "lat", "frp_mw", "first", "last"])
    if det.empty:
        return empty
    det = det.sort_values("t").reset_index(drop=True)
    xy = _xy(det.lon, det.lat)
    near_static = _near(xy, _xy(static.lon, static.lat), STATIC_KM)
    known_false = _near(xy, _xy(false_alarms.lon, false_alarms.lat), FALSE_KM)
    keep = ~near_static & ~known_false
    det, xy = det[keep].reset_index(drop=True), xy[keep]
    ts = _seconds(det.t)
    tree = cKDTree(xy) if len(xy) else None
    vts = _seconds(pd.to_datetime(viirs.t, utc=True)) if len(viirs) else np.array([], dtype=np.int64)
    vxy = _xy(viirs.lon, viirs.lat) if len(viirs) else np.empty((0, 2))
    vtree = cKDTree(vxy) if len(vxy) else None
    lo, hi = REPEAT_MIN[0] * 60, REPEAT_MIN[1] * 60
    rows = []
    for i in np.flatnonzero(det.reliability.to_numpy() == 5):
        # seen twice: another detection 5-60 min earlier within 3 km
        if not any(ts[i] - hi <= ts[j] <= ts[i] - lo for j in tree.query_ball_point(xy[i], REPEAT_KM)):
            continue
        if vtree is not None:
            near_v = vts[vtree.query_ball_point(xy[i], NEW_KM)]
            # new: no VIIRS in the 72 h before; still unconfirmed: none since
            if ((near_v >= ts[i] - LOOKBACK_H * 3600) & (near_v < ts[i])).any() or (near_v >= ts[i]).any():
                continue
        rows.append(i)
    if not rows:
        return empty
    sig = det.loc[rows].reset_index(drop=True)
    # one signal per place: merge within 3 km, keep the latest position
    sxy = _xy(sig.lon, sig.lat)
    group = np.arange(len(sig))
    for a, b in sorted(cKDTree(sxy).query_pairs(REPEAT_KM)):
        group[group == group[b]] = group[a]
    sig["g"] = group
    out = sig.groupby("g").agg(
        lon=("lon", "last"), lat=("lat", "last"), frp_mw=("frp_mw", "max"), first=("t", "min"), last=("t", "max")
    )
    out = out[out["last"] >= pd.Timestamp(now) - pd.Timedelta(hours=WINDOW_H)]
    return out.reset_index(drop=True)


def publish(con: duckdb.DuckDBPyConnection, now: datetime, out: Path) -> int:
    """himawari/early.json, or nothing when P-Tree credentials are not set."""
    if not configured():
        log.info("himawari: JAXA_FTP_* not set, skipped")
        return 0
    det = fetch(now)
    since = pd.Timestamp(now) - pd.Timedelta(hours=WINDOW_H + LOOKBACK_H + 2)
    viirs = con.execute(
        "SELECT acq_time AS t, lon, lat FROM hotspots WHERE sensor = 'VIIRS' AND acq_time >= ?", [since]
    ).df()
    static = con.execute("SELECT lon, lat FROM static_sources").df()
    false_alarms = pd.read_csv(STATIC_DIR / "himawari_false_alarms.csv")
    sig = early(det, viirs, static, false_alarms, now)
    # The backtest measured Indonesia only: drop signals in neighbouring countries and at sea.
    sig = sig[assign_country(sig.lon.to_numpy(), sig.lat.to_numpy(), load_polygons()) == "IDN"]
    stamp = "%Y-%m-%dT%H:%MZ"
    write_json(
        out / "himawari" / "early.json",
        {
            "generated_at": pd.Timestamp(now).strftime(stamp),
            "credit": CREDIT,
            "latest_scan": det.t.max().strftime(stamp) if len(det) else None,
            "columns": ["lon", "lat", "frp_mw", "first", "last"],
            "rows": [
                [round(r.lon, 3), round(r.lat, 3), round(float(r.frp_mw), 1), f"{r.first:{stamp}}", f"{r.last:{stamp}}"]
                for r in sig.itertuples()
            ],
        },
    )
    log.info("himawari: %d early signals from %d detections", len(sig), len(det))
    return len(sig)
