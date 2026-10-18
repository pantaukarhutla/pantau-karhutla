import os
import shutil
import tempfile
from datetime import UTC, datetime

# Tests never touch the real data/ and public/ dirs (DB, caches): haze.config
# reads these when first imported, so set them before importing haze.
_SCRATCH = tempfile.mkdtemp(prefix="haze-tests-")
os.environ["HAZE_DATA_DIR"] = os.path.join(_SCRATCH, "data")
os.environ["HAZE_PUBLIC_DIR"] = os.path.join(_SCRATCH, "public")
os.environ.pop("HAZE_DB", None)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402
import shapely  # noqa: E402

from haze import db  # noqa: E402
from haze.regions import Tagger  # noqa: E402


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_SCRATCH, ignore_errors=True)


def raw_viirs(rows):
    """Minimal FIRMS VIIRS CSV frame: rows of (lat, lon, 'YYYY-MM-DD', 'HHMM', conf, frp)."""
    return pd.DataFrame(
        {
            "latitude": [r[0] for r in rows],
            "longitude": [r[1] for r in rows],
            "bright_ti4": 330.0,
            "scan": 0.4,
            "track": 0.4,
            "acq_date": [r[2] for r in rows],
            "acq_time": [r[3] for r in rows],
            "satellite": "N",
            "instrument": "VIIRS",
            "confidence": [r[4] for r in rows],
            "version": "2.0NRT",
            "bright_ti5": 290.0,
            "frp": [r[5] for r in rows],
            "daynight": "D",
        }
    )


@pytest.fixture
def con():
    c = db.connect(":memory:")
    yield c
    c.close()


@pytest.fixture
def tagger():
    """Two fake kabupaten side by side on Kalimantan, one peat unit, two towns."""
    kab = [shapely.box(110.0, -2.0, 111.0, -1.0), shapely.box(111.0, -2.0, 112.0, -1.0)]
    towns = pd.DataFrame({"name": ["Westtown", "Easttown"], "lat": [-1.5, -1.5], "lon": [110.5, 111.5]})
    from scipy.spatial import cKDTree

    from haze.geo import to_xyz

    return Tagger(
        kab_ids=np.array(["kab:west", "kab:east"]),
        kab_names=np.array(["West", "East"]),
        kab_parent=np.array(["prov:kalbar", "prov:kalbar"]),
        prov_names={"prov:kalbar": "Kalimantan Barat"},
        kab_geoms=np.array(kab, dtype=object),
        kab_tree=shapely.STRtree(kab),
        peat_geoms=np.array([shapely.box(110.0, -2.0, 110.5, -1.0)], dtype=object),
        towns=towns,
        town_tree=cKDTree(to_xyz(towns.lat.to_numpy(), towns.lon.to_numpy())),
    )


NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
