from __future__ import annotations

import argparse
import heapq
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import provenance_field as base


ATOLIA_CORE_NODES = {
    "upper_atesis", "merano_gate", "bolzano_confluence", "trento_gate",
    "rovereto_gate", "verona_plain_gate", "legnago_lower_atesis",
    "adriatic_outlet", "trentino_source", "pusteria_gate",
    "po_west", "frattesina", "veneto_lagoon", "friuli_hub",
    "adriatic_north", "adriatic_south", "tyrrhenian_source",
    "ligurian_gate", "eastern_alps_source",
}

EXTENDED_NODES = [
    ("rhone_delta", "Lower Rhone / Mediterranean gate", 4.84, 43.66, "river", 0.82),
    ("rhone_middle", "Middle Rhone corridor", 4.83, 45.05, "river", 0.72),
    ("upper_rhone", "Upper Rhone corridor", 6.05, 46.20, "river", 0.62),
    ("upper_rhine", "Upper Rhine corridor", 7.61, 47.60, "river", 0.72),
    ("middle_rhine", "Middle Rhine corridor", 7.55, 49.85, "river", 0.68),
    ("lower_rhine", "Lower Rhine corridor", 6.75, 51.35, "river", 0.64),
    ("channel_west", "Western Channel exchange gate", -1.60, 49.50, "coast", 0.40),
    ("severn_estuary", "Severn estuary exchange", -2.55, 51.55, "river", 0.55),
    ("severn_middle", "Middle Severn corridor", -2.63, 52.22, "river", 0.48),
    ("great_orme_source", "North Wales copper source proxy", -3.83, 53.33, "source", 0.32),
    ("iberia_east", "Eastern Iberian Mediterranean gate", 0.20, 40.45, "coast", 0.46),
    ("balearic_gate", "Balearic exchange gate", 2.85, 39.55, "coast", 0.34),
    ("sardinia", "Sardinian exchange field", 9.05, 40.05, "coast", 0.46),
    ("sicily", "Sicilian / central Mediterranean gate", 14.05, 37.55, "coast", 0.52),
    ("north_africa_central", "Central North African coast", 10.05, 36.80, "coast", 0.30),
    ("ionian_gate", "Ionian exchange gate", 19.45, 39.50, "coast", 0.52),
    ("aegean_north", "Northern Aegean exchange", 23.45, 40.15, "coast", 0.66),
    ("cyclades", "Cycladic exchange field", 25.00, 37.35, "coast", 0.42),
    ("crete", "Crete exchange field", 25.10, 35.20, "coast", 0.56),
    ("cyprus", "Cyprus copper / exchange field", 33.00, 35.10, "source", 0.72),
    ("levant_north", "Northern Levantine coast", 35.65, 35.35, "coast", 0.45),
    ("nile_delta", "Lower Nile / eastern Mediterranean gate", 31.10, 31.25, "river", 0.36),
    ("hatti_west", "Hatti / central Anatolian interface", 32.10, 39.05, "hub", 0.58),
    ("sava_danube_gate", "Sava–Danube transfer gate", 20.45, 44.80, "river", 0.58),
    ("lower_danube", "Lower Danube corridor", 27.80, 44.20, "river", 0.62),
]

EXTENDED_EDGES = [
    ("ligurian_gate", "rhone_delta", "coast_land", 0.58),
    ("rhone_delta", "rhone_middle", "river_up", 0.62),
    ("rhone_middle", "upper_rhone", "river_up", 0.66),
    ("upper_rhone", "upper_rhine", "jura_alpine_transfer", 1.12),
    ("upper_rhine", "middle_rhine", "river_down", 0.36),
    ("middle_rhine", "lower_rhine", "river_down", 0.34),
    ("lower_rhine", "channel_west", "coast", 0.35),
    ("channel_west", "severn_estuary", "sea", 0.30),
    ("severn_estuary", "severn_middle", "river_up", 0.62),
    ("severn_estuary", "great_orme_source", "coastal_transfer", 0.72),
    ("rhone_delta", "balearic_gate", "sea", 0.24),
    ("iberia_east", "balearic_gate", "sea", 0.24),
    ("balearic_gate", "sardinia", "sea", 0.23),
    ("sardinia", "sicily", "sea", 0.22),
    ("sicily", "north_africa_central", "sea", 0.24),
    ("sicily", "ionian_gate", "sea", 0.22),
    ("adriatic_south", "ionian_gate", "sea", 0.22),
    ("ionian_gate", "aegean_north", "sea", 0.25),
    ("ionian_gate", "crete", "sea", 0.24),
    ("aegean_north", "cyclades", "sea", 0.23),
    ("cyclades", "crete", "sea", 0.21),
    ("crete", "cyprus", "sea", 0.23),
    ("cyprus", "levant_north", "sea", 0.20),
    ("levant_north", "nile_delta", "sea", 0.23),
    ("cyprus", "hatti_west", "anatolian_transfer", 0.72),
    ("aegean_north", "hatti_west", "anatolian_transfer", 0.82),
    ("friuli_hub", "sava_danube_gate", "balkan_transfer", 0.78),
    ("sava_danube_gate", "lower_danube", "river", 0.42),
    ("lower_danube", "aegean_north", "thracian_transfer", 0.74),
    ("upper_atesis", "upper_rhine", "alpine_pass", 1.08),
]

# Deliberately overlapping simulation priors, not claims that these exact
# trace/isotope centroids are measured archaeological source signatures.
EXTENDED_SOURCE_SPECS = [
    ("cyprus_troodos", "Cypriot / Troodos copper family", 33.05, 35.05, 2200, 900, 0.55,
     [300, 105, 720, 80, 50], [18.71, 15.70, 38.73]),
    ("anatolia_aegean", "Aegean–Anatolian copper family", 29.50, 38.50, 2400, 900, 0.38,
     [520, 155, 510, 92, 64], [18.54, 15.68, 38.61]),
    ("lower_danube_balkan", "Lower Danube / Balkan copper family", 25.20, 44.20, 2600, 900, 0.42,
     [410, 175, 930, 120, 52], [18.39, 15.71, 38.70]),
    ("sardinia_westmed", "Sardinian / west Mediterranean copper family", 9.00, 40.10, 2200, 900, 0.26,
     [665, 205, 315, 62, 91], [18.12, 15.64, 38.20]),
    ("iberia_westmed", "Iberian Mediterranean copper family", -0.20, 39.90, 2600, 900, 0.24,
     [790, 245, 360, 58, 105], [18.08, 15.63, 38.16]),
    ("british_wales", "Western Britain copper family", -3.70, 53.10, 2100, 900, 0.22,
     [245, 85, 520, 74, 37], [18.29, 15.67, 38.49]),
    ("central_europe_rhine", "Central European / Rhine-connected copper family", 8.10, 48.60, 2100, 900, 0.28,
     [370, 125, 860, 115, 45], [18.31, 15.69, 38.57]),
    ("western_alps_rhone", "Western Alpine / Rhone-connected copper family", 6.30, 45.90, 2200, 900, 0.30,
     [455, 145, 645, 82, 58], [18.24, 15.67, 38.43]),
]

EXTENDED_FAMILY_SPECS: Dict[str, Dict[str, Any]] = {
    "western_med_tail": {"count": 3, "incidence": 0.10, "source_bias": ["iberia_westmed", "sardinia_westmed"], "origin": "iberia_east", "destinations": ["rhone_delta", "sardinia", "sicily"]},
    "rhone_atolia_tail": {"count": 2, "incidence": 0.12, "source_bias": ["western_alps_rhone", "trentino_east"], "origin": "rhone_delta", "destinations": ["po_west", "frattesina"]},
    "rhine_rhone_tail": {"count": 2, "incidence": 0.075, "source_bias": ["central_europe_rhine", "western_alps_rhone"], "origin": "lower_rhine", "destinations": ["rhone_delta", "upper_atesis"]},
    "severn_continental_tail": {"count": 2, "incidence": 0.045, "source_bias": ["british_wales", "central_europe_rhine"], "origin": "severn_middle", "destinations": ["lower_rhine", "rhone_delta"]},
    "central_med_tail": {"count": 3, "incidence": 0.105, "source_bias": ["sardinia_westmed", "trentino_east", "tyrrhenian_apennine"], "origin": "sicily", "destinations": ["adriatic_south", "crete", "sardinia"]},
    "aegean_adriatic_tail": {"count": 3, "incidence": 0.115, "source_bias": ["anatolia_aegean", "cyprus_troodos", "trentino_east"], "origin": "aegean_north", "destinations": ["adriatic_south", "frattesina", "crete"]},
    "cyprus_aegean_tail": {"count": 2, "incidence": 0.10, "source_bias": ["cyprus_troodos", "anatolia_aegean"], "origin": "cyprus", "destinations": ["crete", "aegean_north", "adriatic_south"]},
    "hatti_aegean_tail": {"count": 2, "incidence": 0.065, "source_bias": ["anatolia_aegean", "cyprus_troodos"], "origin": "hatti_west", "destinations": ["cyprus", "aegean_north"]},
    "lower_danube_tail": {"count": 3, "incidence": 0.09, "source_bias": ["lower_danube_balkan", "eastern_alps_external"], "origin": "lower_danube", "destinations": ["friuli_hub", "adriatic_north", "aegean_north"]},
    "levant_egypt_tail": {"count": 2, "incidence": 0.045, "source_bias": ["cyprus_troodos", "anatolia_aegean"], "origin": "nile_delta", "destinations": ["crete", "cyprus", "levant_north"]},
}

GUILD_EPITHETS = (
    "Split-Mould", "Socket-Rib", "Raised-Sheet", "Anneal-Line",
    "Cold-Edge", "Rivet-Knot", "Repair-Loop", "Surface-Skin",
    "Wire-Ring", "Wax-Branch", "Scrap-Sum", "Fine-Polish",
)

REGION_BY_NODE: Dict[str, str] = {
    **{node: "atolia_core" for node in ATOLIA_CORE_NODES},
    "rhone_delta": "rhone", "rhone_middle": "rhone", "upper_rhone": "rhone",
    "upper_rhine": "rhine", "middle_rhine": "rhine", "lower_rhine": "rhine",
    "channel_west": "severn_britain", "severn_estuary": "severn_britain",
    "severn_middle": "severn_britain", "great_orme_source": "severn_britain",
    "iberia_east": "western_mediterranean", "balearic_gate": "western_mediterranean",
    "sardinia": "western_mediterranean", "sicily": "central_mediterranean",
    "north_africa_central": "central_mediterranean", "ionian_gate": "central_mediterranean",
    "aegean_north": "aegean", "cyclades": "aegean", "crete": "crete",
    "cyprus": "cyprus", "hatti_west": "hatti_anatolia",
    "sava_danube_gate": "lower_danube", "lower_danube": "lower_danube",
    "levant_north": "levant_egypt", "nile_delta": "levant_egypt",
}


class MediterraneanProvenanceWorld(base.ProvenanceWorld):
    """Low-incidence Mediterranean/NW-European extension of the Atolia field."""

    def __init__(self, hypothesis: Mapping[str, Any], seed: int = 1300):
        super().__init__(hypothesis, seed=seed)
        self.bundle_incidence: Dict[str, float] = {}
        self.guilds: Dict[str, Dict[str, Any]] = {}
        self.workshop_guild: Dict[str, str | None] = {}
        self.guild_strength: Dict[str, float] = {}
        self._distance_cache: Dict[Tuple[str, str], float] = {}
        self.extended_source_ids: set[str] = set()

    def _build_graph(self) -> None:
        super()._build_graph()
        for node_id, label, lon, lat, kind, weight in EXTENDED_NODES:
            self.nodes[node_id] = base.Node(node_id, label, lon, lat, kind, weight)
        for a, b, mode, factor in EXTENDED_EDGES:
            self._add_edge(a, b, mode, factor, directed=False)

    def _build_sources(self) -> None:
        super()._build_sources()
        for sid, label, lon, lat, start, end, cap, trace, iso in EXTENDED_SOURCE_SPECS:
            trace_mean = {k: float(v) for k, v in zip(base.TRACE_KEYS, trace)}
            isotope_mean = {k: float(v) for k, v in zip(base.ISO_KEYS, iso)}
            self.sources[sid] = base.SourceField(sid, label, lon, lat, start, end, cap, trace_mean, isotope_mean)
            self.extended_source_ids.add(sid)

    def _build_jetbundles(self) -> None:
        super()._build_jetbundles()
        for bundle in self.bundles:
            self.bundle_incidence[bundle.id] = 1.0
            mix = dict(bundle.source_mix)
            for source_id in self.extended_source_ids:
                if source_id in mix:
                    mix[source_id] *= 0.06
            total = sum(mix.values())
            if total > 0:
                bundle.source_mix = {k: v / total for k, v in mix.items() if v / total > 0.001}

        bundle_no = len(self.bundles)
        all_source_ids = list(self.sources)
        atolia_sources = {
            "trentino_east", "upper_atesis", "veneto_pre_alps", "eastern_alps_external",
            "tyrrhenian_apennine", "ligurian_tuscany", "balkan_import",
        }
        for family, spec in EXTENDED_FAMILY_SPECS.items():
            for _ in range(int(spec["count"])):
                bundle_no += 1
                origin = str(spec["origin"])
                destination = str(self.rng.choice(spec["destinations"]))
                route = self._route(origin, destination, jitter=0.28)
                bias = set(spec["source_bias"])
                alpha = np.array([2.8 if sid in bias else 0.48 if sid in atolia_sources else 0.14 for sid in all_source_ids], dtype=float)
                arr = self.rng.dirichlet(alpha)
                source_mix = {sid: float(v) for sid, v in zip(all_source_ids, arr) if v > 0.002}
                bundle = base.JetBundle(
                    id=f"JB-{bundle_no:03d}", family=family, origin=origin, destination=destination,
                    route=route, source_mix=source_mix,
                    technical_affinity=base.random_simplex(self.rng, 6, concentration=0.72),
                    symbolic_affinity=base.random_simplex(self.rng, 5, concentration=0.50),
                    recycle_mean=float(np.clip(self.rng.normal(0.52, 0.14), 0.08, 0.90)), flux_tonnes={},
                )
                self.bundles.append(bundle)
                self.bundle_incidence[bundle.id] = float(spec["incidence"])

    def _allocate_hidden_flux(self) -> None:
        crossing = [b for b in self.bundles if self._crosses_checkpoint(b)]
        noncross_core = [b for b in self.bundles if not self._crosses_checkpoint(b) and self.bundle_incidence.get(b.id, 1.0) >= 0.5]
        noncross_tail = [b for b in self.bundles if not self._crosses_checkpoint(b) and self.bundle_incidence.get(b.id, 1.0) < 0.5]
        if not crossing:
            raise RuntimeError("No jetbundle crosses the hidden checkpoint.")
        for t in self.time_slices:
            target = self._slice_target(t)
            if target <= 0:
                continue
            raw = np.array([
                self._bundle_active_weight(b, t) * self.bundle_incidence.get(b.id, 1.0) * self.rng.lognormal(0.0, 0.22)
                for b in crossing
            ], dtype=float)
            raw /= raw.sum()
            for bundle, weight in zip(crossing, raw):
                bundle.flux_tonnes[t] = float(target * weight)
            self._allocate_free_group(noncross_core, t, target * float(self.rng.uniform(0.24, 0.58)), noise=0.34)
            self._allocate_free_group(noncross_tail, t, target * float(self.rng.uniform(0.045, 0.145)), noise=0.46)

    def _allocate_free_group(self, bundles: Sequence[base.JetBundle], t: int, total: float, noise: float) -> None:
        if not bundles or total <= 0:
            return
        raw = np.array([
            self._bundle_active_weight(b, t) * self.bundle_incidence.get(b.id, 1.0) * self.rng.lognormal(0.0, noise)
            for b in bundles
        ], dtype=float)
        if raw.sum() <= 0:
            return
        raw /= raw.sum()
        for bundle, weight in zip(bundles, raw):
            bundle.flux_tonnes[t] = float(total * weight)

    def _build_workshops(self, count: int) -> None:
        super()._build_workshops(count)
        self._build_guilds()

    def _shortest_distance(self, start: str, goal: str) -> float:
        key = (start, goal)
        if key in self._distance_cache:
            return self._distance_cache[key]
        queue: List[Tuple[float, str]] = [(0.0, start)]
        best = {start: 0.0}
        while queue:
            d, node = heapq.heappop(queue)
            if node == goal:
                self._distance_cache[key] = d
                self._distance_cache[(goal, start)] = d
                return d
            if d != best.get(node):
                continue
            for nxt, cost in self._neighbors(node):
                nd = d + cost
                if nd < best.get(nxt, float("inf")):
                    best[nxt] = nd
                    heapq.heappush(queue, (nd, nxt))
        return float("inf")

    def _distance_to_core(self, node_id: str) -> float:
        return min(self._shortest_distance(node_id, core) for core in ATOLIA_CORE_NODES)

    @staticmethod
    def _cosine(a: np.ndarray, b: np.ndarray) -> float:
        denom = float(np.linalg.norm(a) * np.linalg.norm(b))
        return 0.0 if denom <= 0 else float(np.dot(a, b) / denom)

    def _build_guilds(self) -> None:
        core_workshops = [w for w in self.workshops if w.node_id in ATOLIA_CORE_NODES]
        if len(core_workshops) < 36:
            core_workshops = list(self.workshops)
        shuffled = list(core_workshops)
        self.rng.shuffle(shuffled)

        for i, epithet in enumerate(GUILD_EPITHETS):
            start = (i * 3) % len(shuffled)
            seeds = shuffled[start:start + 3]
            if len(seeds) < 3:
                seeds = list(self.rng.choice(core_workshops, size=3, replace=False))
            prototype = np.mean([w.technical_vector for w in seeds], axis=0)
            prototype = np.clip(prototype + self.rng.normal(0, 0.018, size=6), 1e-5, None)
            prototype /= prototype.sum()
            anchor = str(self.rng.choice(sorted(ATOLIA_CORE_NODES)))
            guild_id = f"G-{i + 1:02d}"
            self.guilds[guild_id] = {
                "epithet": epithet,
                "anchor_node": anchor,
                "prototype": prototype,
                "mobility_scale": float(self.rng.uniform(190.0, 520.0)),
                "core_seed_workshops": [w.id for w in seeds],
            }
            for workshop in seeds:
                self.workshop_guild[workshop.id] = guild_id
                self.guild_strength[workshop.id] = 1.0

        extended_route_nodes = {
            node_id for bundle in self.bundles if self.bundle_incidence.get(bundle.id, 1.0) < 0.5 for node_id in bundle.route
        }
        for workshop in self.workshops:
            if workshop.id in self.workshop_guild:
                continue
            region = REGION_BY_NODE.get(workshop.node_id, "other")
            d_core = self._distance_to_core(workshop.node_id)
            p_any = 0.08 + 0.58 * math.exp(-d_core / 250.0)
            if region != "atolia_core":
                p_any *= 0.52
            if workshop.node_id in extended_route_nodes:
                p_any += 0.045
            p_any = float(np.clip(p_any, 0.055, 0.76))
            if self.rng.random() > p_any:
                self.workshop_guild[workshop.id] = None
                self.guild_strength[workshop.id] = 0.0
                continue

            ids = list(self.guilds)
            scores = []
            for guild_id in ids:
                guild = self.guilds[guild_id]
                sim = self._cosine(workshop.technical_vector, guild["prototype"])
                d_anchor = self._shortest_distance(workshop.node_id, guild["anchor_node"])
                spatial = math.exp(-d_anchor / guild["mobility_scale"])
                scores.append(3.0 * sim + 0.9 * spatial + self.rng.normal(0, 0.12))
            scores_arr = np.asarray(scores, dtype=float)
            scores_arr -= scores_arr.max()
            probs = np.exp(scores_arr / 0.45)
            probs /= probs.sum()
            guild_id = str(self.rng.choice(ids, p=probs))
            strength = float(np.clip((max(scores) - 1.4) / 2.2, 0.10, 0.95))
            self.workshop_guild[workshop.id] = guild_id
            self.guild_strength[workshop.id] = strength

    def _class_weights(self, date_bc: int, bundle: base.JetBundle):
        classes, weights = super()._class_weights(date_bc, bundle)
        if self.bundle_incidence.get(bundle.id, 1.0) >= 0.5:
            return classes, weights
        arr = np.array(weights, dtype=float)
        for i, object_class in enumerate(classes):
            if object_class in {"ornament", "dagger", "sword", "vessel", "ingot", "spearhead"}:
                arr[i] *= 1.35
            if object_class in {"scrap", "fitting"}:
                arr[i] *= 0.72
        arr /= arr.sum()
        return classes, arr

    def _materialize_object(self, object_no: int, object_class: str, bundle: base.JetBundle, date_bc: int, workshop: base.Workshop, dep_node: base.Node) -> Dict[str, Any]:
        row = super()._materialize_object(object_no, object_class, bundle, date_bc, workshop, dep_node)
        guild_id = self.workshop_guild.get(workshop.id)
        row["truth"]["guild_id"] = guild_id
        row["truth"]["guild_strength"] = round(self.guild_strength.get(workshop.id, 0.0), 4)
        row["truth"]["macro_region"] = REGION_BY_NODE.get(dep_node.id, "other")
        row["truth"]["long_distance_tail"] = self.bundle_incidence.get(bundle.id, 1.0) < 0.5
        return row

    def select_curriculum(self, n: int = 300, levels: int = 30) -> List[Dict[str, Any]]:
        selected = super().select_curriculum(n=n, levels=levels)
        if n != 300 or levels != 30:
            return selected
        selected_ids = {row["object_id"] for row in selected}
        peripheral_pool = [
            row for row in self.catalogue_truth
            if row["object_id"] not in selected_ids and row["truth"].get("macro_region") != "atolia_core"
        ]
        target_peripheral = min(22, max(16, int(round(n * 0.065))))
        current_peripheral = sum(row["truth"].get("macro_region") != "atolia_core" for row in selected)

        def replacement_index(candidate: Mapping[str, Any], require_core: bool = True) -> int | None:
            eligible = []
            for i, row in enumerate(selected):
                if row["curriculum_level"] <= 4 or row["curriculum_level"] == 30:
                    continue
                if require_core and row["truth"].get("macro_region") != "atolia_core":
                    continue
                delta = abs(float(row["truth"]["complexity"]) - float(candidate["truth"]["complexity"]))
                eligible.append((delta, i))
            return min(eligible)[1] if eligible else None

        self.rng.shuffle(peripheral_pool)
        while current_peripheral < target_peripheral and peripheral_pool:
            candidate = peripheral_pool.pop()
            idx = replacement_index(candidate, require_core=True)
            if idx is None:
                break
            level = selected[idx]["curriculum_level"]
            index = selected[idx]["curriculum_index"]
            out = dict(candidate)
            out["curriculum_level"] = level
            out["curriculum_index"] = index
            selected[idx] = out
            selected_ids.add(out["object_id"])
            current_peripheral += 1

        represented = {row["truth"].get("guild_id") for row in selected if row["truth"].get("guild_id")}
        for guild_id in [gid for gid in self.guilds if gid not in represented]:
            candidates = [row for row in self.catalogue_truth if row["object_id"] not in selected_ids and row["truth"].get("guild_id") == guild_id]
            if not candidates:
                continue
            candidate = min(candidates, key=lambda row: abs(float(row["truth"]["complexity"]) - 0.58))
            idx = replacement_index(candidate, require_core=False)
            if idx is None:
                continue
            level = selected[idx]["curriculum_level"]
            index = selected[idx]["curriculum_index"]
            out = dict(candidate)
            out["curriculum_level"] = level
            out["curriculum_index"] = index
            selected_ids.add(out["object_id"])
            selected[idx] = out
        return sorted(selected, key=lambda row: row["curriculum_index"])

    def guild_truth(self) -> Dict[str, Any]:
        counts = Counter(self.workshop_guild.values())
        periphery = Counter()
        for workshop in self.workshops:
            guild_id = self.workshop_guild.get(workshop.id)
            if guild_id and REGION_BY_NODE.get(workshop.node_id, "other") != "atolia_core":
                periphery[guild_id] += 1
        return {
            "guilds": [
                {
                    "guild_id": guild_id,
                    "developer_epithet": guild["epithet"],
                    "atolia_core_anchor": guild["anchor_node"],
                    "mobility_scale": round(float(guild["mobility_scale"]), 3),
                    "technical_prototype": [round(float(x), 5) for x in guild["prototype"]],
                    "core_seed_workshops": guild["core_seed_workshops"],
                    "total_workshops": int(counts.get(guild_id, 0)),
                    "peripheral_workshops": int(periphery.get(guild_id, 0)),
                }
                for guild_id, guild in self.guilds.items()
            ]
        }

    def validation_report(self, selected: Sequence[Mapping[str, Any]], generation: Mapping[str, Any]) -> Dict[str, Any]:
        report = super().validation_report(selected, generation)
        guild_counts = Counter(row["truth"].get("guild_id") for row in selected if row["truth"].get("guild_id"))
        region_counts = Counter(row["truth"].get("macro_region", "other") for row in selected)
        tail_total = sum(sum(bundle.flux_tonnes.values()) for bundle in self.bundles if self.bundle_incidence.get(bundle.id, 1.0) < 0.5)
        core_checkpoint = report["checkpoint_mass_balance"]["generated_tonnes"]
        report["extended_network"] = {
            "regions_in_sample": dict(sorted(region_counts.items())),
            "peripheral_sample_share": round(1.0 - region_counts.get("atolia_core", 0) / max(1, len(selected)), 4),
            "tail_flux_tonnes_truth": round(float(tail_total), 3),
            "tail_to_checkpoint_ratio_truth": round(float(tail_total / max(core_checkpoint, 1e-9)), 4),
            "guilds_defined": len(self.guilds),
            "guilds_represented_in_sample": len(guild_counts),
            "guild_sample_counts_truth": dict(sorted(guild_counts.items())),
        }
        forbidden = report["anti_spoiler_fields_absent_from_player_export"]
        for key in ("guild_id", "guild_strength", "macro_region", "long_distance_tail"):
            if key not in forbidden:
                forbidden.append(key)
        return report


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def run(hypothesis_path: Path, out_dir: Path, seed: int = 1300, workshop_count: int = 3200, catalogue_cap: int = 30000, sample_n: int = 300) -> Dict[str, Any]:
    hypothesis = json.loads(hypothesis_path.read_text(encoding="utf-8"))
    world = MediterraneanProvenanceWorld(hypothesis, seed=seed)
    world.build(workshop_count=workshop_count)
    generation = world.generate_archaeological_catalogue(max_materialized=catalogue_cap)
    selected = world.select_curriculum(sample_n, levels=30)
    player = [world.player_object(row) for row in selected]
    analyses = [world.analysis_object(row) for row in selected]
    truth = [world.truth_object(row) for row in selected]
    report = world.validation_report(selected, generation)
    write_json(out_dir / "player" / "objects_300.json", player)
    write_json(out_dir / "player" / "analyses_300.json", analyses)
    write_json(out_dir / "player" / "findspots_300.geojson", world.observed_findspots_geojson(selected))
    write_json(out_dir / "debug" / "truth_300.json", truth)
    write_json(out_dir / "debug" / "jetbundles_truth.geojson", world.jetbundle_geojson())
    write_json(out_dir / "debug" / "provenance_field_truth.geojson", world.build_provenance_field(grid_deg=0.48))
    write_json(out_dir / "debug" / "guilds_truth.json", world.guild_truth())
    write_json(out_dir / "debug" / "validation.json", report)
    write_json(out_dir / "debug" / "generation_summary.json", generation)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate extended hidden Atolia provenance field with low-incidence Mediterranean tails.")
    parser.add_argument("--hypothesis", default="hypotheses/atolia_atesis_1800_1000_v0.json")
    parser.add_argument("--out-dir", default="out/atolia_provenance_mediterranean_v0")
    parser.add_argument("--seed", type=int, default=1300)
    parser.add_argument("--workshops", type=int, default=3200)
    parser.add_argument("--catalogue-cap", type=int, default=30000)
    parser.add_argument("--sample", type=int, default=300)
    args = parser.parse_args()
    report = run(Path(args.hypothesis), Path(args.out_dir), seed=args.seed, workshop_count=args.workshops, catalogue_cap=args.catalogue_cap, sample_n=args.sample)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
