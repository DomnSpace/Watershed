#!/usr/bin/env python3
"""
Build a Europe macro-watershed map from real HydroBASINS polygons.

Output classes:
- Mediterranean Europe
- Black Sea Europe
- Baltic / East Sea Europe
- North Sea Europe
- Atlantic Europe
- Polar Europe
- Caspian / Other

HydroBASINS gives nested catchments and downstream topology. We trace each
subbasin to its terminal downstream basin, classify that terminal outlet by sea
region, then dissolve all polygons by outlet region.
"""
from __future__ import annotations

import argparse
import io
import zipfile
from pathlib import Path
from typing import Dict

import geopandas as gpd
import matplotlib.pyplot as plt
import requests
from shapely.geometry import box

try:
    import rasterio
    from rasterio.plot import show as rioshow
except Exception:
    rasterio = None

HYBAS_URLS = {
    5: "https://data.hydrosheds.org/file/hydrobasins/standard/hybas_eu_lev05_v1c.zip",
    6: "https://data.hydrosheds.org/file/hydrobasins/standard/hybas_eu_lev06_v1c.zip",
    7: "https://data.hydrosheds.org/file/hydrobasins/standard/hybas_eu_lev07_v1c.zip",
}
NE_RELIEF_URLS = [
    "https://naturalearth.s3.amazonaws.com/10m_raster/SR_LR.zip",
    "https://naciscdn.org/naturalearth/10m/raster/SR_LR.zip",
]

EUROPE_BBOX = (-25.5, 33.0, 70.0, 72.5)

COLORS = {
    "Mediterranean Europe": "#d98f32",
    "Black Sea Europe": "#76a95f",
    "Baltic / East Sea Europe": "#6fb7c7",
    "North Sea Europe": "#d6b84f",
    "Atlantic Europe": "#9273b5",
    "Polar Europe": "#9cc9df",
    "Caspian / Other": "#b7b7b7",
}


def download_zip(urls, outdir: Path, label: str) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    last_err = None
    for url in urls if isinstance(urls, list) else [urls]:
        print(f"Downloading {label}: {url}")
        try:
            r = requests.get(url, timeout=120)
            r.raise_for_status()
            z = zipfile.ZipFile(io.BytesIO(r.content))
            z.extractall(outdir)
            print(f"Extracted {label} to {outdir}")
            return outdir
        except Exception as e:
            last_err = e
            print(f"  failed: {e}")
    raise RuntimeError(f"Could not download {label}: {last_err}")


def find_first(root: Path, pattern: str) -> Path | None:
    hits = sorted(root.rglob(pattern))
    return hits[0] if hits else None


def classify_terminal(lon: float, lat: float, channel_as: str = "Atlantic Europe") -> str:
    """Editable policy layer mapping terminal basin position to macro-outlet."""
    if lon >= 44 and lat < 62:
        return "Caspian / Other"

    if 26 <= lon <= 43.8 and 40.0 <= lat <= 48.8:
        return "Black Sea Europe"

    if 9.0 <= lon <= 31.5 and 53.0 <= lat <= 66.7:
        return "Baltic / East Sea Europe"

    if lat >= 66.7:
        return "Polar Europe"
    if lat >= 63.0 and lon >= 20.0:
        return "Polar Europe"
    if lat >= 68.0 and lon >= 10.0:
        return "Polar Europe"

    if -6.5 <= lon <= 37.5 and 34.0 <= lat <= 46.8:
        return "Mediterranean Europe"
    if -3.5 <= lon <= 5.0 and 36.0 <= lat <= 43.5:
        return "Mediterranean Europe"

    if -2.5 <= lon <= 11.5 and 50.0 <= lat <= 62.8:
        return "North Sea Europe"
    if 11.5 < lon <= 13.2 and 53.5 <= lat <= 56.8:
        return "North Sea Europe"

    if -6.5 <= lon <= 2.5 and 48.0 <= lat <= 51.8:
        return channel_as

    if lon <= -2.5 and 35.0 <= lat <= 66.8:
        return "Atlantic Europe"
    if -12.0 <= lon <= 2.5 and 43.0 <= lat <= 53.5:
        return "Atlantic Europe"
    if -25.5 <= lon <= -10.0 and 63.0 <= lat <= 67.5:
        return "Atlantic Europe"

    if 2.0 <= lon <= 20.0 and 58.0 <= lat < 66.7:
        return "Atlantic Europe"

    return "Caspian / Other"


def trace_terminal(hyb_id: int, next_down: Dict[int, int], ids: set[int]) -> int:
    seen = set()
    cur = int(hyb_id)
    while True:
        if cur in seen:
            return cur
        seen.add(cur)
        nxt = int(next_down.get(cur, 0) or 0)
        if nxt == 0 or nxt not in ids:
            return cur
        cur = nxt


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", type=int, default=6, choices=[5, 6, 7])
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--out-dir", default="out")
    ap.add_argument("--channel-as", default="Atlantic Europe", choices=["Atlantic Europe", "North Sea Europe"])
    ap.add_argument("--drop-other", action="store_true")
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    hybas_dir = data_dir / f"hydrobasins_lev{args.level}"
    shp = find_first(hybas_dir, f"hybas_eu_lev{args.level:02d}_v1c.shp")
    if shp is None:
        download_zip(HYBAS_URLS[args.level], hybas_dir, f"HydroBASINS Europe level {args.level}")
        shp = find_first(hybas_dir, f"hybas_eu_lev{args.level:02d}_v1c.shp")
    if shp is None:
        raise FileNotFoundError("HydroBASINS shapefile not found after download")

    relief_dir = data_dir / "naturalearth_relief"
    relief = find_first(relief_dir, "*.tif") or find_first(relief_dir, "*.tiff")
    if relief is None:
        try:
            download_zip(NE_RELIEF_URLS, relief_dir, "Natural Earth shaded relief")
            relief = find_first(relief_dir, "*.tif") or find_first(relief_dir, "*.tiff")
        except Exception as e:
            print(f"Relief download failed; continuing without raster background: {e}")
            relief = None

    print(f"Reading {shp}")
    gdf = gpd.read_file(shp).to_crs("EPSG:4326")
    bbox = gpd.GeoDataFrame(geometry=[box(*EUROPE_BBOX)], crs="EPSG:4326")
    gdf = gpd.overlay(gdf, bbox, how="intersection", keep_geom_type=True)
    gdf = gdf[~gdf.geometry.is_empty].copy()

    required = {"HYBAS_ID", "NEXT_DOWN"}
    missing = required - set(gdf.columns)
    if missing:
        raise ValueError(f"Missing HydroBASINS attributes: {missing}. Columns are {list(gdf.columns)}")

    ids = set(gdf["HYBAS_ID"].astype(int))
    next_down = dict(zip(gdf["HYBAS_ID"].astype(int), gdf["NEXT_DOWN"].fillna(0).astype(int)))
    terminals = {int(i): trace_terminal(int(i), next_down, ids) for i in ids}

    reps = gdf.set_index(gdf["HYBAS_ID"].astype(int)).geometry.representative_point()
    term_region: Dict[int, str] = {}
    for tid in set(terminals.values()):
        p = reps.loc[tid]
        term_region[tid] = classify_terminal(p.x, p.y, args.channel_as)

    gdf["terminal_id"] = gdf["HYBAS_ID"].astype(int).map(terminals)
    gdf["outlet_region"] = gdf["terminal_id"].map(term_region)
    gdf[["HYBAS_ID", "NEXT_DOWN", "terminal_id", "outlet_region"]].to_csv(out_dir / "basin_classification_table.csv", index=False)

    dissolved = gdf.dissolve(by="outlet_region", as_index=False)[["outlet_region", "geometry"]]
    if args.drop_other:
        dissolved = dissolved[dissolved["outlet_region"] != "Caspian / Other"]
    dissolved.to_file(out_dir / "europe_watershed_outlet_regions.gpkg", driver="GPKG")

    fig, ax = plt.subplots(figsize=(16, 11), dpi=220)
    ax.set_xlim(EUROPE_BBOX[0], EUROPE_BBOX[2])
    ax.set_ylim(EUROPE_BBOX[1], EUROPE_BBOX[3])
    ax.set_facecolor("#d7e4eb")

    if relief and rasterio is not None:
        try:
            with rasterio.open(relief) as src:
                rioshow(src, ax=ax, alpha=0.78)
        except Exception as e:
            print(f"Could not draw relief raster: {e}")

    for region, color in COLORS.items():
        sub = dissolved[dissolved["outlet_region"] == region]
        if sub.empty:
            continue
        sub.plot(ax=ax, facecolor=color, edgecolor=color, linewidth=1.4, alpha=0.42 if region != "Caspian / Other" else 0.18)
        sub.boundary.plot(ax=ax, color=color, linewidth=1.3, alpha=0.95)

    for _, row in dissolved.iterrows():
        if row["outlet_region"] == "Caspian / Other":
            continue
        p = row.geometry.representative_point()
        ax.text(p.x, p.y, row["outlet_region"].replace(" / ", "\n"), ha="center", va="center", fontsize=9.5,
                color="#202020", weight="bold", bbox=dict(boxstyle="round,pad=0.22", fc="white", ec="none", alpha=0.62))

    ax.set_title(f"Europe by Watershed and Common Outlet — HydroBASINS level {args.level}", fontsize=18, pad=16)
    ax.text(0.01, 0.01, f"Source: HydroBASINS v1.c + Natural Earth shaded relief. English Channel policy: {args.channel_as}.",
            transform=ax.transAxes, fontsize=8, color="#333", ha="left", va="bottom")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.grid(color="white", alpha=0.25, linewidth=0.5)

    png = out_dir / "europe_watershed_common_outlets.png"
    svg = out_dir / "europe_watershed_common_outlets.svg"
    fig.savefig(png, bbox_inches="tight")
    fig.savefig(svg, bbox_inches="tight")
    print(f"Wrote {png}")
    print(f"Wrote {svg}")
    print(f"Wrote {out_dir / 'europe_watershed_outlet_regions.gpkg'}")


if __name__ == "__main__":
    main()
