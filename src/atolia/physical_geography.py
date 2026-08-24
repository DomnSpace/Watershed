from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import provenance_field as base
import provenance_field_mediterranean as med
import dense_geography_v1 as fallback


PHYSICAL_GEOGRAPHY_VERSION = "physical-carrier-v2"
DEFAULT_CARRIER = Path(__file__).resolve().parent / "data" / "physical_carrier_1000.json"
SUPPORTED_SCHEMAS = {"atolia.physical-carrier.v1", "atolia.physical-carrier.v2"}


def install_carrier(world: Any, target_nodes: int = 1000, carrier_path: Path = DEFAULT_CARRIER) -> Dict[str, Any]:
    """Install the derived offline physical carrier or explicitly report fallback use.

    Canonical archaeology/source nodes already exist when this function is called and
    are never moved or replaced by the carrier. The JSON contains only derived nodes
    and edges plus build provenance; raw GIS is not a runtime dependency.
    """
    canonical = set(world.nodes)
    if not carrier_path.exists():
        report = fallback.densify_world_graph(world, target_nodes)
        report.update({
            "physical_geography_version": PHYSICAL_GEOGRAPHY_VERSION,
            "carrier_source": "dense-geography-v1 migration fallback",
            "real_geometry_loaded": False,
            "carrier_path": str(carrier_path),
            "warning": "Round-2 derived physical carrier is absent; routes use migration scaffold geometry.",
        })
        return report

    data = json.loads(carrier_path.read_text(encoding="utf-8"))
    schema = str(data.get("schema", ""))
    if schema not in SUPPORTED_SCHEMAS:
        raise ValueError(f"Unsupported carrier schema {schema!r}; expected one of {sorted(SUPPORTED_SCHEMAS)}")
    nodes = data.get("nodes", [])
    edges = data.get("edges", [])
    if not nodes or not edges:
        raise ValueError(f"Carrier {carrier_path} has no nodes/edges")

    expected_total = int(data.get("target_nodes", target_nodes))
    if expected_total != int(target_nodes):
        raise ValueError(f"Carrier target {expected_total} != requested world target {target_nodes}")
    if len(nodes) + len(canonical) != expected_total:
        raise ValueError(
            f"Carrier node budget mismatch: derived={len(nodes)} canonical={len(canonical)} target={expected_total}"
        )

    derived_ids = [str(item["id"]) for item in nodes]
    if len(derived_ids) != len(set(derived_ids)):
        raise ValueError("Carrier contains duplicate derived node IDs")
    collisions = canonical.intersection(derived_ids)
    if collisions:
        raise ValueError(f"Carrier illegally duplicates canonical nodes: {sorted(collisions)[:10]}")

    for item in nodes:
        node_id = str(item["id"])
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
        cost = float(item["cost"])
        if not (cost > 0):
            raise ValueError(f"Carrier edge has non-positive cost: {a} -> {b}")
        world.edges.append(base.Edge(
            a, b, str(item.get("mode", "plain")), cost, bool(item.get("directed", False))
        ))

    return {
        "physical_geography_version": PHYSICAL_GEOGRAPHY_VERSION,
        "carrier_schema": schema,
        "carrier_source": str(data.get("source", "derived HydroRIVERS/Natural Earth carrier")),
        "real_geometry_loaded": True,
        "carrier_path": str(carrier_path),
        "final_nodes": len(world.nodes),
        "derived_nodes": len(nodes),
        "final_edges": len(world.edges),
        "canonical_nodes": len(canonical),
        "provenance": data.get("provenance", {}),
    }


def carrier_schema() -> Dict[str, Any]:
    return {
        "schema": "atolia.physical-carrier.v2",
        "nodes": [
            "id", "label", "lon", "lat", "kind", "settlement_weight", "region",
            "source_feature_id", "river_order", "upstream_area_km2", "discharge_m3s", "role", "importance",
        ],
        "edges": [
            "a", "b", "mode", "cost", "directed", "source_feature_id", "river_order",
            "upstream_area_km2", "discharge_m3s", "canonical_attachment", "canonical_intent",
        ],
        "required_provenance": ["coastline_paths", "bbox_wgs84", "build_parameters"],
    }
