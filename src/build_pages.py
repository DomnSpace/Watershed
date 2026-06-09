#!/usr/bin/env python3
from pathlib import Path
import io
import zipfile

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import box

import make_europe_watershed_map as base
from make_europe_watershed_map_v2 import classify_terminal_v2

HYDRORIVERS_URLS = [
    "https://data.hydrosheds.org/file/HydroRIVERS/HydroRIVERS_v10_eu_shp.zip",
]
NATURAL_EARTH_RIVERS_URL = "https://naturalearth.s3.amazonaws.com/10m_physical/ne_10m_rivers_lake_centerlines.zip"
EUROPE_BBOX = base.EUROPE_BBOX

COLORS = {
    "Mediterranean Europe": "#d98f32",
    "Black Sea Europe": "#76a95f",
    "Baltic / East Sea Europe": "#6fb7c7",
    "North Sea Europe": "#d6b84f",
    "Atlantic Europe": "#9273b5",
    "Irish Sea Europe": "#7e68a8",
    "Polar Europe": "#9cc9df",
    "Caspian Europe": "#c28b8b",
    "Dardanelles Europe": "#e07a5f",
    "Unclassified / Other": "#999999",
}


def download_zip(urls, outdir, label):
    outdir.mkdir(parents=True, exist_ok=True)
    last_err = None
    for url in urls if isinstance(urls, list) else [urls]:
        print(f"Downloading {label}: {url}")
        try:
            r = requests.get(url, timeout=180)
            r.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                z.extractall(outdir)
            return outdir
        except Exception as e:
            last_err = e
            print(f"  failed: {e}")
    raise RuntimeError(f"Could not download {label}: {last_err}")


def find_first(root, pattern):
    hits = sorted(root.rglob(pattern))
    return hits[0] if hits else None


def override_region_for_basin(lon, lat, current):
    """Local corrections using each subbasin's own representative point."""
    # Upper / western Norway: Norwegian Sea / Atlantic margin, not Baltic.
    # Far north stays Polar; the 62-66.7N coastal belt is the visible problem area.
    if 3.0 <= lon <= 20.5 and 61.5 <= lat < 66.7:
        return "Atlantic Europe"
    if 10.0 <= lon <= 31.5 and lat >= 66.7:
        return "Polar Europe"

    # Denmark split: west/central Jutland to North Sea; east Denmark/Zealand/Bornholm to Baltic.
    if 7.7 <= lon <= 10.55 and 54.4 <= lat <= 57.9:
        return "North Sea Europe"
    if 10.55 < lon <= 15.4 and 54.4 <= lat <= 57.9:
        return "Baltic / East Sea Europe"

    # Maas / Meuse basin and lower Scheldt/Rhine-Meuse delta: North Sea.
    # Widened because HydroBASINS representative points can sit inland/south of the obvious channel.
    if 2.4 <= lon <= 8.8 and 47.55 <= lat <= 52.9:
        return "North Sea Europe"

    # Maritsa / Meric / Evros: Aegean / Mediterranean, not Dardanelles or Black Sea.
    if 23.0 <= lon <= 27.6 and 40.1 <= lat <= 42.9:
        return "Mediterranean Europe"

    # Garonne-Dordogne / Bordeaux and Charente: Atlantic.
    if -2.4 <= lon <= 2.0 and 42.85 <= lat <= 46.25:
        return "Atlantic Europe"
    if -2.0 <= lon <= 0.9 and 44.0 <= lat <= 46.95:
        return "Atlantic Europe"

    # Loire: Atlantic, including inland representative points.
    if -4.6 <= lon <= 3.4 and 46.2 <= lat <= 49.05:
        return "Atlantic Europe"

    # Liverpool-Manchester / Mersey-Dee-Irish Sea-facing Britain.
    if -4.4 <= lon <= -1.45 and 52.5 <= lat <= 54.9:
        return "Irish Sea Europe"
    # Cumbria, Solway and Clyde-facing belt.
    if -5.9 <= lon <= -2.8 and 54.4 <= lat <= 56.8:
        return "Irish Sea Europe"

    return current


def build_regions(level=6, channel_as="Atlantic Europe"):
    data = Path("data")
    hybas_dir = data / f"hydrobasins_lev{level}"
    shp = find_first(hybas_dir, f"hybas_eu_lev{level:02d}_v1c.shp")
    if shp is None:
        base.download_zip(base.HYBAS_URLS[level], hybas_dir, f"HydroBASINS Europe level {level}")
        shp = find_first(hybas_dir, f"hybas_eu_lev{level:02d}_v1c.shp")
    if shp is None:
        raise FileNotFoundError("HydroBASINS shapefile not found")

    gdf = gpd.read_file(shp).to_crs("EPSG:4326")
    bbox = gpd.GeoDataFrame(geometry=[box(*EUROPE_BBOX)], crs="EPSG:4326")
    gdf = gpd.overlay(gdf, bbox, how="intersection", keep_geom_type=True)
    gdf = gdf[~gdf.geometry.is_empty].copy()

    ids = set(gdf["HYBAS_ID"].astype(int))
    next_down = dict(zip(gdf["HYBAS_ID"].astype(int), gdf["NEXT_DOWN"].fillna(0).astype(int)))
    terminals = {int(i): base.trace_terminal(int(i), next_down, ids) for i in ids}
    reps_by_id = gdf.set_index(gdf["HYBAS_ID"].astype(int)).geometry.representative_point()

    term_region = {}
    terminal_rows = []
    for tid in set(terminals.values()):
        p = reps_by_id.loc[tid]
        region = classify_terminal_v2(p.x, p.y, channel_as)
        term_region[tid] = region
        terminal_rows.append({"terminal_id": tid, "lon": p.x, "lat": p.y, "outlet_region": region})

    gdf["terminal_id"] = gdf["HYBAS_ID"].astype(int).map(terminals)
    gdf["outlet_region"] = gdf["terminal_id"].map(term_region)

    own_reps = gdf.geometry.representative_point()
    gdf["rep_lon"] = own_reps.x
    gdf["rep_lat"] = own_reps.y
    gdf["outlet_region"] = [
        override_region_for_basin(lon, lat, reg)
        for lon, lat, reg in zip(gdf["rep_lon"], gdf["rep_lat"], gdf["outlet_region"])
    ]

    regions = gdf.dissolve(by="outlet_region", as_index=False)[["outlet_region", "geometry"]]
    regions["color"] = regions["outlet_region"].map(COLORS).fillna("#999999")
    basin_debug = gdf[["HYBAS_ID", "NEXT_DOWN", "terminal_id", "outlet_region", "rep_lon", "rep_lat"]].copy()
    return regions, pd.DataFrame(terminal_rows), basin_debug


def load_hydrorivers():
    data = Path("data") / "hydrorivers_eu"
    shp = find_first(data, "HydroRIVERS_v10_eu.shp") or find_first(data, "*.shp")
    if shp is None:
        download_zip(HYDRORIVERS_URLS, data, "HydroRIVERS Europe")
        shp = find_first(data, "HydroRIVERS_v10_eu.shp") or find_first(data, "*.shp")
    if shp is None:
        raise FileNotFoundError("HydroRIVERS shapefile not found")
    rivers = gpd.read_file(shp).to_crs("EPSG:4326")
    rivers["name"] = ""
    rivers["scalerank"] = 8
    if "ORD_STRA" in rivers.columns:
        rivers["scalerank"] = 10 - rivers["ORD_STRA"].fillna(1).astype(float).clip(1, 9)
    # Keep a dense but not insane river network. This should include Saone-scale tributaries.
    keep = pd.Series(True, index=rivers.index)
    if "ORD_STRA" in rivers.columns:
        keep &= rivers["ORD_STRA"].fillna(0) >= 4
    if "DIS_AV_CMS" in rivers.columns:
        keep |= rivers["DIS_AV_CMS"].fillna(0) >= 20
    if "LENGTH_KM" in rivers.columns:
        keep |= rivers["LENGTH_KM"].fillna(0) >= 35
    rivers = rivers[keep].copy()
    return rivers[["name", "scalerank", "geometry"]]


def load_naturalearth_rivers():
    data = Path("data") / "naturalearth_rivers"
    shp = find_first(data, "ne_10m_rivers_lake_centerlines.shp")
    if shp is None:
        download_zip(NATURAL_EARTH_RIVERS_URL, data, "Natural Earth rivers")
        shp = find_first(data, "ne_10m_rivers_lake_centerlines.shp")
    if shp is None:
        raise FileNotFoundError("Natural Earth rivers shapefile not found")
    rivers = gpd.read_file(shp).to_crs("EPSG:4326")
    rivers["name"] = rivers.get("name", "").fillna("")
    return rivers[["name", "scalerank", "geometry"]]


def build_rivers(regions):
    try:
        rivers = load_hydrorivers()
        river_source = "HydroRIVERS Europe"
    except Exception as e:
        print(f"HydroRIVERS failed, falling back to Natural Earth rivers: {e}")
        rivers = load_naturalearth_rivers()
        river_source = "Natural Earth rivers"

    bbox = gpd.GeoDataFrame(geometry=[box(*EUROPE_BBOX)], crs="EPSG:4326")
    rivers = gpd.overlay(rivers, bbox, how="intersection", keep_geom_type=True)
    rivers = rivers[~rivers.geometry.is_empty].copy()

    clipped = gpd.overlay(rivers, regions[["outlet_region", "geometry"]], how="intersection", keep_geom_type=True)
    clipped = clipped[~clipped.geometry.is_empty].copy()
    clipped["name"] = clipped["name"].fillna("")
    clipped["river_source"] = river_source
    return clipped[["name", "scalerank", "river_source", "outlet_region", "geometry"]]


def write_geojson(gdf, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    out = gdf.copy()
    out["geometry"] = out.geometry.simplify(0.01, preserve_topology=True)
    path.write_text(out.to_json(drop_id=True), encoding="utf-8")


def write_index(site):
    html = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Europe by Watershed and Common Outlet</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
html, body, #map { height: 100%; margin: 0; background: #08111a; }
.panel { position:absolute; z-index:1000; left:16px; top:16px; max-width:420px; color:#f7fbff; background:rgba(5,10,16,.82); backdrop-filter:blur(8px); border:1px solid rgba(255,255,255,.18); border-radius:14px; padding:14px 16px; font-family:system-ui,sans-serif; box-shadow:0 12px 40px rgba(0,0,0,.35); }
.panel h1 { font-size:20px; margin:0 0 6px; }
.panel p { font-size:13px; line-height:1.38; margin:5px 0; color:#d7e7f7; }
.legend { margin-top:10px; display:grid; grid-template-columns: 1fr 1fr; gap:5px 12px; font-size:12px; }
.sw { display:inline-block; width:12px; height:12px; border-radius:3px; margin-right:6px; vertical-align:-2px; }
.status { position:absolute; z-index:1000; left:16px; bottom:18px; color:#f7fbff; background:rgba(5,10,16,.82); border:1px solid rgba(255,255,255,.18); border-radius:12px; padding:10px 12px; font-family:system-ui,sans-serif; min-width:280px; }
.leaflet-container { background: #122436; }
</style>
</head>
<body>
<div id="map"></div>
<div class="panel">
  <h1>Europe by Watershed and Common Outlet</h1>
  <p>Hover a macro-basin: the region and rivers clipped inside it light up together. Dense river layer uses HydroRIVERS when available.</p>
  <p><b>Basis:</b> HydroBASINS drainage topology + HydroRIVERS/Natural Earth rivers. Classification is still an editable policy layer for marginal seas.</p>
  <div class="legend" id="legend"></div>
</div>
<div class="status" id="status">Hover a watershed region.</div>
<script>
const colors = {
 "Mediterranean Europe":"#d98f32", "Black Sea Europe":"#76a95f", "Baltic / East Sea Europe":"#6fb7c7",
 "North Sea Europe":"#d6b84f", "Atlantic Europe":"#9273b5", "Irish Sea Europe":"#7e68a8", "Polar Europe":"#9cc9df",
 "Caspian Europe":"#c28b8b", "Dardanelles Europe":"#e07a5f", "Unclassified / Other":"#999999"
};
const map = L.map('map', { zoomControl: true }).setView([54, 15], 4);
L.tileLayer('https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png', { attribution: '&copy; OpenStreetMap &copy; CARTO', maxZoom: 10 }).addTo(map);
L.tileLayer('https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png', { maxZoom: 10 }).addTo(map);
const legend = document.getElementById('legend');
Object.entries(colors).forEach(([k,v]) => { const d=document.createElement('div'); d.innerHTML=`<span class="sw" style="background:${v}"></span>${k}`; legend.appendChild(d); });
let regionLayer, riverLayer;
let active = null;
function regionStyle(f){ const c=f.properties.color || colors[f.properties.outlet_region] || '#aaa'; return {color:c, weight:1.5, fillColor:c, fillOpacity:.32}; }
function riverStyle(f){ const on = f.properties.outlet_region === active; return {color:on ? '#00a6ff' : '#2b78a0', weight:on ? 2.8 : .55, opacity:on ? .95 : .18}; }
function setActive(name){ active=name; if(riverLayer) riverLayer.setStyle(riverStyle); if(regionLayer) regionLayer.setStyle(f => { const s=regionStyle(f); if(f.properties.outlet_region===active){s.weight=4; s.fillOpacity=.55;} return s; }); document.getElementById('status').innerHTML = name ? `<b>${name}</b><br>Rivers clipped inside this outlet region highlighted.` : 'Hover a watershed region.'; }
Promise.all([fetch('data/regions.geojson').then(r=>r.json()), fetch('data/rivers.geojson').then(r=>r.json())]).then(([regions,rivers])=>{
  riverLayer = L.geoJSON(rivers, {style: riverStyle, interactive:false}).addTo(map);
  regionLayer = L.geoJSON(regions, {style: regionStyle, onEachFeature:(f,l)=>{
    l.on('mouseover', ()=>setActive(f.properties.outlet_region));
    l.on('mouseout', ()=>setActive(null));
    l.bindTooltip(f.properties.outlet_region, {sticky:true});
  }}).addTo(map);
  map.fitBounds(regionLayer.getBounds(), {padding:[20,20]});
});
</script>
</body>
</html>
'''
    (site / "index.html").write_text(html, encoding="utf-8")


def main():
    site = Path("site")
    data = site / "data"
    regions, terminals, basin_debug = build_regions(level=6, channel_as="Atlantic Europe")
    rivers = build_rivers(regions)
    write_geojson(regions, data / "regions.geojson")
    write_geojson(rivers, data / "rivers.geojson")
    terminals.to_csv(data / "terminal_debug_points.csv", index=False)
    basin_debug.to_csv(data / "basin_debug_points.csv", index=False)
    write_index(site)
    print("Built GitHub Pages site in ./site")


if __name__ == "__main__":
    main()
