import numpy as np

from haze import fwi


def test_van_wagner_reference_day():
    """First day of the CFFDRS test table (Van Wagner & Pickett 1985): start
    FFMC 85, DMC 6, DC 15; 13 April, 17 C, 42% RH, 25 km/h, no rain; Canadian
    April day lengths (Le 12.8, Lf 0.9)."""
    state = fwi.Codes(np.array(85.0), np.array(6.0), np.array(15.0))
    _, c = fwi.step(state, 17.0, 42.0, 25.0, 0.0, le=12.8, lf=0.9)
    assert round(float(c["FFMC"]), 1) == 87.7
    assert round(float(c["DMC"]), 1) == 8.5
    assert round(float(c["DC"]), 1) == 19.0
    assert round(float(c["ISI"]), 1) == 10.9
    assert round(float(c["FWI"]), 1) == 10.1


def test_rain_wets_and_dry_weather_dries():
    state = fwi.Codes(np.array([90.0, 90.0]), np.array([40.0, 40.0]), np.array([400.0, 400.0]))
    t, h, w = np.array([32.0, 32.0]), np.array([55.0, 55.0]), np.array([10.0, 10.0])
    _, c = fwi.step(state, t, h, w, np.array([0.0, 30.0]))
    assert c["FFMC"][0] > 85 > c["FFMC"][1]
    assert c["DC"][0] > 400 > c["DC"][1]
    assert c["DMC"][0] > 40 > c["DMC"][1]
