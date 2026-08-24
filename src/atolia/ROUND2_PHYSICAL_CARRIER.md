# Round 2 — physical river / shore carrier

Round 2 changes the *carrier geometry*, not the archaeological selection target.
The generated 300 must never be used as input to this build.

## Data boundary

Runtime/player generation reads only:

`src/atolia/data/physical_carrier_1000.json`

Raw GIS is a developer input and is deliberately not committed. The builder accepts:

1. **HydroRIVERS Europe** — river reaches with `HYRIV_ID`, `NEXT_DOWN`, and geometry.
   `ORD_STRA`, `UPLAND_SKM`, and `DIS_AV_CMS` are used when available.
2. **Natural Earth 1:10m coastline** — mainland and island shoreline geometry. A second
   minor-islands coastline may be supplied with another `--coast` argument.
3. Existing canonical Atolia nodes/edges — names and archaeological/source anchors are
   retained exactly. Old macro edges are *not* used as replacement river geometry; they
   survive only as sparse cross-watershed/pass/open-sea intent constraints.

## Build

```bash
python -m pip install -r requirements-geography.txt
python src/atolia/build_physical_carrier.py \
  --hydrorivers /path/to/HydroRIVERS_v10_eu.shp \
  --coast /path/to/ne_10m_coastline.shp \
  --coast /path/to/ne_10m_minor_islands_coastline.shp \
  --target 1000
python src/atolia/validate_physical_carrier.py
```

After the JSON exists, `physical_geography.install_carrier()` loads it automatically.
Without it, the old dense-geography scaffold remains the explicit fallback and reports
`real_geometry_loaded: false`.

## Compression

The raw GIS can contain tens of thousands of relevant reaches/vertices. We first create
candidate points at river/coast arc-length intervals, while forcibly increasing candidate
importance at mouths, confluences and canonical transfer zones.

For river candidate `v`:

```text
I(v) = 0.80 log(1 + upstream_area)
     + 0.68 log(1 + 10 discharge)
     + 0.82 Strahler_order
     + 1.15 canonical_transfer_proximity
     + role_bonus
```

`role_bonus` is highest for mouths and confluences. Selection is score-first with spatial
repulsion, then spacing is relaxed only if needed to hit the exact node budget. This means
resolution is concentrated at physically meaningful changes instead of uniformly placing
1,000 dots on Europe.

The first committed builder is intentionally conservative: river and coast geometry are
real; pass/portage/sea bridges are inherited as sparse intents from the canonical graph.
A future rebuild can replace those bridge intents with DEM-derived watershed saddles without
changing the runtime schema.

## Edge semantics

* HydroRIVERS reaches: `river_down`, directed.
* Near confluence joins: `river`, bidirectional local coupling.
* Coastline chains: `coast`, bidirectional.
* River mouth -> coastline: `coastal_transfer`.
* Cross-watershed canonical intent: `pass` / `portage`.
* Open-water canonical intent: `sea`.

Round 1's temporal/directional transport model operates on these edges, so Rhine downstream
bias and weak Danube directionality now have a physical graph on which to act.

## Acceptance tests before trusting the carrier

The build is rejected if:

* the total node budget is not exactly 1,000;
* node IDs collide;
* edges reference invalid/degenerate endpoints;
* continental river or shoreline coverage falls below coarse minimums;
* no pass/portage or maritime links survive.

The debug report must additionally be inspected for component structure, macro-region coverage,
and obviously bad canonical attachments. This is a physical-map validation step only. Do not
adjust it because the final 300-object career looks archaeologically inconvenient.

## Important non-goal

Round 2 does **not** attempt to encode exact Bronze Age navigability. HydroRIVERS/Natural Earth
provide the physical manifold. Historical accessibility, direction, object specificity and
period activation belong to the transport fields from Round 1 and later circulation dynamics.
