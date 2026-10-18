"""Air-quality categories."""

from __future__ import annotations

# Indonesian ISPU PM2.5 bands (P.14/MENLHK/SETJEN/KUM.1/7/2020): upper bound in µg/m³, category.
ISPU_PM25 = [
    (15.5, "baik"),
    (55.4, "sedang"),
    (150.4, "tidak_sehat"),
    (250.4, "sangat_tidak_sehat"),
    (1e9, "berbahaya"),
]


def ispu_category(pm25: float) -> str:
    for upper, name in ISPU_PM25:
        if pm25 <= upper:
            return name
    return ISPU_PM25[-1][1]
