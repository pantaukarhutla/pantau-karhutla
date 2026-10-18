"""Seasonal outlook for preparedness: El Nino / Indian Ocean Dipole state and
the chance that the coming 30 / 60 days stay dry (docs/research/prevention.md).

Drought decides how bad a fire year is (Field et al. 2016: fire responds
sharply to long spells under ~4 mm/day), and seasonal forecasts give weeks of
lead time (Spessa et al. 2015; Shawki et al. 2017, who also show the IOD
matters for Sumatra). Sources, all keyless:
- NOAA CPC ONI (3-month Nino3.4) and weekly Nino3.4 (OISST);
- Australian Bureau of Meteorology weekly IOD;
- Open-Meteo seasonal ensemble (daily rain, ~50 members) per province city.
Each part is optional: an outage drops that part, not the card.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from pathlib import Path

import httpx
import numpy as np

from haze import http
from haze.io import utc_minute, write_json

log = logging.getLogger(__name__)

ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
NINO_WEEKLY_URL = "https://www.cpc.ncep.noaa.gov/data/indices/wksst9120.for"
IOD_URL = "https://reg.bom.gov.au/clim_data/IDCK000072/iod_1.txt"
SEASONAL_URL = "https://seasonal-api.open-meteo.com/v1/seasonal"
DRY_MM_DAY = 4.0
# One representative point per fire-prone province (capital or fire belt).
POINTS = [
    ("Kalimantan Tengah", -2.21, 113.92),
    ("Kalimantan Barat", -0.03, 109.34),
    ("Kalimantan Selatan", -3.32, 114.59),
    ("Kalimantan Timur", -0.50, 117.15),
    ("Riau", 0.51, 101.45),
    ("Jambi", -1.61, 103.61),
    ("Sumatera Selatan", -2.98, 104.78),
    ("Papua Selatan (Merauke)", -8.49, 140.40),
]


def parse_oni(text: str, n: int = 6) -> list[dict]:
    rows = []
    for line in text.splitlines()[1:]:
        p = line.split()
        if len(p) == 4:
            rows.append({"season": p[0], "year": int(p[1]), "anom": float(p[3])})
    return rows[-n:]


def parse_nino_weekly(text: str, n: int = 12) -> list[dict]:
    """Weekly Nino 3.4 anomaly from CPC's wksst9120.for: a date, then SST and
    anomaly for Nino 1+2, 3, 3.4 and 4. A negative anomaly is printed against
    the SST before it ("23.4-0.4"), so the numbers are read by pattern, not
    by splitting on spaces."""
    rows = []
    for line in text.splitlines():
        p = line.split(maxsplit=1)
        if len(p) != 2 or not p[0][:2].isdigit():
            continue
        values = re.findall(r"-?\d+\.\d+", p[1])
        if len(values) == 8:
            d = datetime.strptime(p[0], "%d%b%Y").date().isoformat()
            rows.append({"week": d, "nino34": float(values[5])})
    return rows[-n:]


def parse_iod(text: str, n: int = 12) -> list[dict]:
    rows = []
    for line in text.splitlines():
        p = line.strip().split(",")
        if len(p) == 3 and p[0].isdigit():
            rows.append({"week_end": f"{p[1][:4]}-{p[1][4:6]}-{p[1][6:]}", "iod": float(p[2])})
    return rows[-n:]


def enso_phase(oni: float) -> str:
    if oni >= 2.0:
        return "el_nino_very_strong"
    if oni >= 1.5:
        return "el_nino_strong"
    if oni >= 0.5:
        return "el_nino"
    if oni <= -0.5:
        return "la_nina"
    return "neutral"


def dry_chances(client: httpx.Client) -> list[dict]:
    """Per point: share of ensemble members whose mean rain over the next
    30 / 60 days stays under DRY_MM_DAY."""
    r = client.get(
        SEASONAL_URL,
        params={
            "latitude": ",".join(str(p[1]) for p in POINTS),
            "longitude": ",".join(str(p[2]) for p in POINTS),
            "daily": "precipitation_sum",
            "forecast_days": 60,
        },
    )
    r.raise_for_status()
    data = r.json()
    data = data if isinstance(data, list) else [data]
    out = []
    for (name, _, _), d in zip(POINTS, data, strict=False):
        daily = d.get("daily", {})
        members = [
            np.array([np.nan if v is None else v for v in vals], float)
            for k, vals in daily.items()
            if k.startswith("precipitation_sum")
        ]
        if not members:
            continue
        m = np.stack(members)
        out.append(
            {
                "provinsi": name,
                "members": int(len(m)),
                "dry30": round(float(np.mean(np.nanmean(m[:, :30], axis=1) < DRY_MM_DAY)), 2),
                "dry60": round(float(np.mean(np.nanmean(m[:, :60], axis=1) < DRY_MM_DAY)), 2),
                "rain30_median_mm": round(float(np.nanmedian(np.nansum(m[:, :30], axis=1)))),
            }
        )
    return out


def build(out: Path, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    obj: dict = {"generated_at": utc_minute(now), "dry_threshold_mm_day": DRY_MM_DAY}
    with http.client(timeout=60.0) as client:
        for key, url, parse in (
            ("oni", ONI_URL, parse_oni),
            ("nino34_weekly", NINO_WEEKLY_URL, parse_nino_weekly),
            ("iod_weekly", IOD_URL, parse_iod),
        ):
            try:
                obj[key] = parse(client.get(url).raise_for_status().text)
            except Exception as exc:  # noqa: BLE001
                log.warning("outlook %s unavailable: %s", key, exc)
                obj[key] = []
        try:
            obj["dry_chance"] = dry_chances(client)
        except Exception as exc:  # noqa: BLE001
            log.warning("outlook seasonal rain unavailable: %s", exc)
            obj["dry_chance"] = []
    if obj["oni"]:
        obj["enso_phase"] = enso_phase(obj["oni"][-1]["anom"])
    if obj["iod_weekly"]:
        obj["iod_positive"] = obj["iod_weekly"][-1]["iod"] >= 0.4
    write_json(out / "outlook.json", obj)
    log.info(
        "outlook: ENSO %s, IOD %s, %d provinces", obj.get("enso_phase"), obj.get("iod_positive"), len(obj["dry_chance"])
    )
    return obj
