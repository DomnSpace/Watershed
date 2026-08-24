from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

import provenance_field as base
import provenance_field_mediterranean as med
import dense_geography_v1 as fallback


PHYSICAL_GEOGRAPHY_VERSION = "physical-carrier-v1"
DEFAULT_CARRIER = Path(__file__).resolve().parent / "data" / "physical_carrier_1000.json"


def install_carrier(world: Any, target_nodes: int = 1000, carrier_path: Path = DEFAULT_CARRIER) -> Dict[str, Any]:
    """Install a derived offline carrier graph, or use the deterministic migration scaffold.

    The committed carrier JSON is intentionally a *derived* graph, not raw HydroRIVERS
    or Natural Earth data. Raw GIS sources stay outside player generation. Until the
    derived file is built, the existing dense skeleton remains a compatible fallback.
    """
    canonical = set(world.nodes)
    if not carrier_path.exists():
        report = fallback.densify_world_graph(world, target_nodes)
        report.update({
            "physical_geography_version": PHYSICAL_GEOGRAPHY_VERSION,
            "carrier_source": "dense-geography-v1 migration fallback",
            "real_geometry_loaded": False,
            "carrier_path": str(carrier_path),
        })
        return report

    data = json.loads(carrier_path.read_text(encoding="utf-8"))
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    if not nodes or not edges:
        raise ValueError(f"Carrier {carrier_path} has no nodes/edges")

    # Preserve canonical node objects/IDs exactly. Derived carrier may add metadata
    # for them but cannot silently move the hypothesis anchors.
    for item in nodes:
        node_id = str(item["id"])
        if node_id in canonical:
            continue
        world.nodes[node_id] = base.Node(
            node_id, str(item.get("label", node_id)), float(item["lon"]), float(item["lat"]),
            str(item.get("kind", "hub")), float(item.get("settlement_weight", .45)),
        )
        med.REGION_BY_NODE[node_id] = str(item.get("region", "other"))

    world.edges = []
    for item in edges:
        a, b = str(item["a"]), str(item["b"])
        if a not in world.nodes or b not in world.nodes:
            raise ValueError(f"Carrier edge references missing node: {a} -> {b}")
        world.edges.append(base.Edge(a, b, str(item.get("mode", "plain")), float(item["cost"]), bool(item.get("directed", False))))

    missing = canonical - set(world.nodes)
    if missing:
        raise ValueError(f"Carrier lost canonical nodes: {sorted(missing)}")
    return {
        "physical_geography_version": PHYSICAL_GEOGRAPHY_VERSION,
        "carrier_source": str(data.get("source", "derived HydroRIVERS/Natural Earth carrier")),
        "real_geometry_loaded": True,
        "carrier_path": str(carrier_path),
        "final_nodes": len(world.nodes),
        "final_edges": len(world.edges),
        "canonical_nodes": len(canonical),
        "provenance": data.get("provenance", {}),
    }


def carrier_schema() -> Dict[str, Any]:
    return {
        "schema": "atolia.physical-carrier.v1",
        "nodes": ["id", "label", "lon", "lat", "kind", "settlement_weight", "region", "source_feature_id"],
        "edges": ["a", "b", "mode", "cost", "directed", "source_feature_id", "river_order", "upstream_area_km2", "discharge_m3s"],
        "required_provenance": ["hydrorivers_version", "hydrobasins_version", "coastline_source", "build_parameters"],
    }
