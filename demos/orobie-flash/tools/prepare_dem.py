#!/usr/bin/env python3
"""Preprocess a locally downloaded elevation GeoTIFF to the Rust runner's metric ESRI ASCII grid.

Example:
  python tools/prepare_dem.py --input /path/to/lombardy_dem.tif

No data is downloaded. Source DEM must cover the centre and target extent.
The target is projected EPSG:32632, not geographic degrees.
"""
import argparse
from pathlib import Path
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject, transform

N = 128

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--center-lon", type=float, default=10.007)
    parser.add_argument("--center-lat", type=float, default=46.040)
    parser.add_argument("--cell-m", type=float, default=30.)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent.parent/"data"/"orobie.asc")
    args = parser.parse_args()
    if args.cell_m < 1 or args.cell_m > 1000:
        raise ValueError("cell metres must be between 1 and 1000")
    cx, cy = transform("EPSG:4326", "EPSG:32632", [args.center_lon], [args.center_lat])
    west = cx[0] - N*args.cell_m/2
    south = cy[0] - N*args.cell_m/2
    east = west + N*args.cell_m
    north = south + N*args.cell_m
    dst_transform = from_bounds(west, south, east, north, N, N)
    dst = np.full((N,N), -9999., dtype=np.float32)
    with rasterio.open(args.input) as ds:
        if ds.crs is None:
            raise ValueError("source raster missing georeferencing/CRS")
        reproject(
            source=rasterio.band(ds, 1), destination=dst,
            src_transform=ds.transform, src_crs=ds.crs,
            dst_transform=dst_transform, dst_crs="EPSG:32632",
            dst_nodata=-9999., resampling=Resampling.bilinear
        )
    if not np.isfinite(dst).all() or np.any(dst == -9999.):
        raise ValueError("DEM does not cover all 3.84 km square or has NoData; obtain better input")
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open("w",encoding="utf-8") as f:
        f.write(f"ncols {N}\nnrows {N}\nxllcorner {west:.6f}\nyllcorner {south:.6f}\ncellsize {args.cell_m:.6f}\nNODATA_value -9999\n")
        np.savetxt(f,dst,fmt="%.4f")
    print(f"Created {args.output} from {args.input}; EPSG:32632, {args.cell_m:.1f}m cells, {N}x{N}")
    print("Scientific limitation: downsampled surface data / conceptual hydraulics, not building-scale flood hazard.")

if __name__ == "__main__":
    main()
