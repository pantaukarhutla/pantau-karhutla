import numpy as np
import pandas as pd

from haze import aq, openmeteo, puff, smoke


def test_wind_uv_meteorological_convention():
    # Wind FROM the west (270°) blows east: u > 0, v ~ 0.
    u, v = openmeteo.wind_uv(np.array([10.0]), np.array([270.0]))
    assert u[0] > 9.99 and abs(v[0]) < 1e-9
    u, v = openmeteo.wind_uv(np.array([5.0]), np.array([0.0]))  # from the north -> southward
    assert v[0] < -4.99


def test_ispu_categories():
    assert aq.ispu_category(10) == "baik"
    assert aq.ispu_category(100) == "tidak_sehat"
    assert aq.ispu_category(300) == "berbahaya"


def _wind(u_ms, v_ms, hours=12, rain=0.0):
    g = openmeteo.WIND_GRID
    shape = (hours, g.ny, g.nx)
    times = [
        (pd.Timestamp("2026-09-01T00:00Z") + pd.Timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(hours)
    ]
    return {
        "times": times,
        "u10": np.full(shape, u_ms),
        "v10": np.full(shape, v_ms),
        "rain": np.full(shape, rain),
    }


def _source(peat=True):
    return pd.DataFrame(
        {
            "id": ["f1"],
            "name": ["Test"],
            "lat": [-2.0],
            "lon": [112.0],
            "on_peat": [peat],
            "frp_24h": [600.0],
            "n_24h": [20],
        }
    )


def test_puffs_drift_downwind_and_rain_washes_out():
    s = _source()
    frp = s.frp_24h / puff.PUFF.overpasses_per_day
    s["pm25_kg_h"] = frp * 3600 * puff.PUFF.beta_peat * puff.PUFF.ef_pm25_peat / 1000
    s["tau_h"] = 48.0
    start = pd.Timestamp("2026-09-01T00:00Z")
    dry = puff.run_puffs(s, _wind(10.0, 0.0), start, hours=9)
    assert dry["level"] == "10"
    # Plume tip moves east ~36 km/h: after 9 h about 3 degrees of longitude.
    tip = dry["tracks"][0]["path"][-1]
    assert 114.5 < tip[0] < 115.5 and abs(tip[1] + 2.0) < 0.05
    # Rain washes each puff out with a ~1 h e-folding, so even the freshest
    # puffs keep at most about a third of their mass.
    wet = puff.run_puffs(s, _wind(10.0, 0.0, rain=5.0), start, hours=9)
    assert wet["frames"][-1].sum() < 0.4 * dry["frames"][-1].sum()


def test_spinup_and_receptor_attribution_by_source():
    a = _source()
    b = _source(peat=False).assign(id="f2", name="Far", lat=-2.0, lon=106.0)
    s = pd.concat([a, b], ignore_index=True).assign(provinsi=["Kalimantan Tengah", "Sumatera Selatan"])
    s["pm25_kg_h"] = [500.0, 500.0]
    s["tau_h"] = 48.0
    start = pd.Timestamp("2026-09-01T12:00Z")
    receptors = pd.DataFrame({"name": ["Down"], "country": ["ID"], "lat": [-2.0], "lon": [114.5]})
    out = puff.run_puffs(s, _wind(10.0, 0.0, hours=48), start, hours=6, spinup_h=12, receptors=receptors)
    # Frames start at `start` even with spin-up, and smoke is already in transit.
    assert out["times"][0] == "2026-09-01T15:00Z"
    split = out["receptor_by_source"][0]
    assert split.shape == (1, 2)
    # 10 m/s eastward: only the upwind source 2.5 deg west reaches the receptor.
    assert split[0, 0] > 0 and split[0, 1] < 1e-9 * split[0, 0]
    smog = {"times": ["2026-09-01T12:00"], "pm25": np.zeros((1, openmeteo.SMOG_GRID.ny, openmeteo.SMOG_GRID.nx))}
    (down,) = smoke.transboundary(s, out, smog, start, receptors=receptors)["receptors"]
    assert down["provinces"] == [{"name": "Kalimantan Tengah", "share": 1.0}] and down["peat_share"] == 1.0


def test_needs_refresh_per_grid(tmp_path):
    import json
    from datetime import UTC, datetime, timedelta

    from haze.openmeteo import needs_refresh

    now = datetime(2026, 10, 17, 12, tzinfo=UTC)
    state = tmp_path / "s.json"
    assert needs_refresh(state, now)
    state.write_text(json.dumps({"smog_at": (now - timedelta(hours=7)).isoformat(),
                                 "wind_at": (now - timedelta(hours=7)).isoformat()}))  # fmt: skip
    assert not needs_refresh(state, now, 12, "smog_at")  # CAMS: twice a day
    assert needs_refresh(state, now, 6, "wind_at")
    # Old state files only have fetched_at.
    state.write_text(json.dumps({"fetched_at": (now - timedelta(hours=1)).isoformat()}))
    assert not needs_refresh(state, now, 6, "wind_at")
