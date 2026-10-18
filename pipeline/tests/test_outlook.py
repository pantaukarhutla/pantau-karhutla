import httpx
import numpy as np

from haze import outlook


def test_parsers_and_phase():
    oni = "SEAS  YR   TOTAL   ANOM\n  JJA 2026  29.09   1.80\n  JAS 2026  29.12   2.16\n"
    assert outlook.parse_oni(oni)[-1] == {"season": "JAS", "year": 2026, "anom": 2.16}
    wk = " 07OCT2026     26.1 5.2     29.0 4.1     30.0 3.3     29.9 1.3\n"
    assert outlook.parse_nino_weekly(wk) == [{"week": "2026-10-07", "nino34": 3.3}]
    # CPC prints a negative anomaly against the SST before it.
    cold = " 03JAN1990     23.4-0.4     25.1-0.3     26.6-0.5     28.6 0.1\n"
    assert outlook.parse_nino_weekly(cold) == [{"week": "1990-01-03", "nino34": -0.5}]
    assert outlook.parse_iod("20261005,20261011,0.88\n") == [{"week_end": "2026-10-11", "iod": 0.88}]
    assert outlook.enso_phase(2.16) == "el_nino_very_strong" and outlook.enso_phase(0.1) == "neutral"


def test_dry_chances_from_ensemble():
    dry = [0.0] * 60
    wet = [10.0] * 60
    payload = [{"daily": {"precipitation_sum_member01": dry, "precipitation_sum_member02": wet}}] * len(outlook.POINTS)

    def handler(request):
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        rows = outlook.dry_chances(client)
    assert rows[0]["dry30"] == 0.5 and rows[0]["members"] == 2
    assert np.isclose(rows[0]["rain30_median_mm"], 150)
