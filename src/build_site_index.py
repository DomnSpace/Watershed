#!/usr/bin/env python3
"""Write the tabbed Pages shell for World + Europe watershed maps."""

from pathlib import Path


def main() -> None:
    site = Path("site")
    site.mkdir(parents=True, exist_ok=True)
    html = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>World and Europe by Watershed</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
html, body { height: 100%; margin: 0; background: #08111a; font-family: system-ui, sans-serif; }
#world, #europe { position: absolute; inset: 0; display: none; }
#world.active, #europe.active { display: block; }
#worldSvg { width: 100%; height: 100%; background: radial-gradient(circle at center, #132538 0%, #08111a 78%); }
#europeMap { height: 100%; background: #122436; }
.tabs { position:absolute; z-index:2000; left:16px; top:16px; display:flex; gap:8px; }
.tabs button { color:#f7fbff; background:rgba(5,10,16,.82); border:1px solid rgba(255,255,255,.22); border-radius:999px; padding:9px 13px; font-weight:700; cursor:pointer; }
.tabs button.active { background:#f7fbff; color:#08111a; }
.panel { position:absolute; z-index:1000; left:16px; top:64px; max-width:430px; color:#f7fbff; background:rgba(5,10,16,.82); backdrop-filter:blur(8px); border:1px solid rgba(255,255,255,.18); border-radius:14px; padding:14px 16px; box-shadow:0 12px 40px rgba(0,0,0,.35); }
.panel h1 { font-size:20px; margin:0 0 6px; }
.panel p { font-size:13px; line-height:1.38; margin:5px 0; color:#d7e7f7; }
.legend { margin-top:10px; display:grid; grid-template-columns: 1fr 1fr; gap:5px 12px; font-size:12px; }
.sw { display:inline-block; width:12px; height:12px; border-radius:3px; margin-right:6px; vertical-align:-2px; }
.status { position:absolute; z-index:1000; left:16px; bottom:18px; color:#f7fbff; background:rgba(5,10,16,.82); border:1px solid rgba(255,255,255,.18); border-radius:12px; padding:10px 12px; min-width:280px; }
.world-region { stroke: rgba(255,255,255,.34); stroke-width: .0024; cursor: pointer; }
.world-region:hover { stroke: #fff; stroke-width: .006; }
.graticule { fill:none; stroke:rgba(255,255,255,.12); stroke-width:.002; pointer-events:none; }
.outerCircle { fill:none; stroke:rgba(255,255,255,.35); stroke-width:.008; pointer-events:none; }
</style>
</head>
<body>
<div class="tabs">
  <button id="tabWorld" class="active">World watershed</button>
  <button id="tabEurope">Europe watershed</button>
</div>

<section id="world" class="active">
  <svg id="worldSvg" viewBox="-3.25 -3.25 6.5 6.5" preserveAspectRatio="xMidYMid meet"></svg>
  <div class="panel">
    <h1>World by Watershed and Common Outlet</h1>
    <p>UN-symbol-style north-polar azimuthal watershed view. First pass: major ocean outlets, marginal seas, and large endorheic sinks.</p>
    <p><b>Basis:</b> global HydroBASINS terminals dissolved by outlet class. This tab is intentionally built for fast iteration.</p>
    <div class="legend" id="worldLegend"></div>
  </div>
  <div class="status" id="worldStatus">Hover a global outlet region.</div>
</section>

<section id="europe">
  <div id="europeMap"></div>
  <div class="panel">
    <h1>Europe by Watershed and Common Outlet</h1>
    <p>No country-label basemap. Macro-regions are dissolved outlet groups; thin inner polygons are individual HydroBASINS level-7 basins.</p>
    <p><b>Basis:</b> HydroBASINS drainage topology + HydroRIVERS/Natural Earth rivers. Rivers are line segments, not zones; basin polygons are the zones.</p>
    <div class="legend" id="europeLegend"></div>
  </div>
  <div class="status" id="europeStatus">Hover a watershed region.</div>
</section>

<script>
const bust = Date.now();
const europeColors = {
 "Mediterranean Europe":"#d98f32", "Black Sea Europe":"#76a95f", "Baltic / East Sea Europe":"#43aebe",
 "North Sea Europe":"#d6b84f", "Atlantic Europe":"#9273b5", "Irish Sea Europe":"#7e68a8", "Polar Europe":"#9cc9df",
 "Caspian Europe":"#c28b8b", "Dardanelles Europe":"#e07a5f", "Tehran / Central Iran Sink":"#d2a15e", "Unclassified / Other":"#999999"
};

function fillLegend(el, entries){
  el.innerHTML = '';
  entries.forEach(([k,v]) => { const d=document.createElement('div'); d.innerHTML=`<span class="sw" style="background:${v}"></span>${k}`; el.appendChild(d); });
}

function showTab(name){
  document.getElementById('world').classList.toggle('active', name==='world');
  document.getElementById('europe').classList.toggle('active', name==='europe');
  document.getElementById('tabWorld').classList.toggle('active', name==='world');
  document.getElementById('tabEurope').classList.toggle('active', name==='europe');
  if(name === 'europe' && window.europeMap){ setTimeout(()=>window.europeMap.invalidateSize(), 50); }
}
document.getElementById('tabWorld').onclick = () => showTab('world');
document.getElementById('tabEurope').onclick = () => showTab('europe');

function pathFromCoords(coords){
  if(!coords || !coords.length) return '';
  return coords.map((p,i)=>`${i?'L':'M'}${p[0]},${p[1]}`).join(' ') + ' Z';
}
function pathForGeometry(geom){
  if(!geom) return '';
  if(geom.type === 'Polygon') return geom.coordinates.map(pathFromCoords).join(' ');
  if(geom.type === 'MultiPolygon') return geom.coordinates.map(poly => poly.map(pathFromCoords).join(' ')).join(' ');
  return '';
}
function drawWorld(){
  const svg = document.getElementById('worldSvg');
  const ns = 'http://www.w3.org/2000/svg';
  const outer = document.createElementNS(ns, 'circle');
  outer.setAttribute('class','outerCircle'); outer.setAttribute('cx','0'); outer.setAttribute('cy','0'); outer.setAttribute('r', String(Math.PI)); svg.appendChild(outer);
  fetch('data/global/regions_projected.geojson?v='+bust).then(r=>r.json()).then(fc=>{
    const legend = new Map();
    fc.features.forEach(f=>{
      const props = f.properties || {};
      const label = props.outlet_region || props.class_id || 'Unclassified';
      const color = props.color || '#999999';
      legend.set(label, color);
      const p = document.createElementNS(ns, 'path');
      p.setAttribute('class','world-region');
      p.setAttribute('d', pathForGeometry(f.geometry));
      p.setAttribute('fill', color);
      p.setAttribute('fill-opacity', '.62');
      p.addEventListener('mouseenter',()=>{p.setAttribute('fill-opacity','.88'); document.getElementById('worldStatus').innerHTML=`<b>${label}</b><br>${props.class_id || ''}`;});
      p.addEventListener('mouseleave',()=>{p.setAttribute('fill-opacity','.62'); document.getElementById('worldStatus').textContent='Hover a global outlet region.';});
      svg.appendChild(p);
    });
    fillLegend(document.getElementById('worldLegend'), [...legend.entries()].sort());
  }).catch(err=>{ document.getElementById('worldStatus').textContent = 'Global data not built yet: ' + err; });
}

function drawEurope(){
  fillLegend(document.getElementById('europeLegend'), Object.entries(europeColors));
  const map = L.map('europeMap', { zoomControl: true }).setView([54, 15], 4);
  window.europeMap = map;
  L.tileLayer('https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png', { attribution: '&copy; OpenStreetMap &copy; CARTO', maxZoom: 10 }).addTo(map);
  let regionLayer, basinLayer, riverLayer;
  let active = null;
  function regionStyle(f){ const c=f.properties.color || europeColors[f.properties.outlet_region] || '#aaa'; const baltic=f.properties.outlet_region==='Baltic / East Sea Europe'; return {color:c, weight:baltic?2.6:1.7, fillColor:c, fillOpacity:baltic?.42:.34}; }
  function basinStyle(f){ const c=f.properties.color || europeColors[f.properties.outlet_region] || '#aaa'; return {color:c, weight:.45, fillColor:c, fillOpacity:.05}; }
  function riverStyle(f){ const on = f.properties.outlet_region === active; return {color:on ? '#0097ff' : '#2b78a0', weight:on ? 2.6 : .45, opacity:on ? .95 : .16}; }
  function setActive(name){ active=name; if(riverLayer) riverLayer.setStyle(riverStyle); if(regionLayer) regionLayer.setStyle(f => { const s=regionStyle(f); if(f.properties.outlet_region===active){s.weight=4; s.fillOpacity=.56;} return s; }); document.getElementById('europeStatus').innerHTML = name ? `<b>${name}</b><br>Rivers and individual basins in this outlet group highlighted.` : 'Hover a watershed region.'; }
  Promise.all([
    fetch('data/europe/regions.geojson?v='+bust).then(r=>r.json()),
    fetch('data/europe/basins.geojson?v='+bust).then(r=>r.json()),
    fetch('data/europe/rivers.geojson?v='+bust).then(r=>r.json())
  ]).then(([regions,basins,rivers])=>{
    basinLayer = L.geoJSON(basins, {style: basinStyle, interactive:false}).addTo(map);
    riverLayer = L.geoJSON(rivers, {style: riverStyle, interactive:false}).addTo(map);
    regionLayer = L.geoJSON(regions, {style: regionStyle, onEachFeature:(f,l)=>{
      l.on('mouseover', ()=>setActive(f.properties.outlet_region));
      l.on('mouseout', ()=>setActive(null));
      l.bindTooltip(f.properties.outlet_region, {sticky:true});
    }}).addTo(map);
    map.fitBounds(regionLayer.getBounds(), {padding:[20,20]});
  }).catch(err=>{ document.getElementById('europeStatus').textContent = 'Europe data not built yet: ' + err; });
}

drawWorld();
drawEurope();
</script>
</body>
</html>
'''
    (site / "index.html").write_text(html, encoding="utf-8")
    print("Wrote tabbed site shell to ./site/index.html")


if __name__ == "__main__":
    main()
