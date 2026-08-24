from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

import numpy as np

import provenance_field as base
import provenance_field_mediterranean as med


DENSE_GEOGRAPHY_VERSION = "dense-geography-v1"
DEFAULT_TARGET_NODES = 1000


@dataclass(frozen=True)
class DenseNodeMeta:
    parent_a: str
    parent_b: str
    edge_mode: str
    fraction: float
    corridor_region: str
    original_edge_km: float


def _slug(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return value[:42] or "node"


def _great_circle_fraction(a: base.Node, b: base.Node, fraction: float) -> Tuple[float, float]:
    """Stable spherical interpolation, avoiding dateline pathologies."""
    f = float(np.clip(fraction, 0.0, 1.0))
    lon1, lat1 = math.radians(a.lon), math.radians(a.lat)
    lon2, lat2 = math.radians(b.lon), math.radians(b.lat)
    va = np.array([math.cos(lat1) * math.cos(lon1), math.cos(lat1) * math.sin(lon1), math.sin(lat1)])
    vb = np.array([math.cos(lat2) * math.cos(lon2), math.cos(lat2) * math.sin(lon2), math.sin(lat2)])
    dot = float(np.clip(np.dot(va, vb), -1.0, 1.0))
    omega = math.acos(dot)
    if omega < 1e-10:
        v = va
    else:
        v = math.sin((1.0 - f) * omega) / math.sin(omega) * va + math.sin(f * omega) / math.sin(omega) * vb
    v /= np.linalg.norm(v)
    lat = math.degrees(math.asin(float(v[2])))
    lon = math.degrees(math.atan2(float(v[1]), float(v[0])))
    return lon, lat


def _node_kind(mode: str, a: base.Node, b: base.Node) -> str:
    m = mode.lower()
    if "river" in m:
        return "river"
    if any(token in m for token in ("sea", "coast", "lagoon", "channel")):
        return "coast"
    if any(token in m for token in ("pass", "mountain", "alpine", "jura")):
        return "pass"
    if "source" in {a.kind, b.kind}:
        return "source_corridor"
    return "hub"


def _region_for_fraction(a_id: str, b_id: str, fraction: float) -> str:
    ra = med.REGION_BY_NODE.get(a_id, "other")
    rb = med.REGION_BY_NODE.get(b_id, "other")
    if ra == rb:
        return ra
    return ra if fraction < 0.5 else rb


def _edge_priority(edge: base.Edge, nodes: Mapping[str, base.Node]) -> float:
    a, b = nodes[edge.a], nodes[edge.b]
    km = max(1.0, base.haversine_km(a.lon, a.lat, b.lon, b.lat))
    m = edge.mode.lower()
    mode_weight = 1.0
    if "river" in m:
        mode_weight = 1.35
    elif any(token in m for token in ("coast", "lagoon", "channel")):
        mode_weight = 1.22
    elif "sea" in m:
        mode_weight = 0.92
    elif any(token in m for token in ("pass", "mountain", "alpine", "jura")):
        mode_weight = 1.08
    return km * mode_weight


def _allocate_intermediates(edges: Sequence[base.Edge], nodes: Mapping[str, base.Node], total: int) -> List[int]:
    """Allocate exactly total intermediate nodes across all transport edges."""
    if total <= 0:
        return [0] * len(edges)
    priorities = np.asarray([_edge_priority(e, nodes) for e in edges], dtype=float)
    if priorities.sum() <= 0:
        priorities[:] = 1.0
    raw = priorities / priorities.sum() * total
    alloc = np.floor(raw).astype(int)
    remainder = int(total - alloc.sum())
    if remainder:
        frac = raw - alloc
        order = np.argsort(-frac)
        for idx in order[:remainder]:
            alloc[int(idx)] += 1
    return [int(v) for v in alloc]


def densify_world_graph(world: Any, target_nodes: int = DEFAULT_TARGET_NODES) -> Dict[str, Any]:
    """Replace every transport edge with a deterministic chain, preserving endpoints.

    The archaeology graph remains independent of HydroBASINS downloads at runtime.
    Its geometry is grounded in the already-curated Watershed transport skeleton;
    density is distributed by geographic edge length and corridor type.
    """
    target_nodes = int(max(len(world.nodes), target_nodes))
    original_nodes = dict(world.nodes)
    original_edges = list(world.edges)
    add_total = target_nodes - len(original_nodes)
    allocations = _allocate_intermediates(original_edges, original_nodes, add_total)

    new_edges: List[base.Edge] = []
    metadata: Dict[str, DenseNodeMeta] = {}
    original_edge_stats: List[Dict[str, Any]] = []

    for edge_no, (edge, count) in enumerate(zip(original_edges, allocations), start=1):
        a = original_nodes[edge.a]
        b = original_nodes[edge.b]
        original_km = base.haversine_km(a.lon, a.lat, b.lon, b.lat)
        base_factor = edge.cost / max(original_km, 1e-9)
        chain = [edge.a]
        kind = _node_kind(edge.mode, a, b)
        for i in range(1, count + 1):
            f = i / (count + 1.0)
            lon, lat = _great_circle_fraction(a, b, f)
            node_id = f"dg_{edge_no:03d}_{_slug(edge.a)}_{_slug(edge.b)}_{i:03d}"
            region = _region_for_fraction(edge.a, edge.b, f)
            label = f"{edge.mode.replace('_', ' ').title()} locality {i}/{count} — {a.label} ↔ {b.label}"
            settlement_weight = float(max(0.18, min(1.35, math.sqrt(a.settlement_weight * b.settlement_weight) * 0.72)))
            world.nodes[node_id] = base.Node(node_id, label, lon, lat, kind, settlement_weight)
            med.REGION_BY_NODE[node_id] = region
            if edge.a in med.ATOLIA_CORE_NODES and edge.b in med.ATOLIA_CORE_NODES:
                med.ATOLIA_CORE_NODES.add(node_id)
            metadata[node_id] = DenseNodeMeta(
                parent_a=edge.a,
                parent_b=edge.b,
                edge_mode=edge.mode,
                fraction=f,
                corridor_region=region,
                original_edge_km=float(original_km),
            )
            chain.append(node_id)
        chain.append(edge.b)

        segment_cost_sum = 0.0
        segment_km_max = 0.0
        for x, y in zip(chain[:-1], chain[1:]):
            nx, ny = world.nodes[x], world.nodes[y]
            km = base.haversine_km(nx.lon, nx.lat, ny.lon, ny.lat)
            cost = km * base_factor
            segment_cost_sum += cost
            segment_km_max = max(segment_km_max, km)
            new_edges.append(base.Edge(x, y, edge.mode, cost, edge.directed))
        original_edge_stats.append({
            "a": edge.a,
            "b": edge.b,
            "mode": edge.mode,
            "original_km": float(original_km),
            "intermediate_nodes": int(count),
            "segments": int(count + 1),
            "max_segment_km": float(segment_km_max),
            "cost_error": float(segment_cost_sum - edge.cost),
        })

    world.edges = new_edges
    world.dense_node_metadata = metadata
    segment_km = [
        base.haversine_km(world.nodes[e.a].lon, world.nodes[e.a].lat, world.nodes[e.b].lon, world.nodes[e.b].lat)
        for e in new_edges
    ]
    return {
        "version": DENSE_GEOGRAPHY_VERSION,
        "original_nodes": len(original_nodes),
        "target_nodes": target_nodes,
        "final_nodes": len(world.nodes),
        "original_edges": len(original_edges),
        "final_edges": len(new_edges),
        "added_nodes": len(world.nodes) - len(original_nodes),
        "mean_segment_km": float(np.mean(segment_km)) if segment_km else 0.0,
        "median_segment_km": float(np.median(segment_km)) if segment_km else 0.0,
        "p95_segment_km": float(np.quantile(segment_km, 0.95)) if segment_km else 0.0,
        "max_segment_km": float(max(segment_km)) if segment_km else 0.0,
        "edge_stats": original_edge_stats,
    }


def connectivity_report(world: Any, canonical_nodes: Iterable[str] = ()) -> Dict[str, Any]:
    node_ids = set(world.nodes)
    adjacency: Dict[str, set[str]] = {node: set() for node in node_ids}
    for edge in world.edges:
        adjacency[edge.a].add(edge.b)
        if not edge.directed:
            adjacency[edge.b].add(edge.a)
    if not node_ids:
        return {"connected": True, "reachable": 0, "nodes": 0, "canonical_missing": []}
    start = next(iter(node_ids))
    seen = {start}
    stack = [start]
    while stack:
        cur = stack.pop()
        for nxt in adjacency[cur]:
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    canonical = set(canonical_nodes)
    return {
        "connected": len(seen) == len(node_ids),
        "reachable": len(seen),
        "nodes": len(node_ids),
        "canonical_missing": sorted(canonical - node_ids),
        "isolated_nodes": sorted(node for node, neighbors in adjacency.items() if not neighbors),
    }
