from __future__ import annotations

"""Read the immutable world tables embedded in an Atolia v3 R17 NetCDF.

R17 is a frozen field product.  Player creation must never rebuild the hidden
world from a hypothesis document.  This module rehydrates only the static data
needed by the existing Phase-01 -> Phase-05 materializers: graph, sources,
bundles, workshops/guilds, production cells, and the canonical hydro context.
"""

from collections import defaultdict
import heapq
from pathlib import Path
from typing import Any

import numpy as np
from netCDF4 import Dataset

import archaeology_observation_v2 as observation
import intensity_circulation as intensity
import provenance_field as base


WORLD_TABLE_SCHEMA = "atolia-v3-r17-frozen-world-v1"


def _strings(var: Any) -> list[str]:
    values = var[:]
    return [value.decode("utf-8") if isinstance(value, bytes) else str(value) for value in values]


class FrozenWorld:
    """Minimal world interface consumed by the deterministic v3 materializers."""

    def __init__(self, ds: Dataset) -> None:
        self.seed = int(ds.world_seed)
        self.nodes: dict[str, base.Node] = {}
        self.edges: list[base.Edge] = []
        self.sources: dict[str, base.SourceField] = {}
        self.bundles: list[base.JetBundle] = []
        self.bundle_incidence: dict[str, float] = {}
        self.workshops: list[base.Workshop] = []
        self.workshops_by_node: dict[str, list[int]] = defaultdict(list)
        self.guilds: dict[str, dict[str, Any]] = {}
        self.workshop_guild: dict[str, str | None] = {}
        self.guild_strength: dict[str, float] = {}
        self._distance_cache: dict[tuple[str, str], float] = {}
        self._read_nodes(ds)
        self._read_edges(ds)
        self._read_sources(ds)
        self._read_bundles(ds)
        self._read_workshops(ds)
        self._read_guilds(ds)

    def _read_nodes(self, ds: Dataset) -> None:
        g = ds.groups["world_nodes"]
        ids = _strings(g.variables["node_id"])
        labels = _strings(g.variables["label"])
        kinds = _strings(g.variables["kind"])
        lon = np.asarray(g.variables["lon"][:], dtype=np.float64)
        lat = np.asarray(g.variables["lat"][:], dtype=np.float64)
        settlement = np.asarray(g.variables["settlement_weight"][:], dtype=np.float64)
        for i, node_id in enumerate(ids):
            self.nodes[node_id] = base.Node(
                node_id, labels[i], float(lon[i]), float(lat[i]), kinds[i], float(settlement[i])
            )

    def _read_edges(self, ds: Dataset) -> None:
        g = ds.groups["world_edges"]
        node_ids = list(self.nodes)
        a = np.asarray(g.variables["a_node"][:], dtype=np.int64)
        b = np.asarray(g.variables["b_node"][:], dtype=np.int64)
        modes = _strings(g.variables["mode"])
        costs = np.asarray(g.variables["cost"][:], dtype=np.float64)
        directed = np.asarray(g.variables["directed"][:], dtype=np.int8)
        self.edges = [
            base.Edge(node_ids[int(a[i])], node_ids[int(b[i])], modes[i], float(costs[i]), bool(directed[i]))
            for i in range(len(a))
        ]

    def _read_sources(self, ds: Dataset) -> None:
        g = ds.groups["world_sources"]
        ids = _strings(g.variables["source_id"])
        labels = _strings(g.variables["label"])
        lon = np.asarray(g.variables["lon"][:], dtype=np.float64)
        lat = np.asarray(g.variables["lat"][:], dtype=np.float64)
        start = np.asarray(g.variables["start_bc"][:], dtype=np.int64)
        end = np.asarray(g.variables["end_bc"][:], dtype=np.int64)
        cap = np.asarray(g.variables["capacity_scale"][:], dtype=np.float64)
        trace = {name: np.asarray(g.variables[f"trace_{name}"][:], dtype=np.float64) for name in base.TRACE_KEYS}
        isotope = {name: np.asarray(g.variables[f"isotope_{name}"][:], dtype=np.float64) for name in base.ISO_KEYS}
        for i, source_id in enumerate(ids):
            self.sources[source_id] = base.SourceField(
                source_id,
                labels[i],
                float(lon[i]),
                float(lat[i]),
                int(start[i]),
                int(end[i]),
                float(cap[i]),
                {name: float(trace[name][i]) for name in base.TRACE_KEYS},
                {name: float(isotope[name][i]) for name in base.ISO_KEYS},
            )

    def _read_bundles(self, ds: Dataset) -> None:
        g = ds.groups["world_bundles"]
        ids = _strings(g.variables["bundle_id"])
        families = _strings(g.variables["family"])
        origins = _strings(g.variables["origin"])
        destinations = _strings(g.variables["destination"])
        recycle = np.asarray(g.variables["recycle_mean"][:], dtype=np.float64)
        incidence = np.asarray(g.variables["incidence"][:], dtype=np.float64)
        for i, bundle_id in enumerate(ids):
            self.bundles.append(base.JetBundle(
                id=bundle_id,
                family=families[i],
                origin=origins[i],
                destination=destinations[i],
                route=[origins[i], destinations[i]],
                source_mix={},
                technical_affinity=np.zeros(6, dtype=np.float64),
                symbolic_affinity=np.zeros(4, dtype=np.float64),
                recycle_mean=float(recycle[i]),
                flux_tonnes={},
            ))
            self.bundle_incidence[bundle_id] = float(incidence[i])

    def _read_workshops(self, ds: Dataset) -> None:
        g = ds.groups["world_workshops"]
        ids = _strings(g.variables["workshop_id"])
        nodes = _strings(g.variables["node_id"])
        lineage = _strings(g.variables["lineage_id"])
        primary_guild = _strings(g.variables["primary_guild_id"])
        lon = np.asarray(g.variables["lon"][:], dtype=np.float64)
        lat = np.asarray(g.variables["lat"][:], dtype=np.float64)
        start = np.asarray(g.variables["start_bc"][:], dtype=np.int64)
        end = np.asarray(g.variables["end_bc"][:], dtype=np.int64)
        workers = np.asarray(g.variables["workers"][:], dtype=np.int64)
        technical = np.asarray(g.variables["technical_vector"][:], dtype=np.float64)
        capacity = np.asarray(g.variables["capacity_weight"][:], dtype=np.float64)
        strength = np.asarray(g.variables["guild_strength"][:], dtype=np.float64)
        for i, workshop_id in enumerate(ids):
            row = base.Workshop(
                workshop_id,
                nodes[i],
                float(lon[i]),
                float(lat[i]),
                int(start[i]),
                int(end[i]),
                int(workers[i]),
                lineage[i],
                np.asarray(technical[i], dtype=np.float64),
                float(capacity[i]),
            )
            self.workshops_by_node[row.node_id].append(len(self.workshops))
            self.workshops.append(row)
            self.workshop_guild[workshop_id] = primary_guild[i] or None
            self.guild_strength[workshop_id] = float(strength[i])

    def _read_guilds(self, ds: Dataset) -> None:
        g = ds.groups["world_guilds"]
        ids = _strings(g.variables["guild_id"])
        anchors = _strings(g.variables["anchor_node"])
        mobility = np.asarray(g.variables["mobility_scale"][:], dtype=np.float64)
        prototype = np.asarray(g.variables["prototype"][:], dtype=np.float64)
        for i, guild_id in enumerate(ids):
            self.guilds[guild_id] = {
                "prototype": np.asarray(prototype[i], dtype=np.float64),
                "anchor_node": anchors[i],
                "mobility_scale": float(mobility[i]),
                "core_seed_workshops": [],
            }

    def _network_distance(self, start: str, goal: str) -> float:
        key = (str(start), str(goal))
        if key in self._distance_cache:
            return self._distance_cache[key]
        if start == goal:
            self._distance_cache[key] = 0.0
            return 0.0
        adjacency: dict[str, list[tuple[str, float]]] = defaultdict(list)
        for edge in self.edges:
            adjacency[str(edge.a)].append((str(edge.b), float(edge.cost)))
            if not edge.directed:
                adjacency[str(edge.b)].append((str(edge.a), float(edge.cost)))
        dist = {str(start): 0.0}
        heap = [(0.0, str(start))]
        while heap:
            d, current = heapq.heappop(heap)
            if d != dist.get(current):
                continue
            if current == str(goal):
                self._distance_cache[key] = d
                self._distance_cache[(str(goal), str(start))] = d
                return d
            for nxt, cost in adjacency.get(current, ()):
                nd = d + cost
                if nd < dist.get(nxt, float("inf")):
                    dist[nxt] = nd
                    heapq.heappush(heap, (nd, nxt))
        return 9999.0

    def _shortest_distance(self, start: str, goal: str) -> float:
        return self._network_distance(start, goal)

    def _deposition_probabilities(self, object_class: str, bundle: Any) -> dict[str, float]:
        # The inherited method uses only bundle family/incidence and fixed priors.
        return observation.ArchaeologicalObservationWorld._deposition_probabilities(self, object_class, bundle)


def load_production_cells(ds: Dataset) -> list[intensity.ProductionCell]:
    g = ds.groups["production_cells"]
    bundle = _strings(g.variables["bundle_id"])
    family = _strings(g.variables["bundle_family"])
    object_class = _strings(g.variables["object_class"])
    date = np.asarray(g.variables["date_bc"][:], dtype=np.int64)
    origin = _strings(g.variables["origin"])
    destination = _strings(g.variables["destination"])
    production = np.asarray(g.variables["production_intensity"][:], dtype=np.float64)
    seed = np.asarray(g.variables["circulation_seed_intensity"][:], dtype=np.float64)
    recycle = np.asarray(g.variables["recycle_mean"][:], dtype=np.float64)
    ptr = np.asarray(g.variables["source_ptr"][:], dtype=np.int64)
    source_ids = _strings(g.variables["source_id"])
    source_weight = np.asarray(g.variables["source_weight"][:], dtype=np.float64)
    out: list[intensity.ProductionCell] = []
    for i in range(len(bundle)):
        a, z = int(ptr[i]), int(ptr[i + 1])
        mix = {source_ids[j]: float(source_weight[j]) for j in range(a, z)}
        out.append(intensity.ProductionCell(
            bundle_id=bundle[i],
            bundle_family=family[i],
            object_class=object_class[i],
            date_bc=int(date[i]),
            origin=origin[i],
            destination=destination[i],
            production_intensity=float(production[i]),
            circulation_seed_intensity=float(seed[i]),
            source_mix=mix,
            recycle_mean=float(recycle[i]),
        ))
    return out


def open_frozen_world(path: Path) -> tuple[Dataset, FrozenWorld, list[intensity.ProductionCell]]:
    ds = Dataset(Path(path), "r")
    try:
        if str(getattr(ds, "world_table_schema", "")) != WORLD_TABLE_SCHEMA:
            raise ValueError("R17 does not contain a frozen-world table")
        world = FrozenWorld(ds)
        cells = load_production_cells(ds)
        return ds, world, cells
    except Exception:
        ds.close()
        raise
