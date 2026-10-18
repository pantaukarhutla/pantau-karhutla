# Research basis: fire spread and smoke models

Compiled 2026-10-17 to design the spread forecast (`haze spread`) and smoke model (`haze smoke`).

How each claim was checked:

- **[V]** read in the source's own text.
- **[S]** abstract or snippet only.
- **[M]** from memory; check before relying on it.

## Data-driven spread from active-fire sequences

| Source | What it gives us |
| --- | --- |
| Huot et al. 2022, *Next Day Wildfire Spread*, IEEE TGRS, doi:10.1109/TGRS.2022.3192974 | Next-day fire masks at 1 km. AUC-PR: persistence 11.5%, CNN 28.4% [V]. Persistence is the baseline to beat; AUC-PR is the metric. |
| Gerard et al. 2023, *WildfireSpreadTS*, NeurIPS D&B | VIIRS 375 m next-day masks. Persistence AP 0.193 and F1 0.432 [V]. Best models reach AP ≈ 0.29–0.33 [V]. |
| Andela et al. 2019, *Global Fire Atlas*, ESSD 11:529 | Spread speed = shortest path from yesterday's fire line, per day. Persistence gap 4–10 days [V]. Equatorial Asia mean expansion 0.3 km²/day [V]. |
| Chen et al. 2022, *FEDS*, Sci. Data 9:249 | VIIRS fire objects every 12 h, with fire line and FRP [S]. Closest analogue to our events. |
| Artés et al. 2019, *GlobFire*, Sci. Data 6:296 | MCD64A1 daily perimeters [S]. Independent burned-area truth. |
| Alexandridis et al. 2008, Appl. Math. Comput. 204:191 | Cellular-automaton spread probability (formula below) [V, via Russo et al. 2014]. |

**Alexandridis cellular automaton:**

- p_burn = p0 · (1+p_veg) · (1+p_den) · p_w · p_s
- p_w = exp(c1·V) · exp(V·c2·(cosθ − 1))
- p_s = exp(a·θs)
- Parameters: p0 = 0.58, c1 = 0.045, c2 = 0.131, a = 0.078 per degree.
- The original grid was 5 m; at 375 m, p0 must be recalibrated.

## Semi-empirical spread

**CSIRO grassland** (Cheney, Gould & Catchpole 1998, IJWF 8:1) [V]. Head-fire rate of spread in km/h:

| Wind U10 | Rate of spread |
| --- | --- |
| U < 5 km/h | (0.054 + 0.269·U) · Φ_M · Φ_C |
| U ≥ 5 km/h | (1.4 + 0.838·(U−5)^0.844) · Φ_M · Φ_C |

- Dead fuel moisture: M = 9.58 − 0.205·T + 0.138·RH.
- Moisture factor: Φ_M = exp(−0.108·M) for M ≤ 12.
- Curing factor: Φ_C = 1.036 / (1 + 103.989·exp(−0.0996·(C−20))).
- Length-to-breadth ratio: 1.1·U^0.464.

**Slope:**

- McArthur: R = R0 · exp(0.069·θ°) [V].
- Rothermel slope factor φs = 5.275·β^−0.3·tan²θ [M]. Rothermel fuel models are not calibrated for Indonesian fuels.

**Indonesian FDRS** (Field et al. 2004):

- Drought Code > 350: deep organic layers ignite. DC 700 means burning to 25 cm depth [V].
- FFMC > 82: grass fires spread [S].

## Tropical peat

| Source | Finding |
| --- | --- |
| Usup et al. 2004, Tropics 14:1 | Smouldering spread in Central Kalimantan [V]: surface 3.83 cm/h (≈ 0.9 m/day), deep 1.29 cm/h. Below-ground spread is invisible at 375 m; the spread you can see is surface fire plus new ignitions. |
| Prat-Guitart et al. 2016, IJWF 25:456 | Horizontal spread 1–5 cm/h; extinction at ≈ 115% moisture content [S]. |
| Huang & Rein 2015 | Ignition at ≈ 117% moisture content [S]. |
| Atwood et al. 2016, PLoS ONE | Peat fire fronts > 500 m/day in 2015 [S]. |
| Taufik et al. 2022; Wösten et al. 2008 | High danger when the water table is > 40 cm deep; burns only below 60 cm [S]. |
| Field et al. 2009, Nat. Geosci. | Fire threshold on back-summed rain [V]: Sumatra 631 mm / 5 months, Kalimantan 672 mm / 4 months (≈ 4–5.5 mm/day). |
| Horton et al. 2022, Commun. Earth Environ. | Distance to canals is a key predictor of fire occurrence [V abstract]. |

## Emissions and transport

- **Fire energy to biomass.** Wooster et al. 2005, JGR: 0.368 kg dry matter per MJ of fire radiative energy [V].
- **GFAS conversion factors per land class.** Kaiser et al. 2012, Biogeosciences 9:527 [V]:
  - Peat 5.87 kg/MJ; tropical forest 0.96; savanna 0.78.
  - These absorb the smouldering that MODIS FRP misses.
  - GFAS PM2.5 emission factors: peat 9.1 g/kg, savanna 4.9 g/kg.
- **Peat PM2.5 emission factor.** Wooster et al. 2018: 17.8–22.3 g/kg, mean ≈ 28 [S]. Jayarathne et al. 2018: 17.3 ± 6 [S].
- **Scale of underestimation.** Kiely et al. 2019, ACP: 2015 PM2.5 emissions were ≈ 3.5× the FINN inventory, and peat contributed 71% [S].
- **Injection height.** Sofiev et al. 2012, ACP 12:1995 [V]:
  - Hp = α·H_abl + β·(FRP/P0)^γ · exp(−δ·N²/N0²)
  - α = 0.24, β = 170 m, γ = 0.35, δ = 0.6.
  - Peat smoke mostly stays inside the boundary layer.
- **Puff dispersion.** HYSPLIT (Draxler & Hess, ARL-224) [V]: horizontal puff width grows linearly, dσh/dt = σu. Puffs split when larger than a grid cell.
- **Exposure.**
  - Koplitz et al. 2016, ERL: 100,300 excess deaths in 2015 [S].
  - Kim et al. 2015: Sumatra produced 37% of emissions but 63% of exposure [S].
  - Crippa et al. 2016, Sci. Rep.: 69 million people exposed [S].

## How we use it

| Model | Choice |
| --- | --- |
| Smoke | Hourly puffs per active fire. Mass = FRP × β × EF. Peat: β 5.87 kg/MJ, EF 20 g/kg. Other fires: savanna values 0.78 / 4.9. 850 hPa transport, σh = σ0 + σu·t with σu = 0.7 m/s, 1 km mixing depth, washout when rain > 1 mm/h, 5-day lifetime. Output is an index, not a calibrated concentration; CAMS gives absolute PM2.5. |
| Spread | Stochastic cellular automaton on the 375 m VIIRS grid, 6 h steps, 72 h horizon, Monte Carlo members. Alexandridis wind and slope factors; p0 per fuel class fitted by hindcast; rain suppression; downwind spotting. Validated against persistence and dilated persistence on the 2019/2023 archive using CSI and AUC-PR. |
