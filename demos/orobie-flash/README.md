# WATERSHED / OROBIE + EUGANEI

Native Rust 3D visualisation of **two 100×100 km Italian landscapes**, with a switchable **8×8 km focus**, a conceptual local runoff simulator, and separate modeled EFAS 10/100/500-year river flood-depth reference layers.

**Clearly delimited claims:** the scene *visualises* a georeferenced elevation raster when installed. The built-in rain→runoff approximation is **not a calibrated flood forecast**. EFAS flood-depth maps are **static independently modelled hazard rasters**, not outputs of the local simulation.

## One-click application

The Windows CI downloads a working `orobie_flash.exe` build into artifact `OROBIE-FLASH-windows-x64`.
Extract and double-click from its folder. Without additional data, the two landscapes are **visibly labelled procedural stand-ins**, and RP hazard overlays say "NOT INSTALLED". There are no invented official hazard maps.

From source:

```powershell
cd demos/orobie-flash
cargo test --release
cargo run --release
```

## Acquire both real 100 km scenes (Copernicus 30 m DSM)

Requires Python 3.11+, internet, several hundred MB of disk space and a few minutes:
```powershell
py -m pip install numpy rasterio pyproj boto3 requests
py tools/fetch_inputs.py --region both --dem
$dem = @(Get-ChildItem raw_inputs/dem -Recurse -Filter *.tif | Select-Object -ExpandProperty FullName)
py tools/build_regions.py --region orobie --dem $dem
py tools/build_regions.py --region euganei --dem $dem
cargo run --release
```

The downloader accesses anonymous public AWS `copernicus-dem-30m` S3 tiles and falls back to public 90 m tiles where necessary. It lists exact S3 objects by 1×1-degree geographic tile to avoid guessing filenames. Real data are not bundled in GitHub because of size. All source GeoTIFFs must include valid native CRS/georeferencing.

**Higher resolution:** first acquire regional 5 m *bare-earth DTM* coverage in Lombardia and Veneto (see `docs/TWO_REGION_DATA_PLAN.md`). Pass these georeferenced raster paths **before** the downloaded Copernicus paths via `--dem`. The builder uses the first valid source in each cell. Veneto "Fuso 12" must have its actual native CRS in the raster: never assign EPSG:32632 by assumption.

Terrain samples written to `data/orobie/` and `data/euganei/`:
- `overview.asc`: 512×512, exactly 100 km, EPSG:32632, 195.3125 m render cells;
- `focus.asc`: 512×512, exactly 8 km, EPSG:32632, 15.625 m render cells;
- `provenance.json`: machine-readable source list and study-area coordinates.
If underlying DEM is 30 m, the 15.625 m local rendering samples are *interpolated*. They add NO extra terrain measurement detail.

The **local simulated flow** uses a separate 128×128 finite-volume-like approximation, 62.5 m cells over the focus, independent of static 100 km hazard maps.

### Load modeled flood reference (RP10, RP100, RP500)

Optional data transfer is large (~900 MB total Europe-wide TIFFs). You may fetch only RP10 first:
```powershell
py tools/fetch_inputs.py --efas 10 100 500
py tools/build_regions.py --region orobie --dem $dem \
    --hazard10 raw_inputs/efas/Europe_RP10_filled_depth.tif \
    --hazard100 raw_inputs/efas/Europe_RP100_filled_depth.tif \
    --hazard500 raw_inputs/efas/Europe_RP500_filled_depth.tif
py tools/build_regions.py --region euganei --dem $dem \
    --hazard10 raw_inputs/efas/Europe_RP10_filled_depth.tif \
    --hazard100 raw_inputs/efas/Europe_RP100_filled_depth.tif \
    --hazard500 raw_inputs/efas/Europe_RP500_filled_depth.tif
```
**PowerShell note:** use each long `py` command on **one physical line**; the multiline formatting above is conceptual. PowerShell continuation uses backticks, not backslashes.

Copernicus EMS EFAS v3.1.1 (March 2026), 3 arc-second (~90 m), modelled riverine inundation depth in metres; not urban surface runoff, pluvial flash-flood velocity or measured time series:
https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/CEMS-EFAS/flood_hazard/README.txt

**No RP1000** is sourced by EFAS or GloFAS. A 1000-year scene requires clearly labelled extreme-value extrapolation or a separately licensed validated layer; it is intentionally absent.

## Controls

| Key | Action |
|---|---|
| `M` | Switch Orobie ↔ Euganei |
| `V` | 100 km overview ↔ 8 km local focus |
| `0` / `4` | Explicit overview / focus |
| `H` | Cycle **static** 10/100/500-year EFAS depth overlays in overview (if installed) |
| `1` / `2` / `3` | Switch synthetic *storm* scenarios (independent of EFAS return periods) |
| Space / `R` | Pause / reset conceptual runoff |
| `+` / `-` | Synthetic rain rate |
| `Q` / `F` | Visible rain streaks / live water-flow glints |
| Arrows / wheel / `C` | Orbit and inclination / zoom / toggle slow orbit |

The renderer uses 64×64 surface mesh tiles with software sun shading, physically scaled depth offsets and opaque contiguous water, avoiding the previous transparent depth-sort holes, ghostly white slivers and sparse dotted-water mesh. **Graphics need visual inspection on a real Windows GPU after this code change**; CI verifies compilation/tests, not screenshots or subjective look.

## Numerical limitations and testing

The interactive local model integrates stylized rain, soil wetting, rainfall loss and depth-gradient-directed Manning-like donor-limited 4-neighbour transfer. It conserves modeled water to a numerical tolerance and provides a hydrograph at an open south boundary. This is not LISFLOOD-FP, a 2-D Saint-Venant hydraulic solution, a calibrated storm drain network or a hydrologically conditioned terrain model. Model depth spikes and downstream pulse oscillation are known limitations requiring further solver, timestep, and inlet/outlet validation. No official flood hazard level or return period should be inferred from changing storm intensity.

Reproducibility:
```powershell
cargo test --release
py tools/test_regions.py
```

## Original data and attribution

- Regione Lombardia DTM 5×5 (local portions may have LiDAR): https://www.geoportale.regione.lombardia.it/download-dati
- Regione Veneto 2024 LiDAR-derived DTM 5 m (partial coverage, native Fuso 12): https://idt2.regione.veneto.it/nuovo-dtm-derivato-da-dati-lidar/
- Copernicus DEM GLO-30 **DSM**, Copernicus 2021 release, public anonymous S3: https://registry.opendata.aws/copernicus-dem/
- EFAS European river flood hazard maps v3.1.1, EU Copernicus EMS, released 2026-03-05: https://doi.org/10.2905/1D128B6C-A4EE-4858-9E34-6210707F3C81
- Local authority PGRA, rainfall intensity-duration-frequency studies, gauge comparisons and uncertainties: see `docs/TWO_REGION_DATA_PLAN.md`.

The branch intentionally leaves the main Watershed Python/Pages code unchanged.
