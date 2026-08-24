#!/usr/bin/env python3
from __future__ import annotations

"""Build the compact ~1000-node archaeology carrier from real hydrography/shorelines.

This is a DEVELOPER BUILD TOOL, not a player-runtime dependency.

Inputs
------
* HydroRIVERS Europe shapefile/GeoPackage with HYRIV_ID, NEXT_DOWN and geometry.
  Optional attributes used when present: ORD_STRA, UPLAND_SKM, DIS_AV_CMS.
* Natural Earth 1:10m coastline (and optionally minor-islands coastline).
* The existing Atolia canonical graph, which supplies hypothesis anchors and the
  handful of cross-watershed/pass/open-sea connection intents that physical river
  topology alone cannot infer.

Output
------
src/atolia/data/physical_carrier_1000.json

The output contains only a compressed derived graph. Raw GIS data is deliberately
not vendored and is never required when generating a player career.
"""

import argparse
import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import provenance_field as base
import provenance_field_mediterranean as med

try:
    import geopandas as gpd
    from shapely.geometry import LineString, MultiLineString, Point, box
    from shapely.ops import nearest_points
except Exception as exc:  # pragma: no cover - developer dependency only
    gpd = None
    _GIS_IMPORT_ERROR = exc
else:
    _GIS_IMPORT_ERROR = None


SCHEMA = "atolia.physical-carrier.v2"
BUILD_VERSION = "physical-carrier-builder-v2"
DEFAULT_TARGET = 1000
DEFAULT_BBOX = (-12.5, 30.0, 43.5, 59.5)

# This is a node budget, not an asserted archaeological frequency distribution.
DEFAULT_BUDGET = {
    "river": 440,
    "coast": 190,
    "mouth_estuary": 80,
    "island_strait": 70,
    "pass_portage": 70,
    "adaptive": 150,
}

MODE_COST_PER_KM = {
    "river_down": .74,
    "river_up": 1.10,
    "river": .90,
    "coast": .92,
    "coastal_transfer": .98,
    "sea": 1.02,
    "pass": 1.24,
    "portage": 1.32,
    "plain": 1.08,
    "bridge": 1.10,
}


@dataclass
class Candidate:
    cid: str
    lon: float
    lat: float
    kind: str
    region: str
    score: float
    source: str
    source_feature_id: str = ""
    river_order: float = 0.0
    upstream_area_km2: float = 0.0
    discharge_m3s: float = 0.0
    role: str = "sample"


def require_gis() -> None:
    if gpd is None:
        raise RuntimeError(
            "Carrier building needs geopandas/shapely. Install requirements-geography.txt. "
            f"Import error: {_GIS_IMPORT_ERROR}"
        )


def haversine(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    return base.haversine_km(lon1, lat1, lon2, lat2)


def classify_region(lon: float, lat: float) -> str:
    """Coarse transport macro-region used only as a field prior label."""
    if 8.0 <= lon <= 14.5 and 44.0 <= lat <= 47.8:
        return "atolia_core"
    if 4.0 <= lon <= 10.5 and 46.0 <= lat <= 54.5:
        return "rhine"
    if 2.0 <= lon <= 7.5 and 42.0 <= lat <= 48.5:
        return "rhone"
    if lon < 2.5 and lat >= 48.0:
        return "severn_britain"
    if 14.0 <= lon <= 31.0 and 43.0 <= lat <= 50.5:
        return "lower_danube"
    if 18.0 <= lon <= 29.5 and 35.0 <= lat < 43.5:
        return "aegean"
    if 23.0 <= lon <= 27.5 and 34.0 <= lat <= 36.3:
        return "crete"
    if 32.0 <= lon <= 35.5 and 34.0 <= lat <= 36.5:
        return "cyprus"
    if 25.0 <= lon <= 32.5 and 36.0 <= lat <= 41.5:
        return "western_anatolia"
    if lon >= 32.0 and lat <= 35.8:
        return "levant_egypt"
    if -6.0 <= lon < 8.5 and lat < 44.5:
        return "western_mediterranean"
    if 8.5 <= lon < 18.5 and lat < 44.5:
        return "central_mediterranean"
    return "other"


def _field_gradient_proxy(lon: float, lat: float, canonical_nodes: Mapping[str, Any]) -> float:
    """Resolution booster near canonical/cross-system transfer zones.

    This is intentionally geometry-only. It does not look at generated finds.
    """
    ds = sorted(
        haversine(lon, lat, n.lon, n.lat) for n in canonical_nodes.values()
    )[:3]
    if not ds:
        return 0.0
    return float(sum(math.exp(-d / 180.0) for d in ds))


def _river_candidate_score(order: float, area: float, discharge: float, role: str,
                           lon: float, lat: float, canonical_nodes: Mapping[str, Any]) -> float:
    score = (
        .80 * math.log1p(max(0.0, area))
        + .68 * math.log1p(max(0.0, discharge) * 10.0)
        + .82 * max(0.0, order)
        + 1.15 * _field_gradient_proxy(lon, lat, canonical_nodes)
    )
    if role == "mouth":
        score += 5.0
    elif role == "confluence":
        score += 4.0
    elif role == "order_change":
        score += 2.2
    return score


def _iter_lines(geom: Any) -> Iterable[Any]:
    if geom is None or geom.is_empty:
        return
    if geom.geom_type == "LineString":
        yield geom
    elif geom.geom_type == "MultiLineString":
        yield from geom.geoms


def load_hydrorivers(path: Path, bbox_wgs84: Sequence[float]) -> Any:
    require_gis()
    gdf = gpd.read_file(path).to_crs("EPSG:4326")
    required = {"HYRIV_ID", "NEXT_DOWN"}
    missing = required - set(gdf.columns)
    if missing:
        raise ValueError(f"HydroRIVERS missing required columns {sorted(missing)}")
    clip = box(*bbox_wgs84)
    gdf = gdf[gdf.geometry.intersects(clip)].copy()
    return gdf


def load_coast(paths: Sequence[Path], bbox_wgs84: Sequence[float]) -> Any:
    require_gis()
    frames = []
    clip = box(*bbox_wgs84)
    for path in paths:
        g = gpd.read_file(path).to_crs("EPSG:4326")
        g = g[g.geometry.intersects(clip)].copy()
        frames.append(g[["geometry"]])
    if not frames:
        raise ValueError("At least one coastline dataset is required")
    import pandas as pd
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")


def river_candidates(gdf: Any, canonical_nodes: Mapping[str, Any], spacing_km: float = 32.0) -> Tuple[List[Candidate], Dict[int, List[str]]]:
    """Extract confluences/mouths plus arc-length samples from HydroRIVERS reaches."""
    by_id = {int(row.HYRIV_ID): row for _, row in gdf.iterrows()}
    upstream: Dict[int, List[int]] = defaultdict(list)
    for rid, row in by_id.items():
        nxt = int(getattr(row, "NEXT_DOWN", 0) or 0)
        if nxt in by_id:
            upstream[nxt].append(rid)

    candidates: List[Candidate] = []
    reach_nodes: Dict[int, List[str]] = {}
    for rid, row in by_id.items():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        order = float(getattr(row, "ORD_STRA", 0.0) or 0.0)
        area = float(getattr(row, "UPLAND_SKM", 0.0) or 0.0)
        discharge = float(getattr(row, "DIS_AV_CMS", 0.0) or 0.0)
        parts = list(_iter_lines(geom))
        if not parts:
            continue
        line = max(parts, key=lambda x: x.length)
        # Use an approximate geodesic length for budget spacing.
        coords = list(line.coords)
        km = sum(haversine(a[0], a[1], b[0], b[1]) for a, b in zip(coords[:-1], coords[1:]))
        n = max(1, int(math.ceil(km / spacing_km)))
        ids: List[str] = []
        for i in range(n + 1):
            f = i / n
            p = line.interpolate(f, normalized=True)
            nxt = int(getattr(row, "NEXT_DOWN", 0) or 0)
            role = "sample"
            if i == n and nxt == 0:
                role = "mouth"
            elif i == 0 and len(upstream.get(rid, [])) >= 2:
                role = "confluence"
            cid = f"hr_{rid}_{i:02d}"
            score = _river_candidate_score(order, area, discharge, role, p.x, p.y, canonical_nodes)
            candidates.append(Candidate(
                cid=cid, lon=float(p.x), lat=float(p.y), kind="river",
                region=classify_region(p.x, p.y), score=score, source="HydroRIVERS",
                source_feature_id=str(rid), river_order=order, upstream_area_km2=area,
                discharge_m3s=discharge, role=role,
            ))
            ids.append(cid)
        reach_nodes[rid] = ids
    return candidates, reach_nodes


def coast_candidates(gdf: Any, canonical_nodes: Mapping[str, Any], spacing_km: float = 38.0) -> Tuple[List[Candidate], Dict[str, List[str]]]:
    candidates: List[Candidate] = []
    chains: Dict[str, List[str]] = {}
    feature_no = 0
    for _, row in gdf.iterrows():
        for line in _iter_lines(row.geometry):
            feature_no += 1
            coords = list(line.coords)
            km = sum(haversine(a[0], a[1], b[0], b[1]) for a, b in zip(coords[:-1], coords[1:]))
            if km < 8:
                continue
            n = max(1, int(math.ceil(km / spacing_km)))
            ids = []
            for i in range(n + 1):
                f = i / n
                p = line.interpolate(f, normalized=True)
                # Coast importance is driven by geometry resolution and proximity to
                # transfer anchors, not by archaeological finds.
                score = 2.0 + 1.35 * _field_gradient_proxy(p.x, p.y, canonical_nodes)
                cid = f"ne_coast_{feature_no:04d}_{i:03d}"
                candidates.append(Candidate(
                    cid=cid, lon=float(p.x), lat=float(p.y), kind="coast",
                    region=classify_region(p.x, p.y), score=score, source="NaturalEarth",
                    source_feature_id=str(feature_no), role="coast_sample",
                ))
                ids.append(cid)
            chains[str(feature_no)] = ids
    return candidates, chains


def deduplicate(candidates: Sequence[Candidate], radius_km: float = 5.0) -> List[Candidate]:
    """Greedy score-first spatial deduplication; deterministic and dependency-light."""
    kept: List[Candidate] = []
    for c in sorted(candidates, key=lambda x: (-x.score, x.cid)):
        if all(haversine(c.lon, c.lat, k.lon, k.lat) >= radius_km for k in kept):
            kept.append(c)
    return kept


def select_budget(candidates: Sequence[Candidate], target: int, canonical_count: int) -> List[Candidate]:
    available = max(0, int(target) - int(canonical_count))
    if available <= 0:
        return []
    mandatory = [c for c in candidates if c.role in {"mouth", "confluence"}]
    optional = [c for c in candidates if c.role not in {"mouth", "confluence"}]
    mandatory = deduplicate(mandatory, 4.0)
    optional = deduplicate(optional, 7.0)
    selected = mandatory[:available]
    remaining = available - len(selected)
    if remaining > 0:
        selected.extend(optional[:remaining])
    if len(selected) < available:
        # Relax spacing only to hit the exact runtime carrier budget.
        selected_ids = {c.cid for c in selected}
        for c in sorted(candidates, key=lambda x: (-x.score, x.cid)):
            if c.cid not in selected_ids:
                selected.append(c); selected_ids.add(c.cid)
                if len(selected) == available:
                    break
    return selected[:available]


def nearest_candidate(node: Any, candidates: Sequence[Candidate], kinds: set[str] | None = None) -> Candidate:
    pool = [c for c in candidates if kinds is None or c.kind in kinds]
    if not pool:
        raise ValueError("No carrier candidates available for canonical attachment")
    return min(pool, key=lambda c: haversine(node.lon, node.lat, c.lon, c.lat))


def _edge_cost(km: float, mode: str) -> float:
    return max(.001, km * MODE_COST_PER_KM.get(mode, 1.08))


def build_edges(selected: Sequence[Candidate], canonical_nodes: Mapping[str, Any], canonical_edges: Sequence[Any]) -> List[Dict[str, Any]]:
    """Build local physical chains, canonical attachments, and sparse bridge intents."""
    by_id = {c.cid: c for c in selected}
    by_feature: Dict[Tuple[str, str], List[Candidate]] = defaultdict(list)
    for c in selected:
        by_feature[(c.source, c.source_feature_id)].append(c)

    edges: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str, str]] = set()

    def add(a: str, b: str, mode: str, directed: bool = False, meta: Mapping[str, Any] | None = None) -> None:
        if a == b:
            return
        key = (a, b, mode) if directed else tuple(sorted((a, b))) + (mode,)
        if key in seen:
            return
        seen.add(key)
        if a in canonical_nodes:
            na = canonical_nodes[a]
            lon_a, lat_a = na.lon, na.lat
        else:
            ca = by_id[a]; lon_a, lat_a = ca.lon, ca.lat
        if b in canonical_nodes:
            nb = canonical_nodes[b]
            lon_b, lat_b = nb.lon, nb.lat
        else:
            cb = by_id[b]; lon_b, lat_b = cb.lon, cb.lat
        km = haversine(lon_a, lat_a, lon_b, lat_b)
        item = {"a": a, "b": b, "mode": mode, "cost": _edge_cost(km, mode), "directed": directed}
        if meta:
            item.update(meta)
        edges.append(item)

    # Connect retained points from the same HydroRIVERS reach in their geometric order.
    for (source, fid), points in by_feature.items():
        if len(points) < 2:
            continue
        # cid suffixes encode along-feature order for both river and coast candidates.
        points = sorted(points, key=lambda c: c.cid)
        mode = "river_down" if source == "HydroRIVERS" else "coast"
        for a, b in zip(points[:-1], points[1:]):
            add(a.cid, b.cid, mode, directed=(source == "HydroRIVERS"), meta={
                "source_feature_id": fid,
                "river_order": a.river_order if source == "HydroRIVERS" else 0.0,
                "upstream_area_km2": a.upstream_area_km2 if source == "HydroRIVERS" else 0.0,
                "discharge_m3s": a.discharge_m3s if source == "HydroRIVERS" else 0.0,
            })

    # Join nearby endpoints/confluences across different retained river reaches.
    rivers = [c for c in selected if c.kind == "river"]
    for c in rivers:
        nearby = sorted(
            (haversine(c.lon, c.lat, d.lon, d.lat), d)
            for d in rivers if d.source_feature_id != c.source_feature_id
        )[:4]
        for km, d in nearby:
            if km <= 7.5 and (c.role in {"mouth", "confluence"} or d.role in {"mouth", "confluence"}):
                add(c.cid, d.cid, "river", directed=False)

    # Explicitly couple river mouths to nearby coastline points.
    coasts = [c for c in selected if c.kind == "coast"]
    mouths = [c for c in rivers if c.role == "mouth"]
    for mouth in mouths:
        if not coasts:
            break
        coast = min(coasts, key=lambda c: haversine(mouth.lon, mouth.lat, c.lon, c.lat))
        if haversine(mouth.lon, mouth.lat, coast.lon, coast.lat) <= 45.0:
            add(mouth.cid, coast.cid, "coastal_transfer", directed=False)

    # Canonical nodes become stable named anchors attached to the real carrier.
    for node_id, node in canonical_nodes.items():
        preferred = None
        if node.kind == "river":
            preferred = {"river"}
        elif node.kind == "coast":
            preferred = {"coast"}
        target = nearest_candidate(node, selected, preferred)
        mode = "coastal_transfer" if target.kind == "coast" else "river"
        add(node_id, target.cid, mode, directed=False, meta={"canonical_attachment": True})

    # The old macro graph is retained only as sparse cross-system intent. We no longer
    # subdivide these geometrically; instead they connect the nearest physical carrier
    # locations at passes/portages/open-sea crossings that hydrography cannot infer.
    for old in canonical_edges:
        a, b = canonical_nodes[old.a], canonical_nodes[old.b]
        ta = nearest_candidate(a, selected)
        tb = nearest_candidate(b, selected)
        old_mode = str(old.mode).lower()
        if any(x in old_mode for x in ("pass", "mountain", "alpine", "jura")):
            mode = "pass"
        elif "sea" in old_mode:
            mode = "sea"
        elif "coast" in old_mode or "lagoon" in old_mode:
            mode = "coast"
        elif "river" in old_mode:
            # Real river topology already handles most of these. Add only if the
            # physical endpoints remain widely separated/disconnected.
            if haversine(ta.lon, ta.lat, tb.lon, tb.lat) < 65:
                continue
            mode = "portage"
        else:
            mode = "bridge"
        add(ta.cid, tb.cid, mode, directed=bool(old.directed), meta={
            "canonical_intent": f"{old.a}->{old.b}", "original_mode": str(old.mode)
        })
    return edges


def carrier_nodes(selected: Sequence[Candidate]) -> List[Dict[str, Any]]:
    return [{
        "id": c.cid, "label": f"{c.kind.title()} locality {c.cid}", "lon": c.lon, "lat": c.lat,
        "kind": c.kind, "settlement_weight": .45 if c.kind == "river" else .38,
        "region": c.region, "source_feature_id": c.source_feature_id,
        "river_order": c.river_order, "upstream_area_km2": c.upstream_area_km2,
        "discharge_m3s": c.discharge_m3s, "role": c.role, "importance": c.score,
    } for c in selected]


def build_carrier(hypothesis_path: Path, hydrorivers_path: Path, coast_paths: Sequence[Path],
                  target_nodes: int = DEFAULT_TARGET, bbox_wgs84: Sequence[float] = DEFAULT_BBOX) -> Dict[str, Any]:
    hypothesis = json.loads(hypothesis_path.read_text(encoding="utf-8"))
    world = med.MediterraneanProvenanceWorld(hypothesis, seed=1)
    world._build_graph()
    canonical_nodes = dict(world.nodes)
    canonical_edges = list(world.edges)

    rivers = load_hydrorivers(hydrorivers_path, bbox_wgs84)
    coast = load_coast(coast_paths, bbox_wgs84)
    rc, _ = river_candidates(rivers, canonical_nodes)
    cc, _ = coast_candidates(coast, canonical_nodes)
    candidates = rc + cc
    selected = select_budget(candidates, target_nodes, len(canonical_nodes))
    if len(selected) + len(canonical_nodes) != target_nodes:
        raise RuntimeError(
            f"Could not hit exact node budget: canonical={len(canonical_nodes)}, selected={len(selected)}, target={target_nodes}"
        )
    edges = build_edges(selected, canonical_nodes, canonical_edges)
    return {
        "schema": SCHEMA,
        "source": "derived HydroRIVERS + Natural Earth physical carrier",
        "build_version": BUILD_VERSION,
        "target_nodes": target_nodes,
        "canonical_node_count": len(canonical_nodes),
        "derived_node_count": len(selected),
        "nodes": carrier_nodes(selected),
        "edges": edges,
        "provenance": {
            "hydrorivers_path": str(hydrorivers_path),
            "coastline_paths": [str(p) for p in coast_paths],
            "bbox_wgs84": list(map(float, bbox_wgs84)),
            "build_parameters": {
                "target_nodes": target_nodes,
                "river_candidate_spacing_km": 32.0,
                "coast_candidate_spacing_km": 38.0,
                "node_budget": DEFAULT_BUDGET,
            },
            "note": "Raw GIS files are external developer inputs and are not bundled with player runtime.",
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hydrorivers", required=True, type=Path)
    ap.add_argument("--coast", required=True, action="append", type=Path,
                    help="Natural Earth coastline; pass multiple times to add minor-island coastline")
    ap.add_argument("--hypothesis", type=Path, default=Path("hypotheses/atolia_atesis_1800_1000_v0.json"))
    ap.add_argument("--target", type=int, default=DEFAULT_TARGET)
    ap.add_argument("--out", type=Path, default=HERE / "data" / "physical_carrier_1000.json")
    args = ap.parse_args()
    carrier = build_carrier(args.hypothesis, args.hydrorivers, args.coast, args.target)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(carrier, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "out": str(args.out), "schema": carrier["schema"], "target_nodes": carrier["target_nodes"],
        "derived_nodes": len(carrier["nodes"]), "edges": len(carrier["edges"]),
    }, indent=2))


if __name__ == "__main__":
    main()
