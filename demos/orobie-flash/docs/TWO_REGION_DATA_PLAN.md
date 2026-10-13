# Orobie + Euganei: two 100 × 100 km real-terrain scenes (data acquisition plan)

Status (2026-10-13): **sources verified; HD datasets and flood rasters not yet downloaded or ingested.** This document contains stable acquisition instructions, not a claim that either scene already renders genuine DEMs.

## Georeferenced areas of interest

Both A0Is are exactly 100,000 m × 100,000 m in a shared local projected reference, EPSG:32632. Bounding coordinates are rounded to the metre. The Veneto *input* DTM may have a different native CRS ("Fuso 12"); reproject using its real georeferencing before cropping and mosaicking.

| scene | lon,lat WGS84 | EPSG:32632 centre (m) | EPSG:32632 bbox (xmin,ymin,xmax,ymax) |
|---|---|---|---|
| `orobie` | 10.0070, 46.0400 | 577918,5098985 | 527918,5048985,627918,5148985 |
| `euganei` | 11.6870,45.3150 | 710612,5021456 | 660612,4971456,760612,5071456 |

The AOIs extend beyond the mountain/park feature; they are *landscape squares*, not catchment boundaries. Orobie 100 km AOI crosses the 10°E data-tile meridian and may extend into Switzerland: blend a uniform-coverage Copernicus base with local Lombardy high-resolution data. The Euganei AOI crosses several drainage systems, including low-lying engineered waterways; delineate flood computations by actual catchment/subcatchment, not arbitrary AOI border.

## Terrain sources — resolution versus actual accuracy

1. **Orobie local high resolution:** Regione Lombardia, *DTM 5X5 - Modello digitale del terreno (ed. 2015)*. 5 m grid; regional topographic database and portions of 1 m LiDAR input. CC BY 4.0. Metadata:
   https://www.geoportale.regione.lombardia.it/en/metadati?_detailSheetMetadata_WAR_gptmetadataportlet_identifier=r_lombar%3Adfc98d60-5f02-4a2b-8113-5ad24cc53a9c&_jsfBridgeRedirect=true&p_p_id=detailSheetMetadata_WAR_gptmetadataportlet&p_p_lifecycle=0&p_p_mode=view&p_p_state=normal
   Downloader: https://www.geoportale.regione.lombardia.it/download-dati
   Optional requested LiDAR where covered (see regional acquisition requirements):
   https://www.geoportale.regione.lombardia.it/consultazione-e-distribuzione
   **Do not use the WMS rendered colors as numeric elevation pixels.** Get actual raster grids from the portal.
2. **Euganei local high resolution:** Regione Veneto 2024 harmonized *DTM derivato da dati LiDAR*, 5 m native grid, where flight coverage exists. Check coverage catalogue `c0101071_Lidar5m`.
   https://idt2.regione.veneto.it/nuovo-dtm-derivato-da-dati-lidar/
   Download by province/municipality: https://idt2.regione.veneto.it/idt/downloader/download
   Published in Veneto 'Fuso 12' projection, custom Italian regional projection; do NOT assume EPSG:32632 or EPSG:7792 without inspecting georeferencing. Fuso 12 background: https://www.regione.veneto.it/web/ambiente-e-territorio/programma-conversione-conve
   Alternative 5 m statewide regional DTM is also on the Veneto download page.
3. **Uniform base/fill:** Copernicus DEM GLO-30 Public COG DSM, ~30 m, includes vegetation and structures.
   https://registry.opendata.aws/copernicus-dem/
   https://copernicus-dem-30m.s3.amazonaws.com/readme.html
   Get the tiles covering each AOI; use only with explicit provenance and observed coverage. In hydrologically critical cells, a DSM is NOT interchangeable with a bare-earth LiDAR DTM.

Data licensing: keep source name, year, resolution, CRS, attribution/license in each tile-pack manifest; do not mix vertical datums without confirming transformations.

## Flood reference: real publicly available inundation depth GeoTIFFs

JRC / Copernicus *Global river flood hazard maps* v2.1.2 (README dated 2026-01-12), depth in metres, 3 arc-second (~90 m), open Copernicus product:
https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/CEMS-GLOFAS/flood_hazard/README.txt

Public return periods: **RP10, RP20, RP50, RP75, RP100, RP200, RP500**.
The file names below are confirmed against the publisher's directory indexes and refer to a broad 10-degree geographic tile, not a clipped local map:
- Veneto + east Orobie: `ID123_N40_E10_RP{T}_depth.tif` in `RP{T}/`
- West Orobie: `ID115_N40_W0_RP{T}_depth.tif` in `RP{T}/`
- Base URL: `https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/CEMS-GLOFAS/flood_hazard/`

Examples (direct raster download):
- RP10 east: https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/CEMS-GLOFAS/flood_hazard/RP10/ID123_N40_E10_RP10_depth.tif
- RP10 west: https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/CEMS-GLOFAS/flood_hazard/RP10/ID115_N40_W0_RP10_depth.tif
- RP100 east: https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/CEMS-GLOFAS/flood_hazard/RP100/ID123_N40_E10_RP100_depth.tif
- RP100 west: https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/CEMS-GLOFAS/flood_hazard/RP100/ID115_N40_W0_RP100_depth.tif
- RP500 east: https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/CEMS-GLOFAS/flood_hazard/RP500/ID123_N40_E10_RP500_depth.tif
- RP500 west: https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/CEMS-GLOFAS/flood_hazard/RP500/ID115_N40_W0_RP500_depth.tif

These JRC data are **modelled riverine maximum depth**, not storm time series, not flash-flood velocity, not measured flood statistics at each point, not an official local PGRA zoning map. They do not resolve small tributaries/urban pluvial floods well. Publisher warns about >10 m spurious depths, artificial DEM sinks, and tile edge artefacts. Use the publisher's `Spurious_Depths` mask and compare official maps; never downplay those limitations.

Local official policy/hydraulic comparison:
- Lombardy/Po PGRA: high 20–50 y, medium 100–200 y, rare 500 y. https://www.regione.lombardia.it/ambiente-e-territorio/pianificazione-territoriale/pianificazione-di-bacino/piano-di-gestione-rischio-alluvioni-nel-bacino-del-fiume-po-pgra
- 2025 Po revision published 2026: https://www.adbpo.it/pubblicate-le-mappe-della-pericolosita-di-alluvioni-del-distretto-po-pgra-2027-2033/
- Veneto/Eastern Alps PGRA: 30/100/300 y, including hydrographs requiring SIGMA registration: https://sigma.distrettoalpiorientali.it/portal/index.php/servizi/dati-terr/idrologia/
- Veneto 2026 updated flood maps adopted: https://sigma.distrettoalpiorientali.it/portal/index.php/2026/01/22/pgra_aggiornamento/
- Lombardy rainfall IDF/LSPP: 2,5,10,20,50,100,200 y, 1–24 h https://idro.arpalombardia.it/manual/lsppdoc.pdf
- Veneto rain depth frequency data/method guidance: https://www.arpa.veneto.it/api/temi-ambientali/meteo/file-e-allegati/le-precipitazioni-di-massima-intensita-annuale_agg-_2023.pdf/%40%40download/file

**RP1000 is NOT included in the public JRC release or these standard official PGRA scenario sets.** A 1000-y flood (annual exceedance probability 0.1% under stationary assumptions) can be an explicitly experimental, highly uncertain extrapolated scenario using extreme-value modelling and defensible hydraulic assumptions, or sourced from licensed data. Fathom commercial RP1000 coverage: https://api-docs.fathom.global/data/dynamic_layers.html

## Planned preparation pipeline (not yet implemented)

1. Ingest official GeoTIFF/ASC coverage polygons and validate CRS + vertical datum, license, nodata and overlaps.
2. Warp terrain to **EPSG:32632** 100 km bboxes, fill only justified voids from Copernicus base; document blending priority and differing resolution/accuracy.
3. Build 256×256 or 257×257 `terrain` tiles, with mip/LOD pyramid (~5,10,20,40,80,160,320 m and farther) and reproducible min/max elevation stats. 5 m full AOI is 20,000×20,000 = 400 million cells/region (1.6 GB float32 uncompressed). Do not send it whole to the GPU.
4. Crop official hazard rasters with nearest-neighbour interpolation for categorical masks; depth layers use documented resampling and preserve nodata/nonflood distinction. Store 10,100,500 separately; do not invent missing depths.
5. Preserve two different displays: (A) **static 10/100/500-year riverine hazard depth snapshots**, and (B) **dynamic modelled rainfall→runoff→water animation**. The first is reference-data visualisation; the second is a scenario. The two only become comparable after calibration.
6. Replace the present 128×128 synthetic domain with hierarchical water simulation: coarser 100km hydrology and focused 2D local inundation tiles (variable resolution, river channels/embankments/bathymetry), with stable timestep and boundary fluxes.
7. Validate all terrain tile seams, hillside hydrology, known stations/river gauges, mass+momentum or suitable governing equations, and camera/near-far clipping.

## Rendering issues documented from first user screenshots

- Barely any continuous visible land surface; debug terrain triangle orientation/backface culling, terrain mesh lighting/depth state, normal calculation, camera target/fit and near/far planes **before** touching water style.
- Current water draws sparse streaks and giant white slivers; water mesh must represent a coherent alpha or opaque depth-aware river surface; decouple water surface height (physical m) from shader displacement used for visual emphasis.
- Peak simulated depths 22–27 m need examination for DEM pits, artificial embankments, fixed dt and boundary handling. Conservation alone does not validate depths; review the erratic outlet hydrograph and donor-limiter-induced pulsing.
- Filmic pass after topology correctness: sun-angled hillshade, ambient shadows, realistic river tint, flow-gradient/motion advected texture, thin reflective highlights, weather radar transparency, camera/storyboard, contrast-correct HUD.

Status: source discovery done; **not** yet a real-terrain port or numerical-validation claim.
