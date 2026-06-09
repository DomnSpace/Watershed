#!/usr/bin/env python3
from pathlib import Path
import io
import json
import zipfile

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import box

import make_europe_watershed_map as base
from make_europe_watershed_map_v2 import classify_terminal_v2

RIVERS_URL = "https://naturalearth.s3.amazonaws.com/10m_physical/ne_10m_rivers_lake_centerlines.zip"
EUROPE_BBOX = base.EUROPE_BBOX

COLORS = {
    "Mediterranean Europe": "#d98f32",
    "Black Sea Europe": "#76a95f",
    "Baltic / East Sea Europe": "#6fb7c7",
    "North Sea Europe": "#d6b84f",
    "Atlantic Europe": "#9273b5",
    "Polar Europe": "#9cc9df",
    "Caspian Europe": "#c28b8b",
    "Unclassified / Other": "#999999",
}


def download_zip(url, outdir, label):
    outdir.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {label}: {url}")
    r = requests.get(url, timeout=180)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        z.extractall(outdir)


def find_first(root, pattern):
    hits = sorted(root.rglob(pattern))
    return hits[0] if hits else None


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
    reps = gdf.set_index(gdf["HYBAS_ID"].astype(int)).geometry.representative_point()

    term_region = {}
    terminal_rows = []
    for tid in set(terminals.values()):
        p = reps.loc[tid]
        region = classify_terminal_v2(p.x, p.y, channel_as)
        term_region[tid] = region
        terminal_rows.append({"terminal_id": tid, "lon": p.x, "lat": p.y, "outlet_region": region})

    gdf["terminal_id"] = gdf["HYBAS_ID"].astype(int).map(terminals)
    gdf["outlet_region"] = gdf["terminal_id"].map(term_region)
    regions = gdf.dissolve(by="outlet_region", as_index=False)[["outlet_region", "geometry"]]
    regions["color"] = regions["outlet_region"].map(COLORS).fillna("#999999")
    return regions, pd.DataFrame(terminal_rows)


def build_rivers(regions):
    data = Path("data") / "naturalearth_rivers"
    shp = find_first(data, "ne_10m_rivers_lake_centerlines.shp")
    if shp is None:
        download_zip(RIVERS_URL, data, "Natural Earth rivers")
        shp = find_first(data, "ne_10m_rivers_lake_centerlines.shp")
    rivers = gpd.read_file(shp).to_crs("EPSG:4326")
    bbox = gpd.GeoDataFrame(geometry=[box(*EUROPE_BBOX)], crs="EPSG:4326")
    rivers = gpd.overlay(rivers, bbox, how="intersection", keep_geom_type=True)
    rivers = rivers[~rivers.geometry.is_empty].copy()

    join = gpd.sjoin(
        rivers[["name", "scalerank", "geometry"]],
        regions[["outlet_region", "geometry"]],
        how="inner",
        predicate="intersects",
    )
    join = join.drop(columns=[c for c in ["index_right"] if c in join.columns])
    join["name"] = join["name"].fillna("")
    return join


def write_geojson(gdf, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Keep files compact enough for Pages.
    out = gdf.copy()
    out["geometry"] = out.geometry.simplify(0.015, preserve_topology=True)
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
  <p>Hover a macro-basin: the region and its rivers light up together. This is the fast correction loop: if a basin is misclassified, the rivers make the error visible.</p>
  <p><b>Basis:</b> HydroBASINS drainage topology + Natural Earth rivers. Classification is still an editable policy layer for marginal seas.</p>
  <div class="legend" id="legend"></div>
</div>
<div class="status" id="status">Hover a watershed region.</div>
<script>
const colors = {
 "Mediterranean Europe":"#d98f32", "Black Sea Europe":"#76a95f", "Baltic / East Sea Europe":"#6fb7c7",
 "North Sea Europe":"#d6b84f", "Atlantic Europe":"#9273b5", "Polar Europe":"#9cc9df",
 "Caspian Europe":"#c28b8b", "Unclassified / Other":"#999999"
};
const map = L.map('map', { zoomControl: true }).setView([54, 15], 4);
L.tileLayer('https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png', { attribution: '&copy; OpenStreetMap &copy; CARTO', maxZoom: 10 }).addTo(map);
L.tileLayer('https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png', { maxZoom: 10 }).addTo(map);
const legend = document.getElementById('legend');
Object.entries(colors).forEach(([k,v]) => { const d=document.createElement('div'); d.innerHTML=`<span class="sw" style="background:${v}"></span>${k}`; legend.appendChild(d); });
let regionLayer, riverLayer;
let active = null;
function regionStyle(f){ const c=f.properties.color || colors[f.properties.outlet_region] || '#aaa'; return {color:c, weight:1.5, fillColor:c, fillOpacity:.32}; }
function riverStyle(f){ const on = f.properties.outlet_region === active; return {color:on ? '#00a6ff' : '#2b78a0', weight:on ? 3.5 : .8, opacity:on ? .95 : .22}; }
function setActive(name){ active=name; if(riverLayer) riverLayer.setStyle(riverStyle); if(regionLayer) regionLayer.setStyle(f => { const s=regionStyle(f); if(f.properties.outlet_region===active){s.weight=4; s.fillOpacity=.55;} return s; }); document.getElementById('status').innerHTML = name ? `<b>${name}</b><br>Rivers in this outlet region highlighted.` : 'Hover a watershed region.'; }
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
    regions, terminals = build_regions(level=6, channel_as="Atlantic Europe")
    rivers = build_rivers(regions)
    write_geojson(regions, data / "regions.geojson")
    write_geojson(rivers, data / "rivers.geojson")
    terminals.to_csv(data / "terminal_debug_points.csv", index=False)
    write_index(site)
    print("Built GitHub Pages site in ./site")


if __name__ == "__main__":
    main()
