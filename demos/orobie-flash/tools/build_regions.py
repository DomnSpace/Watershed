#!/usr/bin/env python3
"""Prepare two georeferenced 100 km 3D terrain scenes and independent EFAS depth overlays.

Input DEM(s) must be real raster files supplied by the user. No synthetic elevations
are written to the published data pack. All outputs in EPSG:32632 and metres.

Usage:
  python tools/build_regions.py --region orobie --dem /data/copernicus/*.tif \
      --hazard10 Europe_RP10_filled_depth.tif \
      --hazard100 Europe_RP100_filled_depth.tif \
      --hazard500 Europe_RP500_filled_depth.tif
  python tools/build_regions.py --region euganei --dem /data/veneto/*.tif

Requires numpy, rasterio, pyproj; filenames may be passed multiple times.
Europe-wide EFAS rasters are large: GDAL may perform HTTP range requests from COG
only if the URL supports them. Locally downloaded TIFFs are more reliable.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import rasterio
from rasterio.vrt import WarpedVRT
from rasterio.transform import from_bounds
from rasterio.enums import Resampling
from rasterio.warp import transform
from contextlib import ExitStack

CRS = "EPSG:32632"
SCENES = {
    "orobie": (10.007, 46.040),
    "euganei": (11.687, 45.315),
}
WIDTH_M = 100_000
FOCUS_M = 8_000
SIZE = 512
NODATA = -9999.0

def scene_bounds(lon, lat, size_m):
    x, y = transform("EPSG:4326", CRS, [lon], [lat])
    return (x[0] - size_m/2, y[0] - size_m/2, x[0] + size_m/2, y[0] + size_m/2)

def target(bounds):
    return from_bounds(*bounds, SIZE, SIZE)

def warp_merge(paths, bounds, mode, fill_only=False):
    """Priority mosaic: first valid input wins; no interpolation across NoData.
    Reads via WarpedVRT so a huge source is accessed window-by-window.
    """
    result = np.full((SIZE,SIZE), NODATA, dtype=np.float32)
    coverage = np.zeros((SIZE,SIZE), dtype=bool)
    with ExitStack() as stack:
        sources = [stack.enter_context(rasterio.open(str(p))) for p in paths]
        for ds in sources:
            if ds.crs is None:
                raise ValueError(f"{ds.name}: missing CRS; never assume Fuso 12 is UTM")
            vrt = stack.enter_context(WarpedVRT(
                ds, crs=CRS, transform=target(bounds), width=SIZE, height=SIZE,
                src_nodata=ds.nodata, nodata=NODATA, resampling=mode))
            arr = vrt.read(1, masked=True)
            good = (~np.ma.getmaskarray(arr)) & np.isfinite(arr.data) & (arr.data != NODATA)
            take = good & (~coverage if fill_only else ~coverage)
            result[take] = arr.data[take]
            coverage |= take
    return result, coverage

def write_asc(path, arr, bounds):
    path.parent.mkdir(parents=True,exist_ok=True)
    xmin,ymin,xmax,ymax = bounds
    cell=(xmax-xmin)/SIZE
    if abs((ymax-ymin)/SIZE-cell)>1e-4:
        raise ValueError("target must have square metric pixels")
    with path.open("w",encoding="ascii",newline="\n") as f:
        f.write(f"ncols {SIZE}\nnrows {SIZE}\nxllcorner {xmin:.6f}\nyllcorner {ymin:.6f}\ncellsize {cell:.9f}\nNODATA_value {NODATA}\n")
        np.savetxt(f,arr,fmt="%.5f")

def valid_dem(arr, coverage, label):
    if not coverage.all():
        missing = int((~coverage).sum())
        raise ValueError(f"{label}: {missing} uncovered output cells. Add fallback raster BEFORE exporting; don't invent elevations.")
    if np.max(arr) - np.min(arr) < 2:
        raise ValueError(f"{label}: near-flat or invalid terrain raster")
    if not (-500 < np.min(arr) < 6000 and -500 < np.max(arr) < 6000):
        raise ValueError(f"{label}: implausible elevation range; inspect CRS/vertical units")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--region",choices=[*SCENES,"both"],required=True)
    p.add_argument("--dem",nargs="+",required=True,type=Path,help="ordered priority; first valid raster wins")
    for rp in (10,100,500):
        p.add_argument(f"--hazard{rp}",type=Path,help="EFAS v3.1.1 modeled inundation-depth GeoTIFF")
    p.add_argument("--output",type=Path,default=Path(__file__).resolve().parent.parent/"data")
    a=p.parse_args()
    regions=SCENES if a.region=="both" else {a.region:SCENES[a.region]}
    for region,(lon,lat) in regions.items():
        base=a.output/region
        overview_bounds=scene_bounds(lon,lat,WIDTH_M)
        focus_bounds=scene_bounds(lon,lat,FOCUS_M)
        overview,valid=warp_merge(a.dem,overview_bounds,Resampling.bilinear,fill_only=True)
        valid_dem(overview,valid,region+" overview")
        focus,valid=warp_merge(a.dem,focus_bounds,Resampling.bilinear,fill_only=True)
        valid_dem(focus,valid,region+" focus")
        write_asc(base/"overview.asc",overview,overview_bounds)
        write_asc(base/"focus.asc",focus,focus_bounds)
        has_hazard={}
        for rp in (10,100,500):
            path=getattr(a,f"hazard{rp}")
            if path is None:
                has_hazard[str(rp)]=False
                continue
            depth,coverage=warp_merge([path],overview_bounds,Resampling.nearest)
            # 0 = dry water depth, NoData = not covered. Never fill unavailable data.
            bad=coverage & ((depth < 0) | (depth > 100))
            if bad.any():
                depth[bad]=NODATA
                coverage[bad]=False
            write_asc(base/f"rp{rp}.asc",depth,overview_bounds)
            has_hazard[str(rp)]=True
        manifest={
            "schema":"orobie_flash.terrain_pack.v1",
            "region":region,"center_wgs84":[lon,lat],"crs":CRS,
            "overview_bbox":list(overview_bounds),"focus_bbox":list(focus_bounds),
            "overview_grid":[SIZE,SIZE],"focus_grid":[SIZE,SIZE],
            "elevation_units":"metres",
            "dem_sources":[str(x) for x in a.dem],"flood_sources":{
                str(rp):str(getattr(a,f"hazard{rp}")) if getattr(a,f"hazard{rp}") else None
                for rp in (10,100,500)
            },"flood_years_available":has_hazard,
            "warning":"Static EFAS riverine hazard maps are NOT time-dependent simulation outputs. No RP1000 is supplied."
        }
        (base/"provenance.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
        print(f"{region}: overview and focus {SIZE}², cells {WIDTH_M/SIZE:.3f} m and {FOCUS_M/SIZE:.3f} m; hazard {has_hazard}")
    print("Complete: copy data/<region>/ to the Rust runner's working directory. Do not version huge terrain packs by default.")

if __name__=="__main__":
    main()
