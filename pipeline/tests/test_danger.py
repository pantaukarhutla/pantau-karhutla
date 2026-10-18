from datetime import UTC, datetime

import numpy as np

from haze import danger


def test_model_ranks_dry_burning_peat_above_wet_quiet_cells():
    model = __import__("json").loads(danger.MODEL_FILE.read_text())
    wet = {"DC": np.array([20.0]), "FFMC": np.array([60.0]), "DMC": np.array([2.0]), "ISI": np.array([0.5])}
    dry = {"DC": np.array([600.0]), "FFMC": np.array([90.0]), "DMC": np.array([80.0]), "ISI": np.array([6.0])}
    p_wet = danger.predict(model, danger.features(wet, np.array([0.0]), 0, 0, 0))[0]
    p_dry = danger.predict(model, danger.features(dry, np.array([1.0]), 5, 40, 200))[0]
    assert p_wet < 0.05 < 0.4 < p_dry
    assert danger.classify(np.array([0.01, 0.1, 0.3, 0.9, np.nan]), danger.RISK_EDGES).tolist() == [0, 1, 2, 3, -1]


def test_build_writes_days_from_a_given_forecast(con, tmp_path):
    shape = (danger.GRID.ny, danger.GRID.nx)
    codes = {
        k: np.full(shape, v, np.float32) for k, v in {"FFMC": 88, "DMC": 40, "DC": 500, "ISI": 5, "FWI": 15}.items()
    }
    fc = ("2026/2026091000", {"2026-09-11": codes, "2026-09-09": codes})
    obj = danger.build(con, tmp_path, datetime(2026, 9, 10, 6, tzinfo=UTC), forecast=fc)
    assert [d["date"] for d in obj["days"]] == ["2026-09-11"]  # past days dropped
    day = obj["days"][0]
    assert len(day["prob_pct"]) == danger.GRID.nx * danger.GRID.ny
    # Very dry but no recent fires: elevated, not extreme (persistence matters).
    assert max(day["risk"]) >= 1 and min(day["risk"]) == -1  # -1 = masked cells
    assert (tmp_path / "danger.json").exists()


def test_freshen_brings_stale_codes_forward_to_today():
    """A GFWED run whose first day is 4 days old is stepped forward with the
    weather to today + 7; dry weather raises the drought code day by day."""
    import numpy as np

    from haze import openmeteo

    shape = (danger.GRID.ny, danger.GRID.nx)
    start = {k: np.full(shape, v) for k, v in {"FFMC": 80.0, "DMC": 20.0, "DC": 300.0, "ISI": 2.0, "FWI": 5.0}.items()}
    days = {"2026-10-14": start}
    g = openmeteo.FIRE_WX_GRID
    times = [f"2026-10-{d:02d}T{h:02d}:00" for d in range(13, 27) for h in range(24)]
    wx = {
        "times": times,
        "temperature_2m": np.full((len(times), g.ny, g.nx), 33.0),
        "relative_humidity_2m": np.full((len(times), g.ny, g.nx), 50.0),
        "wind_speed_10m": np.full((len(times), g.ny, g.nx), 10.0),
        "precipitation": np.zeros((len(times), g.ny, g.nx)),
    }
    rolled, issued = danger.freshen(days, datetime(2026, 10, 18, 3, tzinfo=UTC), wx)
    assert issued == "2026-10-18"
    assert min(rolled) == "2026-10-15" and max(rolled) == "2026-10-25"
    dc = [float(np.nanmean(rolled[d]["DC"])) for d in sorted(rolled)]
    assert all(b > a for a, b in zip(dc, dc[1:], strict=False)) and dc[0] > 300
