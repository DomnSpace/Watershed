# OROBIE / FLASH — Alpine Hydrology (Rust)

Self-contained native 3D hydrograph and overland runoff visualisation for the **Watershed** repository's independent Rust sidebranch. Designed as a small WetterOnline job-application work sample, not an operational flood warning tool.

## Launch

Requires stable Rust on Windows/macOS/Linux.

```powershell
cd demos/orobie-flash
cargo test --release
cargo run --release
```

Windows downloadable builds are produced by the branch's GitHub Actions workflow, after passing tests. Download the workflow artifact and double-click `orobie_flash.exe`. The included procedural fallback launches without any data download.

## Actual Orobie terrain

The runner deliberately starts with **synthetic, clearly labelled relief** when `data/orobie.asc` is absent. For a real Alpine elevation base:

1. Obtain a properly licensed DEM GeoTIFF that covers Valbondione, Lombardia (e.g. Regione Lombardia DTM 5×5, as available through Geoportale; or Copernicus GLO-30 public).
2. Locally preprocess with Python, rasterio, numpy: `python tools/prepare_dem.py --input path/to/terrain.tif`.
3. Launch the native runner from `demos/orobie-flash`. It then reads `data/orobie.asc` in EPSG:32632 (UTM 32N metres).
4. For a portable Windows distribution, put the `data/orobie.asc` file alongside the executable under `data/`; binary artifact intentionally excludes large geodata.

Default domain: 128×128 cells ×30 m = 3.84×3.84 km near 46.040°N 10.007°E (coordinates are only used in preprocessing). The grid is intentionally small enough for an interactive demo.

## Keys

- Space pause/unpause; R reset deterministic model.
- 1/2/3 change synthetic storm scenarios (broad, local convective, double-peak), resetting the model.
- +/- change peak rain input (mm/h).
- Left/right rotate camera; up/down camera inclination; mouse wheel zoom; C automatic orbit.
- Q toggle visible rainfall streaks.

## Physical model and truth boundaries

- Rain: time-dependent Gaussian pulse with spatial modulation; **fully synthetic**, not radar or ARPA observations.
- Infiltration: illustrative saturation-dependent soil capacity; no calibrated land-cover or soils.
- Routing: 4-connected surface-water gradient driving Manning-style diffusive overland fluxes, explicit donor-volume limiting, no-flow lateral boundaries, open south boundary; fixed 4 s substeps.
- Outputs: water depth field (metres), outlet hydrograph (m³/s), cumulative rain, infiltrated and outflow volumes (m³), mass balance residual.
- Visuals: shaded mesh, contours, animated flux trajectories, storm filaments and deliberately exaggerated water display elevation. Display depth exaggeration is for perceptual clarity, **not metric flood surface geometry**.
- Validation scope: Rust tests check replay determinism, water nonnegativity and approximate discrete volume balance. They do **not** validate peak flow, real-world inundation extent, full Saint-Venant shallow-water dynamics, infiltration rates or hazard thresholds.
- Proper flood-risk analysis would need measured rainfall forcing, stream-gauge calibration, hydrologically conditioned terrain, drainage/conveyance details, appropriate solver, validation, and uncertainty.

## Data links and attribution

- Regione Lombardia DTM 5×5 (2015 edition; metadata lists CC BY 4.0): https://www.geoportale.regione.lombardia.it/
- ARPA Lombardia observed rainfall: https://www.arpalombardia.it/temi-ambientali/meteo-e-clima/form-richiesta-dati/
- HydroBASINS topology: https://www.hydrosheds.org/products/hydrobasins
- Copernicus Digital Elevation Model (alternative DSM, not bare-earth DTM): https://registry.opendata.aws/copernicus-dem/
- Rust rendering: macroquad https://docs.rs/macroquad/latest/macroquad/

This standalone path intentionally leaves the existing Python Europe/global watershed builds and GitHub Pages workflow unchanged.

## Next upgrades before advertising scientific fidelity

(1) Import actual local DEM and verify drainage orientation; (2) represent real catchment boundary and river centerline; (3) integrate ARPA measured precipitation as gridded or station-interpolated forcing; (4) benchmark numerical convergence vs grid and timestep; (5) validate modelled discharge against gauges; (6) capture a reliable one-click Windows build and a 15-second demonstration video or screenshots.
