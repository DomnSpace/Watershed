# Global Watershed Map Plan

Goal: add a second map mode / tab for a whole-world watershed view using a UN-emblem-like polar azimuthal projection, while keeping the current Europe watershed map stable.

> Note: this document is a planning spine. Implementation should happen on a separate branch, e.g. `global-watershed`, before touching the current Pages build.

## 1. Projection target

The visual reference is the projection logic of the United Nations emblem: a north-polar azimuthal view centered on the North Pole, showing the world as a circular field rather than a rectangular Web Mercator map.

Implementation projection candidates:

- `EPSG:3995` / Arctic Polar Stereographic for an initial north-polar web build.
- Custom `+proj=aeqd +lat_0=90 +lon_0=0` azimuthal equidistant for a closer UN-symbol feel.
- Optional later dual view: north-polar and south-polar, or a rotatable globe.

First implementation should be static, robust, and fast:

```text
HydroBASINS global polygons → classify outlet region → dissolve groups → project to polar azimuthal → export GeoJSON/TopoJSON → render in Leaflet/SVG/Canvas tab
```

Because Leaflet normally assumes Web Mercator, the global tab should likely use one of:

1. SVG/Canvas rendering with pre-projected coordinates, or
2. Leaflet with `proj4leaflet`, or
3. d3-geo with `geoAzimuthalEquidistant`.

For the UN-symbol effect, d3-geo is probably the cleanest frontend.

## 2. Data sources

Primary hydrology:

- HydroBASINS global, probably level 5/6 for first world map.
- HydroRIVERS global for river overlay.
- Natural Earth land/ocean/coastlines for background and visual sanity checks.

Potential future upgrades:

- HydroLAKES for large internal lake/sink logic.
- GRDC / major river mouth datasets for debugging outlet identities.
- GEBCO / ETOPO for shaded relief or ocean-basin background.

## 3. Core taxonomy: ocean and sink outlet classes

The global map should not force everything into country or continent blocs. It should classify by common hydrological outlet.

### Primary ocean basins

- Arctic Ocean
- North Atlantic Ocean
- South Atlantic Ocean
- Mediterranean–Black Sea system, optionally split below
- Indian Ocean
- North Pacific Ocean
- South Pacific Ocean
- Southern Ocean

### Major marginal seas / politically-visible hydrological systems

These can be microcategories or toggles depending on visual density:

- Baltic / East Sea
- North Sea
- Irish Sea
- Mediterranean Sea
- Black Sea
- Caspian Sea
- Red Sea
- Persian Gulf
- Arabian Sea
- Bay of Bengal
- South China Sea
- East China Sea / Yellow Sea
- Sea of Japan / East Sea
- Bering Sea
- Hudson Bay
- Gulf of Mexico / Caribbean
- Gulf of California
- Great Lakes / St Lawrence
- Amazon Atlantic
- Congo Atlantic
- Nile Mediterranean

### Endorheic / internal sink regions

These need special treatment, not `Other`:

- Caspian basin
- Aral basin
- Tarim / Lop Nur
- Qaidam / Tibetan internal basins
- Mongolian / Dzungarian internal basins
- Iranian Plateau / Tehran–Central Iran sink
- Dead Sea / Jordan Rift sink
- Lake Chad basin
- Okavango / Kalahari sinks
- Great Basin, western North America
- Altiplano / Titicaca–Poopo system
- Australian internal drainage / Lake Eyre basin
- Sahara internal wadis and chotts
- Antarctic internal/ice marginal drainage, if represented

## 4. First-pass outlet classification strategy

The Europe map currently uses downstream terminal tracing plus local overrides. The global version should separate classification into a data file rather than hard-coded Python boxes.

Proposed structure:

```text
src/global/
  build_global.py
  outlet_taxonomy.yml
  projection.py
  classify_global.py
  debug_outlets.py
site/
  index.html
  data/europe/*
  data/global/*
```

`outlet_taxonomy.yml` should define:

```yaml
classes:
  - id: north_atlantic
    label: North Atlantic Ocean
    color: "#7e68a8"
  - id: arctic
    label: Arctic Ocean
    color: "#9cc9df"
  - id: caspian
    label: Caspian Sea Basin
    color: "#c28b8b"

rules:
  - name: Caspian basin
    if_terminal_bbox: [44, 35, 70.5, 62.5]
    class: caspian
  - name: Baltic basin
    if_terminal_bbox: [9, 53, 32.5, 66.9]
    class: baltic
```

Then local exceptions can be edited without rewriting the builder.

## 5. UI plan

Add a top tab bar:

```text
[Europe watershed] [World watershed]
```

Europe tab:

- Keep current Leaflet map.
- Keep hover highlight behavior.
- Keep HydroBASINS level 7 and current microcategories.

World tab:

- Use circular polar azimuthal map.
- Show ocean/sink basin regions as dissolved colors.
- Hover basin group → highlight rivers in that group.
- Toggle marginal seas on/off:
  - simple mode: major oceans + endorheic sinks
  - detailed mode: marginal seas/micro-basins

## 6. Build workflow plan

Existing Pages workflow can call both builders:

```bash
python src/build_pages.py
python src/global/build_global.py
```

Outputs:

```text
site/data/europe/regions.geojson
site/data/europe/basins.geojson
site/data/europe/rivers.geojson
site/data/global/regions.geojson or .topojson
site/data/global/rivers.geojson or .topojson
site/data/global/outlet_debug_points.csv
```

The first world map should be conservative: HydroBASINS level 5 or 6, simplified aggressively, and possibly TopoJSON later to keep GitHub Pages fast.

## 7. Known difficult regions

These should be expected debugging hotspots:

- Mediterranean / Black Sea / Caspian / Persian Gulf boundary zones.
- Sahara and Arabian internal wadis.
- Tibetan Plateau / Tarim / Ganges / Mekong / Yangtze divides.
- Great Lakes / Hudson Bay / Mississippi / Gulf of Mexico boundary.
- Amazon / Orinoco / La Plata / Pacific Andes.
- Australia: Lake Eyre and coastal basins.
- Antarctica and Greenland: may need a special ice-drainage policy or omission.
- Island arcs and tiny coastal basins, where HydroBASINS terminals become visually noisy.

## 8. First milestone

Milestone 1 should only create the world tab with a coarse but visually coherent map:

- major oceans
- Caspian
- Aral / Central Asia internal
- Lake Chad
- Great Basin
- Lake Eyre
- Iranian Plateau sink
- Mediterranean / Black Sea separated from Atlantic/Indian

Do not optimize every marginal sea at first. The Europe map became good through hover-debugging; the global map should get the same feedback loop.

## 9. Design principle

This is a hydrological counter-map, not a political regionalization map. The priority order is:

```text
actual drainage topology
→ common outlet / sink
→ readable ocean basin grouping
→ marginal sea microcategories
→ political/geographic naming only when helpful
```

Names should never override the drainage field unless the class is explicitly a display aggregation.
