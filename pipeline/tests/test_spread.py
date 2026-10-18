import numpy as np

from haze import spread
from haze.spread import Landscape, SpreadParams

P = SpreadParams(p0_peat=0.2, p0_other=0.2, persist_peat=0.0, persist_other=0.0, p_spot=0.0, members=200)


def flat(n=41, peat=False):
    return Landscape(land=np.ones((n, n), bool), peat=np.full((n, n), peat), elev=np.zeros((n, n)))


def centre(n=41):
    b = np.zeros((n, n), bool)
    b[n // 2, n // 2] = True
    return b


def mass_centre(active):
    p = active.sum(axis=0)
    ys, xs = np.indices(p.shape)
    return (ys * p).sum() / p.sum(), (xs * p).sum() / p.sum()


def test_wind_pushes_spread_downwind():
    n = 41
    calm = [{"speed": 0.0, "to_deg": 0.0, "rain_mm": 0.0}] * 6
    east = [{"speed": 10.0, "to_deg": 90.0, "rain_mm": 0.0}] * 6  # blowing towards the east
    rng = np.random.default_rng(0)
    a_calm = spread.simulate(centre(n), np.zeros((n, n), bool), flat(n), calm, P, rng, 6)
    a_east = spread.simulate(centre(n), np.zeros((n, n), bool), flat(n), east, P, rng, 6)
    assert abs(mass_centre(a_calm)[1] - n // 2) < 0.5
    assert mass_centre(a_east)[1] > n // 2 + 1.0  # columns increase eastwards


def test_uphill_spreads_faster():
    n = 41
    elev = np.tile(np.arange(n) * 60.0, (n, 1))  # rising to the east (~9 degrees)
    land = Landscape(np.ones((n, n), bool), np.zeros((n, n), bool), elev)
    calm = [{"speed": 0.0, "to_deg": 0.0, "rain_mm": 0.0}] * 6
    a = spread.simulate(centre(n), np.zeros((n, n), bool), land, calm, P, np.random.default_rng(1), 6)
    assert mass_centre(a)[1] > n // 2 + 0.5


def test_rain_suppresses_and_burnt_cells_do_not_reignite():
    n = 41
    dry = [{"speed": 0.0, "to_deg": 0.0, "rain_mm": 0.0}] * 4
    wet = [{"speed": 0.0, "to_deg": 0.0, "rain_mm": 30.0}] * 4
    rng = np.random.default_rng(2)
    a_dry = spread.simulate(centre(n), np.zeros((n, n), bool), flat(n), dry, P, rng, 4)
    a_wet = spread.simulate(centre(n), np.zeros((n, n), bool), flat(n), wet, P, rng, 4)
    assert a_wet.sum() < 0.05 * a_dry.sum()
    burnt = np.ones((n, n), bool)
    a_burnt = spread.simulate(centre(n), burnt, flat(n), dry, P, rng, 4)
    assert a_burnt.sum() == 0


def test_wind_factor_is_normalised():
    pw = spread.wind_factor(8.0, 45.0, 0.045, 0.131)
    assert abs(pw.mean() - 1.0) < 1e-9
    # Strongest toward north-east (dy=+1, dx=+1 is NEIGHBOURS index 7).
    assert int(np.argmax(pw)) == spread.NEIGHBOURS.index((1, 1))


def test_average_precision():
    truth = np.array([1, 0, 1, 0, 0], bool)
    assert spread.average_precision(np.array([0.9, 0.8, 0.7, 0.1, 0.0]), truth) == (1 + 2 / 3) / 2
    assert spread.average_precision(np.array([0.9, 0.1, 0.8, 0.0, 0.0]), truth) == 1.0
