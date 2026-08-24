from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Sequence, Tuple

import numpy as np

import provenance_field as base
import temporal_directional_model as temporal
import transport_fields as fields


MOBILITY_MODEL_VERSION = "artifact-mobility-v2-temporal-directional"

PURPOSEFULNESS = {
    "ingot": 1.35, "scrap": 1.18, "sickle": 1.15, "chisel": 1.12, "awl": 1.10,
    "axe": 1.05, "fitting": 1.02, "knife": .98, "pin": .92, "ring": .90,
    "spearhead": .88, "dagger": .80, "vessel": .72, "ornament": .68,
    "sword": .62, "figurine": .58, "bead": .72,
}


@dataclass(frozen=True)
class MobilityRoute:
    nodes: Tuple[str, ...]
    km: float
    hops: int
    physical_crossings: int
    field_crossings: float
    field_mix: Dict[str, float]
    generalized_cost: float
    mean_direction_bias: float = 0.0
    mean_route_temperature: float = 0.0


def _adjacency(world: Any) -> Dict[str, List[Tuple[str, Any]]]:
    out: Dict[str, List[Tuple[str, Any]]] = {node: [] for node in world.nodes}
    for edge in world.edges:
        out[edge.a].append((edge.b, edge))
        if not edge.directed:
            out[edge.b].append((edge.a, edge))
    return out


def _edge_km(world: Any, edge: Any) -> float:
    a, b = world.nodes[edge.a], world.nodes[edge.b]
    return float(base.haversine_km(a.lon, a.lat, b.lon, b.lat))


def _physical_type(mode: str) -> str:
    m = mode.lower()
    if "river" in m or "lagoon" in m:
        return "river"
    if "sea" in m:
        return "sea"
    if "coast" in m:
        return "coast"
    if any(x in m for x in ("pass", "mountain", "alpine", "jura")):
        return "pass"
    return "land"


def _temporal_field_attraction(world: Any, edge: Any, mix: Mapping[str, float], date_bc: int) -> float:
    """Geometric field attraction after explicit temporal activation."""
    alpha = fields.normalize_mix(mix)
    raw = fields.edge_field_vector(world, edge, date_bc)
    log_w = 0.0
    for name, weight in alpha.items():
        value = max(1e-9, raw[name] * temporal.field_temporal_activation(name, date_bc))
        log_w += weight * np.log(value)
    return float(np.exp(log_w))


def _dijkstra(world: Any, start: str, goal: str, mix: Mapping[str, float], date_bc: int,
              object_class: str, jitter_seed: int | None = None) -> Tuple[List[str], float]:
    adjacency = _adjacency(world)
    rng = np.random.default_rng(jitter_seed) if jitter_seed is not None else None
    purpose = PURPOSEFULNESS.get(object_class, .9)
    dist = {start: 0.0}
    prev: Dict[str, str] = {}
    queue: List[Tuple[float, str]] = [(0.0, start)]
    while queue:
        cur_d, node = heapq.heappop(queue)
        if cur_d != dist.get(node):
            continue
        if node == goal:
            break
        for nxt, edge in adjacency.get(node, []):
            attraction = _temporal_field_attraction(world, edge, mix, date_bc)
            direction_log = temporal.directional_log_bias(object_class, mix, edge, node, nxt, date_bc)
            directed_attraction = attraction * float(np.exp(direction_log))
            temp = temporal.route_temperature(object_class, str(edge.mode), date_bc)
            # Temperature controls the scale of deterministic per-biography cost noise.
            # River/local utilitarian paths stay narrow; Mediterranean prestige paths
            # can choose among substantially more near-equivalent alternatives.
            jitter = 1.0 if rng is None else float(np.exp(rng.normal(0.0, .10 * temp / max(.45, purpose))))
            base_cost = max(1e-6, float(edge.cost))
            step = base_cost * jitter / max(.08, directed_attraction) ** (1.0 / max(.42, purpose))
            nd = cur_d + step
            if nd < dist.get(nxt, float("inf")):
                dist[nxt] = nd
                prev[nxt] = node
                heapq.heappush(queue, (nd, nxt))
    if goal not in dist:
        raise RuntimeError(f"No mobility path from {start} to {goal}")
    path = [goal]
    while path[-1] != start:
        path.append(prev[path[-1]])
    path.reverse()
    return path, float(dist[goal])


def route_for_object(world: Any, bundle: Any, object_class: str, date_bc: int,
                     jitter_seed: int | None = None) -> MobilityRoute:
    phase = float(np.clip((1800.0 - date_bc) / 800.0, 0.0, 1.0))
    mix = fields.object_field_mix(object_class, bundle.family, phase)
    nodes, cost = _dijkstra(world, bundle.origin, bundle.destination, mix, date_bc, object_class, jitter_seed)
    km = 0.0
    physical_crossings = 0
    field_crossings = 0.0
    direction_values: List[float] = []
    temperature_values: List[float] = []
    previous_type = None
    previous_sig = None
    edge_lookup: Dict[Tuple[str, str], Any] = {}
    for edge in world.edges:
        edge_lookup[(edge.a, edge.b)] = edge
        if not edge.directed:
            edge_lookup[(edge.b, edge.a)] = edge
    for a, b in zip(nodes[:-1], nodes[1:]):
        edge = edge_lookup[(a, b)]
        km += _edge_km(world, edge)
        ptype = _physical_type(str(edge.mode))
        if previous_type is not None and ptype != previous_type:
            physical_crossings += 1
        previous_type = ptype
        sig = fields.field_signature(world, edge, mix, date_bc)
        if previous_sig is not None:
            field_crossings += fields.js_divergence(previous_sig, sig)
        previous_sig = sig
        direction_values.append(temporal.directional_log_bias(object_class, mix, edge, a, b, date_bc))
        temperature_values.append(temporal.route_temperature(object_class, str(edge.mode), date_bc))
    return MobilityRoute(
        nodes=tuple(nodes), km=float(km), hops=max(0, len(nodes) - 1),
        physical_crossings=int(physical_crossings), field_crossings=float(field_crossings),
        field_mix=dict(mix), generalized_cost=float(cost),
        mean_direction_bias=float(np.mean(direction_values)) if direction_values else 0.0,
        mean_route_temperature=float(np.mean(temperature_values)) if temperature_values else 0.0,
    )


def choose_deposition_position(rng: np.random.Generator, route: Sequence[str], object_class: str) -> int:
    """Biographies can terminate anywhere after the first third, with prestige objects broader."""
    n = len(route)
    if n <= 1:
        return 0
    low = max(0, n // 3)
    prestige = object_class in {"sword", "dagger", "ornament", "figurine", "vessel", "spearhead"}
    u = float(rng.beta(1.45 if prestige else 2.15, 1.25 if prestige else 1.05))
    return int(np.clip(low + round(u * (n - 1 - low)), low, n - 1))
