"""Guards on committed reference data: a test or script that writes into
static/ by mistake (it happened once: a fixture replaced the 1.5 M-cell fire
history) must fail CI instead of shipping."""

import json

import numpy as np
import pandas as pd

from haze.config import STATIC_DIR


def test_fire_history_is_the_full_archive():
    fh = pd.read_parquet(STATIC_DIR / "fire_history.parquet")
    stats = json.loads((STATIC_DIR / "fire_history.json").read_text())
    assert len(fh) > 1_000_000 and len(fh) == stats["cells"]
    assert stats["hindcast"]["lift"] > 2


def test_desa_lookup_matches_its_table():
    desa = pd.read_parquet(STATIC_DIR / "desa.parquet")
    grid = np.load(STATIC_DIR / "desa_grid.npz")["idx"]
    assert len(desa) > 80_000 and grid.max() < len(desa)
    assert (grid >= 0).sum() > 1_000_000
    assert int(desa.cells.sum()) == int((grid >= 0).sum())
