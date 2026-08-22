from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

import numpy as np

TRACE_KEYS = ("Sb_ppm", "Ag_ppm", "Ni_ppm", "Co_ppm", "Bi_ppm")
ISO_KEYS = ("Pb206_204", "Pb207_204", "Pb208_204")

OBJECT_CLASSES: Dict[str, Dict[str, Any]] = {
    "bead":       {"mean_kg": 0.018, "weight": 0.080, "survival": 0.82, "status": 0.35, "start": 1800, "end": 1000},
    "awl":        {"mean_kg": 0.055, "weight": 0.070, "survival": 0.84, "status": 0.20, "start": 1800, "end": 1000},
    "pin":        {"mean_kg": 0.035, "weight": 0.075, "survival": 0.80, "status": 0.42, "start": 1800, "end": 1000},
    "ring":       {"mean_kg": 0.045, "weight": 0.050, "survival": 0.83, "status": 0.48, "start": 1800, "end": 1000},
    "fitting":    {"mean_kg": 0.120, "weight": 0.075, "survival": 0.72, "status": 0.30, "start": 1800, "end": 1000},
    "knife":      {"mean_kg": 0.210, "weight": 0.075, "survival": 0.72, "status": 0.35, "start": 1800, "end": 1000},
    "sickle":     {"mean_kg": 0.380, "weight": 0.060, "survival": 0.70, "status": 0.26, "start": 1700, "end": 1000},
    "chisel":     {"mean_kg": 0.260, "weight": 0.045, "survival": 0.77, "status": 0.25, "start": 1800, "end": 1000},
    "axe":        {"mean_kg": 0.620, "weight": 0.090, "survival": 0.78, "status": 0.46, "start": 1800, "end": 1000},
    "spearhead":  {"mean_kg": 0.330, "weight": 0.065, "survival": 0.75, "status": 0.62, "start": 1700, "end": 1000},
    "dagger":     {"mean_kg": 0.360, "weight": 0.052, "survival": 0.77, "status": 0.70, "start": 1800, "end": 1000},
    "sword":      {"mean_kg": 0.880, "weight": 0.040, "survival": 0.78, "status": 0.88, "start": 1600, "end": 1000},
    "vessel":     {"mean_kg": 1.850, "weight": 0.025, "survival": 0.52, "status": 0.80, "start": 1500, "end": 1000},
    "ornament":   {"mean_kg": 0.095, "weight": 0.055, "survival": 0.79, "status": 0.82, "start": 1800, "end": 1000},
    "figurine":   {"mean_kg": 0.480, "weight": 0.016, "survival": 0.72, "status": 0.93, "start": 1600, "end": 1000},
    "ingot":      {"mean_kg": 4.800, "weight": 0.012, "survival": 0.88, "status": 0.38, "start": 1800, "end": 1000},
    "scrap":      {"mean_kg": 0.160, "weight": 0.070, "survival": 0.70, "status": 0.10, "start": 1800, "end": 1000},
}

DEPOSITION_MODES = (
    "founder_scrap_hoard",
    "finished_object_hoard",
    "selective_ritual_deposit",
    "personal_wealth_deposit",
    "grave_assemblage",
    "settlement_loss",
    "river_wetland_deposit",
    "workshop_debris",
    "catastrophic_abandonment",
)

FAMILY_SPECS: Dict[str, Dict[str, Any]] = {
    "upper_atesis_south": {
        "count": 5, "source_bias": ["upper_atesis", "trentino_east"], "origin": "upper_atesis",
        "destinations": ["verona_plain_gate", "frattesina"],
    },
    "trentino_to_trunk": {
        "count": 7, "source_bias": ["trentino_east", "veneto_pre_alps"], "origin": "trentino_source",
        "destinations": ["verona_plain_gate", "frattesina", "adriatic_outlet"],
    },
    "cross_alpine_import": {
        "count": 4, "source_bias": ["eastern_alps_external", "upper_atesis"], "origin": "eastern_alps_source",
        "destinations": ["verona_plain_gate", "frattesina"],
    },
    "po_redistribution": {
        "count": 5, "source_bias": ["trentino_east", "tyrrhenian_apennine", "upper_atesis"], "origin": "verona_plain_gate",
        "destinations": ["po_west", "frattesina", "veneto_lagoon"],
    },
    "adriatic_export": {
        "count": 5, "source_bias": ["trentino_east", "veneto_pre_alps"], "origin": "frattesina",
        "destinations": ["adriatic_north", "adriatic_south"],
    },
    "adriatic_return": {
        "count": 3, "source_bias": ["balkan_import", "eastern_alps_external"], "origin": "adriatic_south",
        "destinations": ["frattesina", "veneto_lagoon"],
    },
    "tyrrhenian_crossfeed": {
        "count": 4, "source_bias": ["tyrrhenian_apennine", "ligurian_tuscany"], "origin": "tyrrhenian_source",
        "destinations": ["po_west", "verona_plain_gate"],
    },
    "danubian_competitor": {
        "count": 4, "source_bias": ["eastern_alps_external", "balkan_import"], "origin": "eastern_alps_source",
        "destinations": ["friuli_hub", "adriatic_north"],
    },
    "local_recycling": {
        "count": 6, "source_bias": ["trentino_east", "upper_atesis", "veneto_pre_alps"], "origin": "verona_plain_gate",
        "destinations": ["legnago_lower_atesis", "frattesina"],
    },
    "prestige_long_distance": {
        "count": 3, "source_bias": ["eastern_alps_external", "trentino_east", "balkan_import", "ligurian_tuscany"],
        "origin": "trento_gate", "destinations": ["adriatic_south", "tyrrhenian_source"],
    },
}


@dataclass
class Node:
    id: str
    label: str
    lon: float
    lat: float
    kind: str
    settlement_weight: float = 1.0


@dataclass
class Edge:
    a: str
    b: str
    mode: str
    cost: float
    directed: bool = False


@dataclass
class SourceField:
    id: str
    label: str
    lon: float
    lat: float
    start_bc: int
    end_bc: int
    capacity_scale: float
    trace_mean: Dict[str, float]
    isotope_mean: Dict[str, float]


@dataclass
class JetBundle:
    id: str
    family: str
    origin: str
    destination: str
    route: List[str]
    source_mix: Dict[str, float]
    technical_affinity: np.ndarray
    symbolic_affinity: np.ndarray
    recycle_mean: float
    flux_tonnes: Dict[int, float]


@dataclass
class Workshop:
    id: str
    node_id: str
    lon: float
    lat: float
    start_bc: int
    end_bc: int
    workers: int
    lineage_id: str
    technical_vector: np.ndarray
    capacity_weight: float


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(max(0.0, min(1.0, a))))


def normalized_entropy(weights: Sequence[float]) -> float:
    arr = np.asarray(weights, dtype=float)
    arr = arr[arr > 0]
    if len(arr) <= 1:
        return 0.0
    p = arr / arr.sum()
    h = -float(np.sum(p * np.log(p)))
    return h / math.log(len(arr))


def random_simplex(rng: np.random.Generator, n: int, concentration: float = 1.0) -> np.ndarray:
    return rng.dirichlet(np.full(n, concentration, dtype=float))


class ProvenanceWorld:
    """Hidden Atolia archaeometallurgy generator.

    Developer truth and player exports are deliberately separated. Never write
    hidden scenario target, true jetbundle IDs, source truth, workshop truth, or
    route truth into player-facing files.
    """

    def __init__(self, hypothesis: Mapping[str, Any], seed: int = 1300):
        self.hypothesis = dict(hypothesis)
        self.seed = int(seed)
        self.rng = np.random.default_rng(self.seed)
        self.nodes: Dict[str, Node] = {}
        self.edges: List[Edge] = []
        self.sources: Dict[str, SourceField] = {}
        self.bundles: List[JetBundle] = []
        self.workshops: List[Workshop] = []
        self.workshops_by_node: Dict[str, List[int]] = defaultdict(list)
        self.time_slices = list(
            range(
                int(self.hypothesis["claim"]["start_bc"]) - 12,
                int(self.hypothesis["claim"]["end_bc"]),
                -25,
            )
        )
        if not self.time_slices:
            self.time_slices = list(range(1788, 1000, -25))
        self.catalogue_truth: List[Dict[str, Any]] = []

    def build(self, workshop_count: int = 3200) -> None:
        self._build_graph()
        self._build_sources()
        self._build_jetbundles()
        self._allocate_hidden_flux()
        self._build_workshops(workshop_count)

    def _build_graph(self) -> None:
        for w in self.hypothesis["corridor_waypoints"]:
            self.nodes[w["id"]] = Node(w["id"], w["label"], w["lon"], w["lat"], "river", 1.2)

        extra = [
            Node("trentino_source", "Eastern Trentino source field", 11.35, 46.12, "source", 0.5),
            Node("pusteria_gate", "Pusteria cross-Alpine gate", 11.95, 46.80, "pass", 0.55),
            Node("eastern_alps_source", "Eastern Alpine external source", 13.13, 47.39, "source", 0.45),
            Node("po_west", "Western Po redistribution", 10.45, 45.15, "hub", 1.35),
            Node("frattesina", "Frattesina / lower Po node", 11.42, 45.02, "hub", 1.45),
            Node("veneto_lagoon", "Veneto lagoon transfer zone", 12.15, 45.35, "hub", 1.30),
            Node("friuli_hub", "Friuli eastern transfer zone", 13.05, 45.80, "hub", 1.05),
            Node("adriatic_north", "Northern Adriatic exchange", 13.10, 44.90, "coast", 1.0),
            Node("adriatic_south", "Central Adriatic exchange", 14.60, 43.65, "coast", 0.9),
            Node("tyrrhenian_source", "Tyrrhenian / Apennine feeder", 10.05, 44.10, "source", 0.5),
            Node("ligurian_gate", "Ligurian-Apennine crossing", 10.15, 44.55, "pass", 0.6),
        ]
        for n in extra:
            self.nodes[n.id] = n

        trunk = [w["id"] for w in self.hypothesis["corridor_waypoints"]]
        for a, b in zip(trunk[:-1], trunk[1:]):
            self._add_edge(a, b, "river_down", 0.35, directed=False)

        connectors = [
            ("trentino_source", "trento_gate", "mountain_local", 0.95),
            ("bolzano_confluence", "pusteria_gate", "pass", 1.25),
            ("pusteria_gate", "eastern_alps_source", "pass", 1.15),
            ("verona_plain_gate", "po_west", "plain", 0.75),
            ("po_west", "frattesina", "river_plain", 0.45),
            ("legnago_lower_atesis", "frattesina", "plain_river", 0.40),
            ("frattesina", "veneto_lagoon", "lagoon", 0.35),
            ("veneto_lagoon", "adriatic_outlet", "lagoon", 0.30),
            ("veneto_lagoon", "friuli_hub", "coast", 0.40),
            ("friuli_hub", "adriatic_north", "coast", 0.32),
            ("adriatic_north", "adriatic_south", "coast", 0.26),
            ("tyrrhenian_source", "ligurian_gate", "mountain", 1.15),
            ("ligurian_gate", "po_west", "pass", 1.00),
            ("adriatic_outlet", "adriatic_north", "coast", 0.28),
        ]
        for a, b, mode, factor in connectors:
            self._add_edge(a, b, mode, factor, directed=False)

    def _add_edge(self, a: str, b: str, mode: str, factor: float, directed: bool = False) -> None:
        na, nb = self.nodes[a], self.nodes[b]
        km = haversine_km(na.lon, na.lat, nb.lon, nb.lat)
        self.edges.append(Edge(a, b, mode, max(1.0, km * factor), directed))

    def _build_sources(self) -> None:
        specs = [
            ("trentino_east", "Eastern Trentino copper", 11.35, 46.12, 1700, 900, 1.00,
             [820, 180, 1100, 95, 55], [18.17, 15.66, 38.35]),
            ("upper_atesis", "Upper Atesis / central Alpine copper", 10.70, 46.72, 1900, 1000, 0.45,
             [430, 95, 720, 70, 32], [18.25, 15.68, 38.48]),
            ("veneto_pre_alps", "Veneto pre-Alpine copper", 11.70, 46.05, 1750, 950, 0.55,
             [620, 210, 560, 82, 74], [18.09, 15.64, 38.23]),
            ("eastern_alps_external", "Eastern Alpine external copper", 13.13, 47.39, 1650, 1100, 0.80,
             [250, 70, 1320, 140, 36], [18.33, 15.70, 38.61]),
            ("tyrrhenian_apennine", "Tyrrhenian-Apennine copper", 10.10, 44.15, 2100, 900, 0.38,
             [950, 310, 220, 52, 110], [18.04, 15.62, 38.10]),
            ("ligurian_tuscany", "Ligurian / Tuscan copper", 9.95, 44.35, 3400, 900, 0.32,
             [710, 260, 340, 48, 86], [18.00, 15.61, 38.05]),
            ("balkan_import", "Eastern Adriatic / Balkan import family", 15.40, 44.65, 1800, 900, 0.42,
             [350, 130, 890, 125, 48], [18.42, 15.73, 38.76]),
        ]
        for sid, label, lon, lat, start, end, cap, trace, iso in specs:
            trace_mean = {k: float(v) for k, v in zip(TRACE_KEYS, trace)}
            isotope_mean = {k: float(v) for k, v in zip(ISO_KEYS, iso)}
            self.sources[sid] = SourceField(
                sid, label, lon, lat, start, end, cap, trace_mean, isotope_mean
            )

    def _neighbors(self, node_id: str) -> Iterable[Tuple[str, float]]:
        for e in self.edges:
            if e.a == node_id:
                yield e.b, e.cost
            if not e.directed and e.b == node_id:
                yield e.a, e.cost

    def _route(self, start: str, goal: str, jitter: float = 0.18) -> List[str]:
        # Dijkstra with small per-call stochastic edge perturbation: route diversity
        # without fabricating one deterministic prehistoric road.
        dist = {start: 0.0}
        prev: Dict[str, str] = {}
        unused = set(self.nodes)
        while unused:
            cur = min((n for n in unused if n in dist), key=lambda n: dist[n], default=None)
            if cur is None:
                break
            unused.remove(cur)
            if cur == goal:
                break
            for nxt, base_cost in self._neighbors(cur):
                if nxt not in unused:
                    continue
                cost = base_cost * float(self.rng.lognormal(0.0, jitter))
                nd = dist[cur] + cost
                if nd < dist.get(nxt, float("inf")):
                    dist[nxt] = nd
                    prev[nxt] = cur
        if goal not in dist:
            return [start, goal]
        out = [goal]
        while out[-1] != start:
            out.append(prev[out[-1]])
        return list(reversed(out))

    def _build_jetbundles(self) -> None:
        bundle_no = 0
        source_ids = list(self.sources)
        for family, spec in FAMILY_SPECS.items():
            for _ in range(int(spec["count"])):
                bundle_no += 1
                origin = str(spec["origin"])
                dest = str(self.rng.choice(spec["destinations"]))
                route = self._route(origin, dest, jitter=0.22)
                bias = set(spec["source_bias"])
                alpha = np.array([2.8 if sid in bias else 0.28 for sid in source_ids], dtype=float)
                source_mix_arr = self.rng.dirichlet(alpha)
                source_mix = {sid: float(v) for sid, v in zip(source_ids, source_mix_arr) if v > 0.002}
                technical = random_simplex(self.rng, 6, concentration=0.75)
                symbolic = random_simplex(self.rng, 5, concentration=0.55)
                recycle_mean = float(
                    np.clip(
                        self.rng.normal(0.72 if family == "local_recycling" else 0.56, 0.12),
                        0.10,
                        0.92,
                    )
                )
                self.bundles.append(
                    JetBundle(
                        id=f"JB-{bundle_no:03d}",
                        family=family,
                        origin=origin,
                        destination=dest,
                        route=route,
                        source_mix=source_mix,
                        technical_affinity=technical,
                        symbolic_affinity=symbolic,
                        recycle_mean=recycle_mean,
                        flux_tonnes={},
                    )
                )

    def _slice_target(self, center_bc: int) -> float:
        # Tonnes in one 25-year slice, using the developer-only phase prior.
        for phase in self.hypothesis["time_prior"]:
            if int(phase["end_bc"]) < center_bc <= int(phase["start_bc"]):
                return float(phase["mean_tonnes_per_year"]) * 25.0
        return 0.0

    def _bundle_active_weight(self, bundle: JetBundle, center_bc: int) -> float:
        idx = int(bundle.id.split("-")[-1])
        span_start = int(self.hypothesis["claim"]["start_bc"])
        span_end = int(self.hypothesis["claim"]["end_bc"])
        frac = (idx * 0.61803398875) % 1.0
        peak = span_end + 80 + frac * max(1, span_start - span_end - 160)
        sigma = 85.0 + (idx % 7) * 18.0
        pulse = math.exp(-0.5 * ((center_bc - peak) / sigma) ** 2)
        family_floor = 0.10 if bundle.family in {"local_recycling", "po_redistribution"} else 0.03
        return family_floor + pulse

    def _crosses_checkpoint(self, bundle: JetBundle) -> bool:
        checkpoint = str(self.hypothesis["claim"]["checkpoint_id"])
        return checkpoint in bundle.route

    def _allocate_hidden_flux(self) -> None:
        crossing = [bundle for bundle in self.bundles if self._crosses_checkpoint(bundle)]
        noncrossing = [bundle for bundle in self.bundles if not self._crosses_checkpoint(bundle)]
        if not crossing:
            raise RuntimeError("No jetbundle crosses the hidden checkpoint.")

        for t in self.time_slices:
            target = self._slice_target(t)
            if target <= 0:
                continue
            raw = np.array(
                [
                    self._bundle_active_weight(bundle, t) * self.rng.lognormal(0.0, 0.22)
                    for bundle in crossing
                ]
            )
            raw /= raw.sum()
            for bundle, weight in zip(crossing, raw):
                bundle.flux_tonnes[t] = float(target * weight)

            # Flows that do not cross the hidden checkpoint are free latent economy.
            total_other = target * float(self.rng.uniform(0.30, 0.95))
            raw_other = np.array(
                [
                    self._bundle_active_weight(bundle, t) * self.rng.lognormal(0.0, 0.35)
                    for bundle in noncrossing
                ]
            )
            if raw_other.sum() > 0:
                raw_other /= raw_other.sum()
            for bundle, weight in zip(noncrossing, raw_other):
                bundle.flux_tonnes[t] = float(total_other * weight)

    def _build_workshops(self, count: int) -> None:
        node_flux = Counter()
        for bundle in self.bundles:
            q = sum(bundle.flux_tonnes.values())
            for node_id in bundle.route:
                node_flux[node_id] += q / max(1, len(bundle.route))
        node_ids = list(self.nodes)
        weights = np.array(
            [
                (node_flux[node_id] + 1.0) ** 0.72 * self.nodes[node_id].settlement_weight
                for node_id in node_ids
            ],
            dtype=float,
        )
        weights /= weights.sum()

        lineage_count = max(60, int(round(count / 24)))
        lineage_bases = self.rng.dirichlet(np.full(6, 0.75), size=lineage_count)
        chosen_nodes = self.rng.choice(node_ids, size=count, p=weights)

        for i, node_id in enumerate(chosen_nodes):
            node = self.nodes[str(node_id)]
            lineage = int(self.rng.integers(0, lineage_count))
            technical = lineage_bases[lineage] + self.rng.normal(0, 0.025, size=6)
            technical = np.clip(technical, 1e-5, None)
            technical /= technical.sum()

            midpoint = int(self.rng.integers(1050, 1751))
            duration = int(np.clip(self.rng.lognormal(math.log(95), 0.48), 35, 310))
            start_bc = min(1800, midpoint + duration // 2)
            end_bc = max(1000, midpoint - duration // 2)
            workers = int(np.clip(round(self.rng.lognormal(math.log(3.5), 0.88)), 1, 90))
            capacity = float(workers ** 0.82 * self.rng.lognormal(0.0, 0.32))
            spread = 0.025 if node.kind in {"river", "hub"} else 0.055
            lon = float(node.lon + self.rng.normal(0, spread))
            lat = float(node.lat + self.rng.normal(0, spread * 0.75))
            workshop = Workshop(
                id=f"W-{i + 1:04d}",
                node_id=node.id,
                lon=lon,
                lat=lat,
                start_bc=start_bc,
                end_bc=end_bc,
                workers=workers,
                lineage_id=f"L-{lineage + 1:03d}",
                technical_vector=technical,
                capacity_weight=capacity,
            )
            self.workshops_by_node[node.id].append(len(self.workshops))
            self.workshops.append(workshop)

    def _active_workshop(self, node_id: str, date_bc: int) -> Workshop:
        ids = self.workshops_by_node.get(node_id, [])
        active = [i for i in ids if self.workshops[i].end_bc <= date_bc <= self.workshops[i].start_bc]
        if not active:
            active = ids
        if not active:
            return self.workshops[int(self.rng.integers(0, len(self.workshops)))]
        weights = np.array([self.workshops[i].capacity_weight for i in active], dtype=float)
        weights /= weights.sum()
        return self.workshops[int(self.rng.choice(active, p=weights))]

    def _class_weights(self, date_bc: int, bundle: JetBundle) -> Tuple[List[str], np.ndarray]:
        classes, weights = [], []
        for object_class, spec in OBJECT_CLASSES.items():
            if not (int(spec["end"]) <= date_bc <= int(spec["start"])):
                continue
            weight = float(spec["weight"])
            if bundle.family == "prestige_long_distance" and object_class in {
                "sword", "dagger", "ornament", "figurine", "vessel"
            }:
                weight *= 3.2
            if bundle.family == "local_recycling" and object_class in {"scrap", "fitting", "axe", "sickle"}:
                weight *= 2.4
            if bundle.family == "adriatic_export" and object_class in {"ingot", "ornament", "sword", "dagger"}:
                weight *= 1.8
            classes.append(object_class)
            weights.append(weight)
        arr = np.asarray(weights, dtype=float)
        arr /= arr.sum()
        return classes, arr

    def _expected_object_events(self, bundle: JetBundle, t: int) -> float:
        tonnes = bundle.flux_tonnes.get(t, 0.0)
        if tonnes <= 0:
            return 0.0
        classes, weights = self._class_weights(t, bundle)
        avg_mass = sum(OBJECT_CLASSES[c]["mean_kg"] * weight for c, weight in zip(classes, weights))
        reuse_cycles = 1.0 / max(0.12, 1.0 - bundle.recycle_mean)
        manufacture_fraction = 0.48
        kg = tonnes * 1000.0 * manufacture_fraction * reuse_cycles
        return float(kg / max(0.01, avg_mass))

    def generate_archaeological_catalogue(self, max_materialized: int = 30000) -> Dict[str, Any]:
        if not self.bundles or not self.workshops:
            raise RuntimeError("Call build() before generating catalogue.")

        observed_specs: List[Tuple[JetBundle, int, int]] = []
        hidden_events = 0.0
        expected_observed = 0.0

        for bundle in self.bundles:
            for t in self.time_slices:
                events = self._expected_object_events(bundle, t)
                if events <= 0:
                    continue
                hidden_events += events
                # deposition -> survival -> discovery -> catalogue
                base_p = 0.018 * 0.22 * 0.008 * 0.28
                expected = events * base_p
                expected_observed += expected
                n = int(self.rng.poisson(expected))
                if n > 0:
                    observed_specs.append((bundle, t, n))

        total_n = sum(n for _, _, n in observed_specs)
        scale = 1.0
        if total_n > max_materialized:
            scale = max_materialized / total_n

        rows: List[Dict[str, Any]] = []
        object_no = 0
        for bundle, t, n_raw in observed_specs:
            n = int(self.rng.binomial(n_raw, scale)) if scale < 1 else n_raw
            if n <= 0:
                continue
            classes, class_p = self._class_weights(t, bundle)
            for _ in range(n):
                object_no += 1
                object_class = str(self.rng.choice(classes, p=class_p))
                route_pos = int(self.rng.integers(max(0, len(bundle.route) // 3), len(bundle.route)))
                dep_node_id = bundle.route[route_pos]
                dep_node = self.nodes[dep_node_id]
                workshop_node = bundle.route[
                    max(0, route_pos - int(self.rng.integers(0, min(3, route_pos + 1))))
                ]
                workshop = self._active_workshop(workshop_node, t)
                rows.append(
                    self._materialize_object(object_no, object_class, bundle, t, workshop, dep_node)
                )

        self._assign_hoards(rows)
        self.catalogue_truth = rows
        return {
            "hidden_manufacture_use_events_est": int(round(hidden_events)),
            "expected_catalogued_before_bound": float(expected_observed),
            "materialization_scale": float(scale),
            "catalogued_objects": len(rows),
        }

    def _materialize_object(
        self,
        object_no: int,
        object_class: str,
        bundle: JetBundle,
        date_bc: int,
        workshop: Workshop,
        dep_node: Node,
    ) -> Dict[str, Any]:
        mass = float(self.rng.lognormal(math.log(OBJECT_CLASSES[object_class]["mean_kg"]), 0.34))
        recycle = float(np.clip(self.rng.normal(bundle.recycle_mean, 0.10), 0, 0.96))

        source_ids = [
            source_id
            for source_id in bundle.source_mix
            if self.sources[source_id].end_bc <= date_bc <= self.sources[source_id].start_bc
        ]
        if not source_ids:
            source_ids = list(bundle.source_mix)
        source_weights = np.array([bundle.source_mix[source_id] for source_id in source_ids], dtype=float)
        source_weights /= source_weights.sum()
        background = self.rng.dirichlet(np.ones(len(source_ids))) if len(source_ids) > 1 else np.ones(1)
        source_weights = (1 - recycle * 0.42) * source_weights + recycle * 0.42 * background
        source_weights /= source_weights.sum()
        source_mix = {source_id: float(weight) for source_id, weight in zip(source_ids, source_weights)}

        trace = {}
        isotopes = {}
        for key in TRACE_KEYS:
            mean = sum(source_mix[source_id] * self.sources[source_id].trace_mean[key] for source_id in source_ids)
            trace[key] = float(max(0.0, self.rng.lognormal(math.log(max(1.0, mean)), 0.13)))
        for key in ISO_KEYS:
            mean = sum(source_mix[source_id] * self.sources[source_id].isotope_mean[key] for source_id in source_ids)
            isotopes[key] = float(self.rng.normal(mean, 0.018))

        alloy = self._alloy_profile(date_bc, object_class)
        dep_mode = self._deposition_mode(object_class, bundle)
        move_jitter = 0.018 if dep_mode == "workshop_debris" else 0.055
        find_lon = float(dep_node.lon + self.rng.normal(0, move_jitter))
        find_lat = float(dep_node.lat + self.rng.normal(0, move_jitter * 0.75))
        repair_count = int(
            self.rng.poisson(
                0.10
                + 0.55 * recycle
                + (0.28 if object_class in {"sword", "axe", "vessel", "dagger"} else 0)
            )
        )
        surface_complexity = float(
            np.clip(
                self.rng.beta(1.8, 3.8)
                + 0.25 * (object_class in {"ornament", "vessel", "figurine"}),
                0,
                1,
            )
        )
        source_entropy = normalized_entropy(source_weights)
        technique_entropy = normalized_entropy(workshop.technical_vector)
        complexity = float(
            np.clip(
                0.18 * source_entropy
                + 0.15 * technique_entropy
                + 0.14 * recycle
                + 0.12 * min(1.0, repair_count / 2)
                + 0.15 * surface_complexity
                + 0.12 * OBJECT_CLASSES[object_class]["status"]
                + 0.14 * self.rng.random(),
                0,
                1,
            )
        )

        manufacturing_sequence = self._manufacturing_sequence(
            object_class, workshop, repair_count, surface_complexity
        )
        metallography = self._metallography(workshop)
        display_name = self._display_name(object_class, alloy, surface_complexity)

        return {
            "object_id": f"OBJ-{object_no:06d}",
            "display_name": display_name,
            "class": object_class,
            "mass_kg": round(mass, 4),
            "date_center_bc": int(date_bc + self.rng.integers(-12, 13)),
            "date_uncertainty_years": int(self.rng.choice([25, 40, 60, 80, 100])),
            "findspot": {
                "lon": round(find_lon, 5),
                "lat": round(find_lat, 5),
                "node_label": dep_node.label,
            },
            "deposition_mode_truth": dep_mode,
            "hoard_id": None,
            "preservation": self._preservation_label(object_class, dep_mode),
            "catalogue_material": alloy["catalogue_material"],
            "tests": {
                "xrf": {
                    "Cu_pct": alloy["Cu_pct"],
                    "Sn_pct": alloy["Sn_pct"],
                    "As_pct": alloy["As_pct"],
                    "Pb_pct": alloy["Pb_pct"],
                    **{key: round(value, 1) for key, value in trace.items()},
                },
                "lead_isotopes": {key: round(value, 5) for key, value in isotopes.items()},
                "metallography": metallography,
                "manufacturing_sequence": manufacturing_sequence,
                "morphometrics": self._morphometrics(workshop),
            },
            "truth": {
                "bundle_id": bundle.id,
                "bundle_family": bundle.family,
                "source_mix": {key: round(value, 5) for key, value in source_mix.items()},
                "workshop_id": workshop.id,
                "lineage_id": workshop.lineage_id,
                "workshop_node": workshop.node_id,
                "recycle_fraction": round(recycle, 4),
                "repair_count": repair_count,
                "surface_complexity": round(surface_complexity, 4),
                "technical_vector": [round(float(value), 5) for value in workshop.technical_vector],
                "route": list(bundle.route),
                "source_entropy": round(source_entropy, 4),
                "complexity": round(complexity, 4),
            },
        }

    def _alloy_profile(self, date_bc: int, object_class: str) -> Dict[str, Any]:
        late = (1800 - date_bc) / 800.0
        status = OBJECT_CLASSES[object_class]["status"]
        p_tin = float(np.clip(0.25 + 0.62 * late + 0.10 * status, 0.15, 0.95))
        is_tin = self.rng.random() < p_tin
        if is_tin:
            sn = float(np.clip(self.rng.normal(9.0 + 2.0 * status, 2.6), 2.0, 18.0))
            arsenic = float(np.clip(self.rng.lognormal(math.log(0.22), 0.65), 0.02, 1.8))
            lead = float(np.clip(self.rng.lognormal(math.log(0.18 + late * 0.4), 0.85), 0.01, 5.0))
            material = "bronze object"
        else:
            sn = float(np.clip(self.rng.lognormal(math.log(0.12), 0.7), 0.0, 1.2))
            arsenic = float(np.clip(self.rng.lognormal(math.log(0.75), 0.70), 0.05, 4.5))
            lead = float(np.clip(self.rng.lognormal(math.log(0.08), 0.8), 0.0, 1.5))
            material = "copper object" if arsenic < 0.7 else "arsenical copper object"
        cu = max(70.0, 100.0 - sn - arsenic - lead - 0.35)
        return {
            "Cu_pct": round(cu, 3),
            "Sn_pct": round(sn, 3),
            "As_pct": round(arsenic, 3),
            "Pb_pct": round(lead, 3),
            "catalogue_material": material,
        }

    def _deposition_mode(self, object_class: str, bundle: JetBundle) -> str:
        base = np.array([0.15, 0.16, 0.10, 0.08, 0.09, 0.16, 0.10, 0.10, 0.06], dtype=float)
        if object_class in {"scrap", "ingot"}:
            base += np.array([0.25, 0.0, 0.0, 0.0, -0.03, -0.04, -0.02, 0.18, 0.0])
        if object_class in {"sword", "dagger", "spearhead", "ornament", "figurine"}:
            base += np.array([-0.03, 0.08, 0.13, 0.06, 0.08, -0.08, 0.03, -0.08, 0.0])
        if bundle.family == "local_recycling":
            base[0] += 0.16
            base[7] += 0.12
        base = np.clip(base, 0.001, None)
        base /= base.sum()
        return str(self.rng.choice(DEPOSITION_MODES, p=base))

    def _preservation_label(self, object_class: str, mode: str) -> str:
        score = OBJECT_CLASSES[object_class]["survival"] + self.rng.normal(0, 0.12)
        if mode == "river_wetland_deposit":
            score -= 0.06
        if score > 0.82:
            return "good; coherent corrosion layers"
        if score > 0.66:
            return "moderate; surface alteration"
        if score > 0.48:
            return "fragmentary; substantial corrosion"
        return "poor; mineralized / incomplete"

    def _manufacturing_sequence(
        self,
        object_class: str,
        workshop: Workshop,
        repair_count: int,
        surface_complexity: float,
    ) -> List[str]:
        sequence = ["metal batch prepared"]
        cast_classes = {"axe", "spearhead", "dagger", "sword", "figurine", "fitting", "ingot"}
        sheet_classes = {"vessel", "ornament"}
        if object_class in cast_classes:
            sequence += ["mould prepared", "cast", "gate / flash removed"]
        elif object_class in sheet_classes:
            sequence += ["cast or selected blank", "hammered / raised"]
        else:
            sequence += ["blank cast", "hammered to section"]
        if workshop.technical_vector[1] > 0.12:
            sequence.append("hot / warm worked")
        if workshop.technical_vector[2] > 0.12:
            sequence.append("annealed")
        sequence.append("cold finished / planished")
        if workshop.technical_vector[4] > 0.13:
            sequence.append("ground / polished")
        if surface_complexity > 0.60:
            sequence.append("surface treatment / decoration")
        for _ in range(repair_count):
            sequence.append("repair / reworking event")
        return sequence

    def _metallography(self, workshop: Workshop) -> Dict[str, Any]:
        cast_strength = float(workshop.technical_vector[0])
        anneal = float(workshop.technical_vector[2])
        cold = float(workshop.technical_vector[3])
        dendritic = np.clip(
            0.75 * cast_strength + self.rng.normal(0.18, 0.10) - 0.45 * anneal,
            0,
            1,
        )
        recrystallized = np.clip(0.60 * anneal + 0.28 * cold + self.rng.normal(0.08, 0.08), 0, 1)
        grain = float(np.clip(self.rng.normal(5.5 - 2.0 * anneal + 1.0 * cold, 0.8), 1, 9))
        return {
            "dendritic_fraction_index": round(float(dendritic), 3),
            "recrystallized_fraction_index": round(float(recrystallized), 3),
            "grain_size_index": round(grain, 2),
            "working_state": (
                "cast-dominant"
                if dendritic > 0.58
                else "annealed / recrystallized"
                if recrystallized > 0.52
                else "worked"
            ),
        }

    def _morphometrics(self, workshop: Workshop) -> Dict[str, float]:
        vector = workshop.technical_vector
        return {
            "slenderness": round(float(np.clip(0.25 + 0.7 * vector[0] + self.rng.normal(0, 0.04), 0, 1)), 3),
            "section_ratio": round(float(np.clip(0.25 + 0.7 * vector[3] + self.rng.normal(0, 0.04), 0, 1)), 3),
            "symmetry": round(float(np.clip(0.55 + 0.4 * vector[4] + self.rng.normal(0, 0.035), 0, 1)), 3),
            "edge_curvature": round(float(np.clip(0.20 + 0.8 * vector[5] + self.rng.normal(0, 0.05), 0, 1)), 3),
        }

    def _display_name(self, object_class: str, alloy: Mapping[str, Any], surface_complexity: float) -> str:
        material = str(alloy["catalogue_material"]).replace(" object", "")
        adjective = ""
        if object_class == "axe" and alloy["Sn_pct"] > 5:
            adjective = str(self.rng.choice(["flanged", "socketed", "ribbed", "flat"]))
        elif object_class == "spearhead":
            adjective = str(self.rng.choice(["leaf-shaped", "socketed", "midrib"]))
        elif object_class == "dagger":
            adjective = str(self.rng.choice(["riveted", "tanged", "flange-hilted"]))
        elif object_class == "sword":
            adjective = str(self.rng.choice(["flange-hilted", "leaf-shaped", "ribbed"]))
        elif object_class == "vessel":
            adjective = str(self.rng.choice(["hammered", "riveted sheet", "raised"]))
        elif object_class == "ornament":
            adjective = str(self.rng.choice(["spiral", "twisted", "sheet", "cast"]))
        elif object_class == "ingot":
            adjective = str(self.rng.choice(["bar", "bun-shaped", "casting-cake"]))
        if surface_complexity > 0.72 and object_class in {"ornament", "vessel", "figurine", "fitting"}:
            adjective = ("decorated " + adjective).strip()
        return " ".join(value for value in [material, adjective, object_class] if value).strip()

    def _assign_hoards(self, rows: List[Dict[str, Any]]) -> None:
        pools: Dict[Tuple[int, str, str], List[int]] = defaultdict(list)
        for i, row in enumerate(rows):
            time_bin = int(round(row["date_center_bc"] / 50.0) * 50)
            node = row["findspot"]["node_label"]
            mode = row["deposition_mode_truth"]
            pools[(time_bin, node, mode)].append(i)
        hoard_no = 0
        for idxs in pools.values():
            if len(idxs) < 3:
                continue
            self.rng.shuffle(idxs)
            pos = 0
            while pos + 2 < len(idxs):
                size = int(np.clip(self.rng.lognormal(math.log(7), 0.75), 3, 42))
                group = idxs[pos:pos + size]
                if len(group) < 3:
                    break
                hoard_no += 1
                hoard_id = f"H-{hoard_no:04d}"
                for i in group:
                    rows[i]["hoard_id"] = hoard_id
                pos += size

    def select_curriculum(self, n: int = 300, levels: int = 30) -> List[Dict[str, Any]]:
        if not self.catalogue_truth:
            raise RuntimeError("Generate catalogue before selecting curriculum.")
        if n % levels:
            raise ValueError("n must be divisible by levels.")
        per_level = n // levels
        rows = list(self.catalogue_truth)
        complexity = np.array([row["truth"]["complexity"] for row in rows], dtype=float)
        order = np.argsort(complexity)
        quantiles = np.empty(len(rows), dtype=float)
        quantiles[order] = np.linspace(0, 1, len(rows), endpoint=True)

        selected: List[Dict[str, Any]] = []
        used = set()
        seen_class = Counter()
        seen_source = Counter()
        seen_hoard = Counter()

        for level in range(1, levels + 1):
            target = (level - 0.5) / levels
            width = 0.055 if level not in {1, levels} else 0.085
            candidates = [
                i for i, quantile in enumerate(quantiles)
                if abs(quantile - target) <= width and i not in used
            ]
            if level == 1:
                simple = [
                    i for i in candidates
                    if rows[i]["class"] in {"awl", "bead", "pin"}
                    and rows[i]["catalogue_material"] in {"copper object", "arsenical copper object"}
                    and rows[i]["truth"]["repair_count"] == 0
                ]
                if len(simple) >= per_level:
                    candidates = simple
            if level == levels:
                complex_rows = [
                    i for i in candidates
                    if rows[i]["class"] in {"vessel", "ornament", "figurine", "sword", "dagger"}
                    and (
                        rows[i]["truth"]["repair_count"] >= 1
                        or rows[i]["truth"]["source_entropy"] > 0.45
                        or rows[i]["truth"]["surface_complexity"] > 0.62
                    )
                ]
                if len(complex_rows) >= per_level:
                    candidates = complex_rows
            if len(candidates) < per_level:
                candidates = [i for i in range(len(rows)) if i not in used]

            for _ in range(per_level):
                if not candidates:
                    break
                best_i, best_score = None, -1e9
                trial = self.rng.choice(candidates, size=min(220, len(candidates)), replace=False)
                for candidate in trial:
                    i = int(candidate)
                    row = rows[i]
                    source = max(row["truth"]["source_mix"], key=row["truth"]["source_mix"].get)
                    hoard_id = row["hoard_id"] or "singleton"
                    diversity = (
                        0.60 / (1 + seen_class[row["class"]])
                        + 0.55 / (1 + seen_source[source])
                        + 0.30 / (1 + seen_hoard[hoard_id])
                    )
                    closeness = -3.0 * abs(quantiles[i] - target)
                    score = diversity + closeness + float(self.rng.normal(0, 0.03))
                    if score > best_score:
                        best_score, best_i = score, i
                if best_i is None:
                    raise RuntimeError("Curriculum selector exhausted candidates.")
                row = rows[best_i]
                used.add(best_i)
                candidates.remove(best_i)
                source = max(row["truth"]["source_mix"], key=row["truth"]["source_mix"].get)
                hoard_id = row["hoard_id"] or "singleton"
                seen_class[row["class"]] += 1
                seen_source[source] += 1
                seen_hoard[hoard_id] += 1
                out = dict(row)
                out["curriculum_level"] = level
                out["curriculum_index"] = len(selected) + 1
                selected.append(out)

        if len(selected) != n:
            raise RuntimeError(f"Could only select {len(selected)} curriculum objects.")
        return selected

    def build_provenance_field(self, grid_deg: float = 0.28) -> Dict[str, Any]:
        lons = np.array([node.lon for node in self.nodes.values()])
        lats = np.array([node.lat for node in self.nodes.values()])
        grid_x = np.arange(lons.min() - 0.45, lons.max() + 0.46, grid_deg)
        grid_y = np.arange(lats.min() - 0.35, lats.max() + 0.36, grid_deg)
        points = np.array([(x, y) for y in grid_y for x in grid_x], dtype=float)
        features = []
        source_ids = list(self.sources)

        for t in self.time_slices:
            bundle_contrib = np.zeros((len(points), len(self.bundles)), dtype=float)
            source_contrib = np.zeros((len(points), len(source_ids)), dtype=float)
            for bundle_index, bundle in enumerate(self.bundles):
                q = bundle.flux_tonnes.get(t, 0.0)
                if q <= 0:
                    continue
                route_nodes = [self.nodes[node_id] for node_id in bundle.route]
                local = np.zeros(len(points), dtype=float)
                for route_node in route_nodes:
                    dx = (points[:, 0] - route_node.lon) * np.cos(np.radians(route_node.lat))
                    dy = points[:, 1] - route_node.lat
                    d2 = dx * dx + dy * dy
                    local += np.exp(-d2 / (2 * 0.20 ** 2))
                local /= max(1, len(route_nodes))
                contribution = q * local
                bundle_contrib[:, bundle_index] = contribution
                for source_index, source_id in enumerate(source_ids):
                    source_contrib[:, source_index] += contribution * bundle.source_mix.get(source_id, 0.0)

            metal = bundle_contrib.sum(axis=1)
            node_work = Counter()
            for workshop in self.workshops:
                if workshop.end_bc <= t <= workshop.start_bc:
                    node_work[workshop.node_id] += workshop.capacity_weight
            work = np.zeros(len(points), dtype=float)
            for node_id, capacity in node_work.items():
                node = self.nodes[node_id]
                dx = (points[:, 0] - node.lon) * np.cos(np.radians(node.lat))
                dy = points[:, 1] - node.lat
                work += capacity * np.exp(-(dx * dx + dy * dy) / (2 * 0.16 ** 2))

            for i, (lon, lat) in enumerate(points):
                if metal[i] < 0.01 and work[i] < 0.01:
                    continue
                source_vector = source_contrib[i]
                source_entropy = normalized_entropy(source_vector)
                bundle_entropy = normalized_entropy(bundle_contrib[i])
                top_source = source_ids[int(np.argmax(source_vector))] if source_vector.sum() > 0 else None
                features.append(
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [round(float(lon), 5), round(float(lat), 5)],
                        },
                        "properties": {
                            "date_bc": int(t),
                            "metal_flux_density": round(float(metal[i]), 5),
                            "workshop_density": round(float(work[i]), 5),
                            "source_entropy": round(float(source_entropy), 5),
                            "bundle_entropy": round(float(bundle_entropy), 5),
                            "top_source_truth": top_source,
                        },
                    }
                )
        return {"type": "FeatureCollection", "features": features}

    def jetbundle_geojson(self) -> Dict[str, Any]:
        features = []
        for bundle in self.bundles:
            coordinates = [[self.nodes[node_id].lon, self.nodes[node_id].lat] for node_id in bundle.route]
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": coordinates},
                    "properties": {
                        "bundle_id": bundle.id,
                        "family": bundle.family,
                        "total_tonnes_truth": round(sum(bundle.flux_tonnes.values()), 3),
                        "source_mix_truth": bundle.source_mix,
                    },
                }
            )
        return {"type": "FeatureCollection", "features": features}

    def observed_findspots_geojson(self, selected: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        features = []
        for row in selected:
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [row["findspot"]["lon"], row["findspot"]["lat"]],
                    },
                    "properties": {
                        "object_id": row["object_id"],
                        "name": row["display_name"],
                        "date_center_bc": row["date_center_bc"],
                        "curriculum_level": row["curriculum_level"],
                        "hoard_id": row["hoard_id"],
                        "catalogue_material": row["catalogue_material"],
                    },
                }
            )
        return {"type": "FeatureCollection", "features": features}

    def player_object(self, row: Mapping[str, Any]) -> Dict[str, Any]:
        uncertainty = int(row["date_uncertainty_years"])
        center = int(row["date_center_bc"])
        return {
            "object_id": row["object_id"],
            "curriculum_index": row["curriculum_index"],
            "curriculum_level": row["curriculum_level"],
            "display_name": row["display_name"],
            "class": row["class"],
            "mass_kg": row["mass_kg"],
            "date_range_bc": [center + uncertainty, max(0, center - uncertainty)],
            "findspot": row["findspot"],
            "hoard_id": row["hoard_id"],
            "preservation": row["preservation"],
            "catalogue_material": row["catalogue_material"],
            "available_tests": [
                "xrf",
                "lead_isotopes",
                "metallography",
                "manufacturing_sequence",
                "morphometrics",
            ],
        }

    def analysis_object(self, row: Mapping[str, Any]) -> Dict[str, Any]:
        return {"object_id": row["object_id"], "tests": row["tests"]}

    def truth_object(self, row: Mapping[str, Any]) -> Dict[str, Any]:
        return {
            "object_id": row["object_id"],
            "deposition_mode_truth": row["deposition_mode_truth"],
            "truth": row["truth"],
        }

    def validation_report(
        self,
        selected: Sequence[Mapping[str, Any]],
        generation: Mapping[str, Any],
    ) -> Dict[str, Any]:
        hidden_target = float(self.hypothesis["claim"]["target_tonnes"])
        checkpoint_sum = sum(
            sum(bundle.flux_tonnes.values())
            for bundle in self.bundles
            if self._crosses_checkpoint(bundle)
        )
        bundle_counts = Counter(row["truth"]["bundle_id"] for row in selected)
        lineage_counts = Counter(row["truth"]["lineage_id"] for row in selected)
        classes = Counter(row["class"] for row in selected)
        return {
            "seed": self.seed,
            "checkpoint_mass_balance": {
                "target_tonnes": hidden_target,
                "generated_tonnes": round(checkpoint_sum, 6),
                "absolute_error_tonnes": round(abs(checkpoint_sum - hidden_target), 6),
            },
            "hidden_manufacture_use_events_est": generation["hidden_manufacture_use_events_est"],
            "catalogued_objects": generation["catalogued_objects"],
            "selected_objects": len(selected),
            "selected_unique_bundles": len(bundle_counts),
            "selected_unique_lineages": len(lineage_counts),
            "largest_bundle_share": round(max(bundle_counts.values()) / max(1, len(selected)), 4),
            "class_counts": dict(sorted(classes.items())),
            "anti_spoiler_fields_absent_from_player_export": [
                "target_tonnes",
                "bundle_id",
                "bundle_family",
                "source_mix",
                "workshop_id",
                "lineage_id",
                "route",
                "recycle_fraction",
            ],
        }


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def run(
    hypothesis_path: Path,
    out_dir: Path,
    seed: int = 1300,
    workshop_count: int = 3200,
    catalogue_cap: int = 30000,
    sample_n: int = 300,
) -> Dict[str, Any]:
    hypothesis = json.loads(hypothesis_path.read_text(encoding="utf-8"))
    world = ProvenanceWorld(hypothesis, seed=seed)
    world.build(workshop_count=workshop_count)
    generation = world.generate_archaeological_catalogue(max_materialized=catalogue_cap)
    selected = world.select_curriculum(sample_n, levels=30)

    player = [world.player_object(row) for row in selected]
    analyses = [world.analysis_object(row) for row in selected]
    truth = [world.truth_object(row) for row in selected]
    report = world.validation_report(selected, generation)

    # Player-facing: no scenario target and no true source/bundle/workshop/route.
    write_json(out_dir / "player" / "objects_300.json", player)
    write_json(out_dir / "player" / "analyses_300.json", analyses)
    write_json(out_dir / "player" / "findspots_300.geojson", world.observed_findspots_geojson(selected))

    # Developer-only ground truth. Keep outside site/ when integrating with Pages.
    write_json(out_dir / "debug" / "truth_300.json", truth)
    write_json(out_dir / "debug" / "jetbundles_truth.geojson", world.jetbundle_geojson())
    write_json(out_dir / "debug" / "provenance_field_truth.geojson", world.build_provenance_field())
    write_json(out_dir / "debug" / "validation.json", report)
    write_json(out_dir / "debug" / "generation_summary.json", generation)

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate hidden Atolia provenance field and 300-object archaeology sample."
    )
    parser.add_argument("--hypothesis", default="hypotheses/atolia_atesis_1800_1000_v0.json")
    parser.add_argument("--out-dir", default="out/atolia_provenance_v0")
    parser.add_argument("--seed", type=int, default=1300)
    parser.add_argument("--workshops", type=int, default=3200)
    parser.add_argument("--catalogue-cap", type=int, default=30000)
    parser.add_argument("--sample", type=int, default=300)
    args = parser.parse_args()

    report = run(
        Path(args.hypothesis),
        Path(args.out_dir),
        seed=args.seed,
        workshop_count=args.workshops,
        catalogue_cap=args.catalogue_cap,
        sample_n=args.sample,
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
