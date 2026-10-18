# Independent burned-area estimate (prototype)

A sample-based estimate of burned area with a 95% confidence interval that does not depend on
official figures. Results: `pipeline/static/independent_area.json`. Method, numbers and limits:
`docs/research/independent-burned-area.md`.

1. **Strata from our own detections.** Five strata: VIIRS detection cells, a ring out to 0.8 km,
   0.8–2 km, the rest of the KHG peat area, and the rest of the province (`strata.py`).
2. **Stratified random sample.** 700 points (`sample.py`).
3. **Labels.**
   - Sentinel-2 C1 L2A (Earth Search) and Landsat 8/9 (Planetary Computer) dNBR, with
     Key & Benson thresholds.
   - Sentinel-1 RTC VH backscatter drop, with a two-Gaussian threshold (`fetch.py`, `features.py`,
     `rules.py`).
4. **Estimator.** Stehman 2014 / Olofsson 2014 area estimator. The CI includes a Monte Carlo
   correction for label error, measured against 268 expert points from Gaveau et al. 2021
   (`estimate.py`, `gaveau_points.py`).
5. **Comparisons.** `gaveau_area.py`, `mcd64.py` and `firecci.py`.

Run: `python run_estimate.py <workdir> <year>`, from the pipeline venv with pystac-client,
rasterio and pyproj installed. It reads the DuckDB FIRMS archive read-only. Each
province-season takes about 15–25 minutes of keyless network reads.
