#!/usr/bin/env python3
"""Build first-pass global watershed data for the world tab.

This is intentionally a coarse scaffold. It does not yet replace the Europe
builder. It writes global outlet regions into `site/data/global/` so the future
site tab can render a UN-symbol-style global watershed view.
"""

from __future__ import annotations

from pathlib import Path
import io
import json
import zipfile

import geopandas as gpd
import pandas as pd
import requests
import yaml
from shapely.geometry import box

import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))
import make_europe_watershed_map as europe_base  # reuse download URLs + terminal tracing

from projection import project_geometry_mapping

ROOT = Path(__file__).resolve().parents[2]
TAXONOMY_PATH = Path(__file__).with_name("outlet_taxonomy.yml")
GLOBAL_BBOX = (-180.0, -90.0, 180.0, 90.0)

# HydroBASINS global is split by continent. The Europe builder used the EU file;
# global assembly downloads all continental tiles at the chosen level.
HYBAS_CONTINENTS = {
    "af": "Africa",
    "ar": "Arctic",
    "as": "Asia",
    "au": "Australia",
    "eu": "Europe",
    "gr": "Greenland",
    "na": "North America",
    "sa": "South America",
    "si": "Siberia",
}


def hybas_url(continent: str, level: int) -> str:
    return f"https://data.hydrosheds.org/file/hydrobasins/standard/hybas_{continent}_lev{level:02d}_v1c.zip"


def download_zip(url: str, outdir: Path, label: str) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {label}: {url}")
    r = requests.get(url, timeout=240)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        z.extractall(outdir)


def find_first(root: Path, pattern: str) -> Path | None:
    hits = sorted(root.rglob(pattern))
    return hits[0] if hits else None


def load_taxonomy() -> dict:
    with TAXONOMY_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def classify_terminal(lon: float, lat: float, taxonomy: dict) -> str:
    for rule in taxonomy["terminal_bbox_rules"]:
        min_lon, min_lat, max_lon, max_lat = rule["bbox"]
        if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat:
            return rule["class"]
    return "unclassified"


def load_global_hydrobasins(level: int = 5) -> gpd.GeoDataFrame:
    frames = []
    data_root = ROOT / "data" / "global_hydrobasins" / f"lev{level:02d}"
    for code, label in HYBAS_CONTINENTS.items():
        outdir = data_root / code
        shp = find_first(outdir, f"hybas_{code}_lev{level:02d}_v1c.shp")
        if shp is None:
            try:
                download_zip(hybas_url(code, level), outdir, f"HydroBASINS {label} level {level}")
                shp = find_first(outdir, f"hybas_{code}_lev{level:02d}_v1c.shp")
            except Exception as exc:
                print(f"Skipping {label}: {exc}")
                continue
        if shp is None:
            print(f"Skipping {label}: shapefile not found after download")
            continue
        frame = gpd.read_file(shp).to_crs("EPSG:4326")
        frame["continent_tile"] = code
        frames.append(frame)

    if not frames:
        raise RuntimeError("No HydroBASINS tiles loaded")
    gdf = pd.concat(frames, ignore_index=True)
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs="EPSG:4326")
    bbox = gpd.GeoDataFrame(geometry=[box(*GLOBAL_BBOX)], crs="EPSG:4326")
    gdf = gpd.overlay(gdf, bbox, how="intersection", keep_geom_type=True)
    return gdf[~gdf.geometry.is_empty].copy()


def assign_regions(gdf: gpd.GeoDataFrame, taxonomy: dict) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    ids = set(gdf["HYBAS_ID"].astype(int))
    next_down = dict(zip(gdf["HYBAS_ID"].astype(int), gdf["NEXT_DOWN"].fillna(0).astype(int)))
    terminals = {int(i): europe_base.trace_terminal(int(i), next_down, ids) for i in ids}
    reps_by_id = gdf.set_index(gdf["HYBAS_ID"].astype(int)).geometry.representative_point()

    terminal_rows = []
    term_class = {}
    for tid in sorted(set(terminals.values())):
        p = reps_by_id.loc[tid]
        cls = classify_terminal(float(p.x), float(p.y), taxonomy)
        term_class[tid] = cls
        terminal_rows.append({"terminal_id": tid, "lon": float(p.x), "lat": float(p.y), "class_id": cls})

    labels = {k: v["label"] for k, v in taxonomy["classes"].items()}
    colors = {k: v["color"] for k, v in taxonomy["classes"].items()}

    gdf = gdf.copy()
    gdf["terminal_id"] = gdf["HYBAS_ID"].astype(int).map(terminals)
    gdf["class_id"] = gdf["terminal_id"].map(term_class).fillna("unclassified")
    gdf["outlet_region"] = gdf["class_id"].map(labels).fillna("Unclassified / Other")
    gdf["color"] = gdf["class_id"].map(colors).fillna("#999999")
    return gdf, pd.DataFrame(terminal_rows)


def dissolve_regions(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    regions = gdf.dissolve(by=["class_id", "outlet_region", "color"], as_index=False)[
        ["class_id", "outlet_region", "color", "geometry"]
    ]
    return regions


def project_feature_collection(gdf: gpd.GeoDataFrame) -> dict:
    raw = json.loads(gdf.to_json(drop_id=True))
    for feat in raw["features"]:
        feat["geometry"] = project_geometry_mapping(feat["geometry"])
    raw["crs"] = {"type": "name", "properties": {"name": "custom:un_azimuthal_equidistant_north"}}
    return raw


def write_json(obj: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":")), encoding="utf-8")


def main(level: int = 5) -> None:
    taxonomy = load_taxonomy()
    gdf = load_global_hydrobasins(level=level)
    gdf, terminals = assign_regions(gdf, taxonomy)
    regions = dissolve_regions(gdf)

    # Simplify in lon/lat before projecting; first milestone favors load speed.
    regions_simple = regions.copy()
    regions_simple["geometry"] = regions_simple.geometry.simplify(0.08, preserve_topology=True)

    outdir = ROOT / "site" / "data" / "global"
    write_json(project_feature_collection(regions_simple), outdir / "regions_projected.geojson")
    terminals.to_csv(outdir / "outlet_debug_points.csv", index=False)

    # Also write unprojected regions for debugging in QGIS/Leaflet if needed.
    outdir.mkdir(parents=True, exist_ok=True)
    regions.to_file(outdir / "regions_lonlat.geojson", driver="GeoJSON")
    print(f"Built global watershed regions at level {level}: {len(regions)} outlet classes")


if __name__ == "__main__":
    main()
