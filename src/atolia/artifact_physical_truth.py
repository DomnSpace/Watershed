from __future__ import annotations

import hashlib
import heapq
import math
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple

import numpy as np

import guild_model
import provenance_field as base
import provenance_field_mediterranean as med


ARTIFACT_TRUTH_VERSION = "atolia-artifact-physical-truth-v1"

# Geometry priors are intentionally broad. Dimensions are reconciled with sampled
# mass/bronze density, so they are not independent decorative labels.
SHAPE_PRIORS: Dict[str, Dict[str, float]] = {
    "bead": {"length": 15, "width": 12, "fill": .66},
    "awl": {"length": 115, "width": 8, "fill": .42},
    "pin": {"length": 155, "width": 7, "fill": .34},
    "ring": {"length": 65, "width": 60, "fill": .20},
    "fitting": {"length": 70, "width": 35, "fill": .46},
    "knife": {"length": 220, "width": 35, "fill": .50},
    "sickle": {"length": 310, "width": 58, "fill": .35},
    "chisel": {"length": 145, "width": 24, "fill": .64},
    "axe": {"length": 165, "width": 85, "fill": .62},
    "spearhead": {"length": 260, "width": 55, "fill": .42},
    "dagger": {"length": 310, "width": 48, "fill": .43},
    "sword": {"length": 710, "width": 55, "fill": .40},
    "vessel": {"length": 260, "width": 260, "fill": .09},
    "ornament": {"length": 80, "width": 45, "fill": .28},
    "figurine": {"length": 160, "width": 70, "fill": .38},
    "ingot": {"length": 280, "width": 170, "fill": .72},
    "scrap": {"length": 75, "width": 55, "fill": .58},
}

EDGE_CLASSES = {"knife", "sickle", "chisel", "axe", "spearhead", "dagger", "sword", "awl"}
PRESTIGE_CLASSES = {"sword", "dagger", "ornament", "figurine", "vessel", "spearhead"}


def _seed64(*parts: Any) -> int:
    raw = "|".join(str(x) for x in parts)
    return int.from_bytes(hashlib.sha256(raw.encode("utf-8")).digest()[:8], "big")


def stable_rng(seed: int, *parts: Any) -> np.random.Generator:
    return np.random.default_rng(_seed64(seed, *parts))


def _entropy(mix: Mapping[str, float]) -> float:
    a = np.asarray([float(v) for v in mix.values() if float(v) > 0], dtype=float)
    if len(a) <= 1:
        return 0.0
    a /= a.sum()
    return float(-np.sum(a * np.log(a)) / math.log(len(a)))


def _node_payload(world: Any, node_id: str, *, lon: float | None = None, lat: float | None = None) -> Dict[str, Any]:
    node = world.nodes[node_id]
    return {
        "node_id": node_id,
        "label": str(node.label),
        "region": med.REGION_BY_NODE.get(node_id, "other"),
        "kind": str(node.kind),
        "lon": round(float(node.lon if lon is None else lon), 6),
        "lat": round(float(node.lat if lat is None else lat), 6),
    }


def _active_workshops(world: Any, date_bc: int) -> List[Any]:
    return [w for w in getattr(world, "workshops", ()) if int(w.end_bc) <= int(date_bc) <= int(w.start_bc)]


def choose_actual_workshop(world: Any, origin_node: str, date_bc: int, rng: np.random.Generator) -> Any:
    """Choose an actual world workshop; never synthesize a hash-only guild placeholder."""
    workshops = list(getattr(world, "workshops", ()))
    if not workshops:
        raise RuntimeError("Rich artifact truth requires world.build(...): no workshops exist")
    active = _active_workshops(world, date_bc) or workshops
    exact = [w for w in active if w.node_id == origin_node]
    if exact:
        weights = np.asarray([max(.01, float(w.capacity_weight)) for w in exact], dtype=float)
        weights /= weights.sum()
        return exact[int(rng.choice(len(exact), p=weights))]
    origin = world.nodes[origin_node]
    origin_region = med.REGION_BY_NODE.get(origin_node, "other")
    same_region = [w for w in active if med.REGION_BY_NODE.get(w.node_id, "other") == origin_region]
    pool = same_region or active
    d = np.asarray([
        base.haversine_km(origin.lon, origin.lat, w.lon, w.lat) for w in pool
    ], dtype=float)
    cap = np.asarray([max(.01, float(w.capacity_weight)) for w in pool], dtype=float)
    scale = 90.0 if same_region else 240.0
    weights = np.exp(-d / scale) * np.sqrt(cap)
    weights /= weights.sum()
    return pool[int(rng.choice(len(pool), p=weights))]


def _workshop_by_id(world: Any, workshop_id: str | None) -> Any | None:
    if not workshop_id:
        return None
    return next((w for w in getattr(world, "workshops", ()) if w.id == workshop_id), None)


def _bundle_by_id(world: Any, bundle_id: str | None) -> Any | None:
    if not bundle_id:
        return None
    return next((b for b in getattr(world, "bundles", ()) if str(b.id) == str(bundle_id)), None)


def _weighted_source_truth(
    world: Any,
    source_mix: Mapping[str, float],
    recycle_count: int,
    rng: np.random.Generator,
) -> Tuple[Dict[str, float], Dict[str, float]]:
    known = [(sid, float(w)) for sid, w in source_mix.items() if sid in getattr(world, "sources", {}) and float(w) > 0]
    if not known:
        # Keep the object physically defined even for an externally recycled component,
        # but do not invent a named ore source.
        trace = {k: float(rng.lognormal(math.log(300.0), .75)) for k in base.TRACE_KEYS}
        isotopes = {"Pb206_204": float(rng.normal(18.35, .22)), "Pb207_204": float(rng.normal(15.67, .055)), "Pb208_204": float(rng.normal(38.48, .32))}
        return trace, isotopes
    total = sum(w for _, w in known)
    known = [(sid, w / total) for sid, w in known]
    hetero = .08 + .025 * min(5, recycle_count)
    trace: Dict[str, float] = {}
    isotopes: Dict[str, float] = {}
    for key in base.TRACE_KEYS:
        mu = sum(w * float(world.sources[sid].trace_mean[key]) for sid, w in known)
        trace[key] = float(max(0.0, rng.lognormal(math.log(max(1.0, mu)), hetero)))
    for key in base.ISO_KEYS:
        mu = sum(w * float(world.sources[sid].isotope_mean[key]) for sid, w in known)
        isotopes[key] = float(rng.normal(mu, .006 + .0025 * min(4, recycle_count)))
    return trace, isotopes


def _bulk_alloy(object_class: str, date_bc: int, recycle_count: int, rng: np.random.Generator) -> Dict[str, float]:
    late = float(np.clip((1800.0 - date_bc) / 800.0, 0, 1))
    status = float(base.OBJECT_CLASSES.get(object_class, {"status": .4})["status"])
    edge = float(object_class in EDGE_CLASSES)
    tin_probability = np.clip(.28 + .48 * late + .16 * edge + .08 * status, .15, .96)
    if rng.random() < tin_probability:
        sn = float(np.clip(rng.normal(7.8 + 2.1 * edge + 1.4 * status, 2.2 + .25 * recycle_count), 1.5, 16.5))
        arsenic = float(np.clip(rng.lognormal(math.log(.20 + .08 * recycle_count), .58), .015, 2.5))
        lead = float(np.clip(rng.lognormal(math.log(.16 + .25 * late + .08 * recycle_count), .72), .005, 5.5))
    else:
        sn = float(np.clip(rng.lognormal(math.log(.15 + .04 * recycle_count), .72), 0, 1.5))
        arsenic = float(np.clip(rng.lognormal(math.log(.65 + .10 * recycle_count), .66), .03, 4.8))
        lead = float(np.clip(rng.lognormal(math.log(.08 + .04 * recycle_count), .80), 0, 2.0))
    # Minor Fe/Zn are physical batch impurities, not separate source labels.
    fe = float(np.clip(rng.lognormal(math.log(.08), .65), .005, .8))
    zn = float(np.clip(rng.lognormal(math.log(.035), .75), .001, .5))
    cu = max(68.0, 100.0 - sn - arsenic - lead - fe - zn)
    values = {"Cu": cu, "Sn": sn, "As": arsenic, "Pb": lead, "Fe": fe, "Zn": zn}
    total = sum(values.values())
    return {k: round(100.0 * v / total, 5) for k, v in values.items()}


def _dimensions(object_class: str, mass_kg: float, rng: np.random.Generator) -> Dict[str, float]:
    prior = SHAPE_PRIORS.get(object_class, SHAPE_PRIORS["fitting"])
    length = float(prior["length"] * rng.lognormal(0, .13))
    width = float(prior["width"] * rng.lognormal(0, .15))
    # rho ~ 8.5 g/cm3 = 8.5e-6 kg/mm3. Fill accounts for curved/bladed/hollow geometry.
    rho = 8.50e-6
    fill = float(np.clip(prior["fill"] * rng.lognormal(0, .10), .06, .90))
    thickness = mass_kg / max(1e-9, rho * length * width * fill)
    thickness = float(np.clip(thickness, .5, 85.0))
    return {
        "length_mm": round(length, 2),
        "width_mm": round(width, 2),
        "thickness_mm": round(thickness, 2),
        "shape_fill_fraction": round(fill, 4),
    }


def _guild_and_manufacture(world: Any, workshop: Any, object_class: str, recycle_count: int,
                           repair_count: int, alloy: Mapping[str, float], rng: np.random.Generator) -> Dict[str, Any]:
    affinities = guild_model.workshop_affinities(world, workshop)
    primary = max(affinities, key=affinities.get) if affinities else None
    profile = guild_model.GUILD_PROFILES.get(primary) if primary else None
    ops: List[str] = ["batching"]
    cast = object_class in {"axe", "spearhead", "dagger", "sword", "figurine", "fitting", "ingot", "scrap"}
    if cast:
        ops += ["moulding", "casting"]
    elif object_class in {"vessel", "ornament"}:
        ops += ["casting", "deformation", "sheetwork"]
    else:
        ops += ["casting", "deformation"]
    if profile:
        ranked = sorted(profile.operations.items(), key=lambda kv: -kv[1])
        for op, strength in ranked[:5]:
            if strength >= .38 and op not in ops and rng.random() < .45 + .45 * strength:
                ops.append(op)
    if object_class in EDGE_CLASSES and "edge_treatment" not in ops:
        ops.append("edge_treatment")
    if recycle_count and "recycling" not in ops:
        ops.append("recycling")
    if repair_count and "repair" not in ops:
        ops.append("repair")
    if "finishing" not in ops:
        ops.append("finishing")

    tv = np.asarray(workshop.technical_vector, dtype=float)
    cast_strength = float(tv[0]) if len(tv) else .16
    anneal = float(tv[2]) if len(tv) > 2 else .16
    cold = float(tv[3]) if len(tv) > 3 else .16
    sn = float(alloy.get("Sn", 8.0))
    dendrite_spacing = float(np.clip(rng.lognormal(math.log(55.0 + 55.0 * cast_strength), .28) * (1.0 - .28 * anneal), 12, 240))
    grain_size = float(np.clip(rng.lognormal(math.log(42.0 + 45.0 * (1.0 - anneal)), .27), 8, 190))
    cold_work = float(np.clip(.18 + 1.35 * cold - .52 * anneal + rng.normal(0, .08), 0, .92))
    recrystallized = float(np.clip(.12 + 1.20 * anneal - .48 * cold + rng.normal(0, .08), 0, .95))
    porosity = float(np.clip(rng.beta(1.4, 15) * (1.15 if cast else .65), .0005, .18))
    hardness = float(np.clip(52 + 4.0 * sn + 48 * cold_work - 18 * recrystallized + rng.normal(0, 7), 45, 190))
    return {
        "workshop_id": workshop.id,
        "workshop_node_id": workshop.node_id,
        "workshop_site": _node_payload(world, workshop.node_id, lon=workshop.lon, lat=workshop.lat),
        "lineage_id": workshop.lineage_id,
        "workers": int(workshop.workers),
        "technical_vector": [round(float(v), 6) for v in workshop.technical_vector],
        "guild_affinities": {k: round(float(v), 5) for k, v in affinities.items()},
        "primary_guild_id": primary,
        "primary_guild_developer_name": profile.developer_name if profile else None,
        "operations": list(dict.fromkeys(ops)),
        "microstructure": {
            "grain_size_um": round(grain_size, 2),
            "dendrite_arm_spacing_um": round(dendrite_spacing, 2),
            "porosity_fraction": round(porosity, 5),
            "cold_work_fraction": round(cold_work, 5),
            "recrystallized_fraction": round(recrystallized, 5),
            "hardness_hv": round(hardness, 2),
        },
    }


def _adjacency(world: Any) -> Dict[str, List[Tuple[str, Any]]]:
    out: Dict[str, List[Tuple[str, Any]]] = {n: [] for n in world.nodes}
    for e in world.edges:
        out[e.a].append((e.b, e))
        if not e.directed:
            out[e.b].append((e.a, e))
    return out


def shortest_physical_path(world: Any, start: str, goal: str) -> List[str]:
    if start == goal:
        return [start]
    cache = getattr(world, "_artifact_truth_path_cache", None)
    if cache is None:
        cache = {}
        setattr(world, "_artifact_truth_path_cache", cache)
    key = (start, goal)
    if key in cache:
        return list(cache[key])
    adj = _adjacency(world)
    dist = {start: 0.0}; prev: Dict[str, str] = {}; q = [(0.0, start)]
    while q:
        d, cur = heapq.heappop(q)
        if d != dist.get(cur):
            continue
        if cur == goal:
            break
        for nxt, e in adj.get(cur, ()):
            nd = d + max(.001, float(e.cost))
            if nd < dist.get(nxt, float("inf")):
                dist[nxt] = nd; prev[nxt] = cur; heapq.heappush(q, (nd, nxt))
    if goal not in dist:
        path = [start, goal]
    else:
        path = [goal]
        while path[-1] != start:
            path.append(prev[path[-1]])
        path.reverse()
    cache[key] = tuple(path)
    return path


def _usage_timeline(world: Any, route_nodes: Sequence[str], production_bc: int, object_class: str,
                    repair_count: int, loss_node: str, rng: np.random.Generator) -> Dict[str, Any]:
    prestige = object_class in PRESTIGE_CLASSES
    life_years = int(np.clip(rng.lognormal(math.log(11 if prestige else 7), .70), 1, 55))
    loss_bc = max(950, int(production_bc - life_years))
    path = [n for n in route_nodes if n in world.nodes]
    if not path:
        path = [loss_node]
    if path[-1] != loss_node:
        extra = shortest_physical_path(world, path[-1], loss_node)
        path = path + extra[1:]
    indices = sorted(set(np.linspace(0, max(0, len(path) - 1), min(5, max(2, len(path))), dtype=int).tolist()))
    events = []
    for idx_no, idx in enumerate(indices):
        f = idx_no / max(1, len(indices) - 1)
        date = int(round(production_bc - f * life_years))
        site = _node_payload(world, path[idx])
        events.append({
            "date_bc": date,
            "node_id": path[idx],
            "site": site,
            "activity": "production/use" if idx_no == 0 else "use/transfer" if idx_no < len(indices) - 1 else "final use",
        })
    repair_events = []
    for i in range(repair_count):
        f = float(rng.uniform(.18, .88))
        idx = min(len(path) - 1, int(round(f * (len(path) - 1))))
        repair_events.append({
            "date_bc": int(round(production_bc - f * life_years)),
            "node_id": path[idx],
            "site": _node_payload(world, path[idx]),
            "operation": str(rng.choice(["edge reworking", "local straightening", "patch/join repair", "surface refinishing"])),
        })
    return {
        "production_bc": int(production_bc),
        "use_life_years": int(life_years),
        "usage_events": events,
        "repair_events": sorted(repair_events, key=lambda e: -e["date_bc"]),
        "loss_bc": int(loss_bc),
        "route_nodes_representative": list(path),
    }


def _burial_environment(world: Any, loss_node: str, deposition_mode: str, loss_bc: int,
                        discovery_year: int, rng: np.random.Generator) -> Dict[str, float | str]:
    node = world.nodes[loss_node]
    wet = deposition_mode == "river_wetland_deposit" or node.kind in {"river", "coast"}
    coastal = node.kind == "coast" or "coast" in str(node.kind)
    workshop = deposition_mode == "workshop_debris"
    saturation = float(np.clip(rng.beta(5.0, 2.0) if wet else rng.beta(2.2, 4.5), .03, .99))
    chloride = float(np.clip(rng.lognormal(math.log(220 if coastal else 75 if wet else 35), .72), 2, 3200))
    pH = float(np.clip(rng.normal(7.25 if wet else 7.55, .65), 5.2, 9.1))
    redox = float(np.clip(rng.normal(-35 if wet else 145, 95), -280, 420))
    carbonate = float(np.clip(rng.beta(2.5, 2.5), .02, .98))
    porosity = float(np.clip(rng.beta(2.7, 3.2), .08, .86))
    organic = float(np.clip(rng.beta(2.2, 5.0) * (1.7 if wet else 1.0), 0, 1))
    if workshop:
        chloride *= .78; saturation *= .78
    burial_years = max(100.0, float(loss_bc + discovery_year - 1))
    return {
        "environment_class": "waterlogged" if saturation > .72 else "seasonally_wet" if saturation > .42 else "aerated_soil",
        "pH": round(pH, 3),
        "chloride_mg_per_kg": round(chloride, 2),
        "water_saturation_fraction": round(saturation, 5),
        "redox_mV": round(redox, 1),
        "carbonate_index": round(carbonate, 5),
        "soil_porosity": round(porosity, 5),
        "organic_index": round(organic, 5),
        "burial_years": round(burial_years, 1),
    }


def _corrosion_state(alloy: Mapping[str, float], env: Mapping[str, Any], dimensions: Mapping[str, float],
                     rng: np.random.Generator) -> Dict[str, Any]:
    years = float(env["burial_years"])
    sat = float(env["water_saturation_fraction"])
    chloride = float(env["chloride_mg_per_kg"])
    pH = float(env["pH"])
    redox = float(env["redox_mV"])
    carbonate = float(env["carbonate_index"])
    sn = float(alloy.get("Sn", 0.0))
    cl = float(np.clip(math.log1p(chloride) / math.log(3201), 0, 1))
    oxygen = float(np.clip((redox + 280) / 700, 0, 1))
    passive = 72.0 * math.sqrt(max(1.0, years) / 1000.0) * (0.70 + .70 * sat + .20 * carbonate)
    active = 780.0 * max(0.0, cl - .47) ** 1.55 * (.38 + .62 * sat) * (.35 + .65 * oxygen)
    thickness = float(np.clip((passive + active) * rng.lognormal(0, .28), 35, 4200))
    pit_p50 = float(np.clip(thickness * rng.lognormal(math.log(.65), .34), 10, 5000))
    pit_p95 = float(np.clip(pit_p50 * rng.lognormal(math.log(2.2), .28), pit_p50, 9000))
    characteristic = max(500.0, 1000.0 * float(dimensions["thickness_mm"]))
    metal_loss = float(np.clip(.12 * thickness / characteristic + .10 * pit_p95 / characteristic, .001, .88))
    bronze_disease_z = -4.4 + 5.2 * cl + 1.15 * sat + .85 * oxygen - .50 * carbonate - .22 * max(0, pH - 7.5)
    bronze_disease = float(1.0 / (1.0 + math.exp(-bronze_disease_z)))

    raw = {
        "cuprite": 1.10 + .75 * (1 - sat) + .35 * oxygen,
        "malachite": .18 + 1.25 * carbonate * oxygen * (1 - .35 * sat),
        "tenorite": .10 + .40 * oxygen * (1 - sat),
        "nantokite": .04 + 1.55 * cl * sat * (1 - .45 * oxygen),
        "atacamite_paratacamite": .05 + 1.45 * cl * (.30 + .70 * oxygen) * (.25 + .75 * sat),
        "tin_oxide": .05 + .055 * sn * (.45 + .55 * oxygen),
        "soil_encrustation": .22 + .55 * float(env["soil_porosity"]) + .25 * float(env["organic_index"]),
    }
    phase_total = sum(raw.values())
    phases = {k: round(v / phase_total, 6) for k, v in raw.items()}

    # Surface XRF is a forward-view state, not the hidden bulk alloy. Tin is often
    # enriched in altered layers; chloride/soil products also suppress apparent Cu.
    enrich_sn = 1.0 + 1.8 * metal_loss + .9 * phases["tin_oxide"]
    suppress_cu = max(.18, 1.0 - .72 * metal_loss - .30 * phases["soil_encrustation"])
    surface_metals = {
        "Cu": float(alloy.get("Cu", 0)) * suppress_cu,
        "Sn": float(alloy.get("Sn", 0)) * enrich_sn,
        "Pb": float(alloy.get("Pb", 0)) * (1.0 + .25 * metal_loss),
        "As": float(alloy.get("As", 0)) * (1.0 + .12 * metal_loss),
        "Fe": float(alloy.get("Fe", 0)) + 2.5 * phases["soil_encrustation"],
        "Cl": 3.8 * (phases["nantokite"] + phases["atacamite_paratacamite"]),
    }
    st = sum(surface_metals.values()) or 1.0
    surface = {k: round(100 * v / st, 5) for k, v in surface_metals.items()}
    crack_fraction = float(np.clip(rng.beta(1.5, 8) * (1 + 2.5 * metal_loss + 1.3 * bronze_disease), 0, .82))
    surface_coverage = float(np.clip(1 - math.exp(-thickness / 190.0), .08, .999))
    integrity = float(np.clip(1 - .66 * metal_loss - .24 * crack_fraction, .02, .99))
    return {
        "mean_layer_thickness_um": round(thickness, 2),
        "metal_loss_fraction": round(metal_loss, 6),
        "pit_depth_um_p50": round(pit_p50, 2),
        "pit_depth_um_p95": round(pit_p95, 2),
        "bronze_disease_active_probability": round(bronze_disease, 6),
        "phase_fraction": phases,
        "surface_apparent_wt_pct": surface,
        "crack_fraction": round(crack_fraction, 6),
        "surface_coverage_fraction": round(surface_coverage, 6),
        "integrity_fraction": round(integrity, 6),
    }


def _discovery_context(world: Any, loss_node: str, deposition_mode: str, rng: np.random.Generator) -> Dict[str, Any]:
    node = world.nodes[loss_node]
    if deposition_mode == "river_wetland_deposit":
        methods = ["river engineering/dredging", "wetland excavation", "chance recovery"]
    elif deposition_mode == "grave_assemblage":
        methods = ["controlled excavation", "cemetery excavation", "rescue archaeology"]
    elif deposition_mode == "workshop_debris":
        methods = ["settlement excavation", "rescue archaeology", "industrial-area excavation"]
    else:
        methods = ["controlled excavation", "agricultural discovery", "rescue archaeology", "chance recovery"]
    year = int(np.clip(round(rng.normal(1975, 38)), 1850, 2025))
    jitter = .004 if node.kind not in {"river", "coast"} else .010
    lon = float(node.lon + rng.normal(0, jitter)); lat = float(node.lat + rng.normal(0, jitter * .75))
    return {
        "find_site_id": f"SITE-{_seed64(loss_node, deposition_mode, round(lon,4), round(lat,4)) % 100000:05d}",
        "site": _node_payload(world, loss_node, lon=lon, lat=lat),
        "discovery_year_ce": year,
        "recovery_method": str(rng.choice(methods)),
    }


def build_artifact_truth(
    world: Any,
    *,
    artifact_id: str,
    object_class: str,
    production_bc: int,
    source_mix: Mapping[str, float],
    recycle_count: int,
    repair_count: int,
    production_node: str,
    loss_node: str,
    deposition_mode: str,
    route_nodes: Sequence[str] | None = None,
    workshop_id: str | None = None,
    mass_kg: float | None = None,
    seed: int = 1,
) -> Dict[str, Any]:
    rng = stable_rng(seed, "artifact_truth", artifact_id)
    workshop = _workshop_by_id(world, workshop_id) or choose_actual_workshop(world, production_node, production_bc, rng)
    if mass_kg is None:
        mass_kg = float(rng.lognormal(math.log(base.OBJECT_CLASSES[object_class]["mean_kg"]), .34))
    source_mix = {str(k): float(v) for k, v in source_mix.items() if float(v) > 0}
    total = sum(source_mix.values()) or 1.0
    source_mix = {k: v / total for k, v in source_mix.items()}
    trace, isotopes = _weighted_source_truth(world, source_mix, recycle_count, rng)
    alloy = _bulk_alloy(object_class, production_bc, recycle_count, rng)
    dims = _dimensions(object_class, mass_kg, rng)
    manufacture = _guild_and_manufacture(world, workshop, object_class, recycle_count, repair_count, alloy, rng)
    if route_nodes:
        route = [str(n) for n in route_nodes if str(n) in world.nodes]
    else:
        route = shortest_physical_path(world, workshop.node_id, loss_node)
    if not route or route[0] != workshop.node_id:
        route = shortest_physical_path(world, workshop.node_id, loss_node)
    timeline = _usage_timeline(world, route, production_bc, object_class, repair_count, loss_node, rng)
    discovery = _discovery_context(world, loss_node, deposition_mode, rng)
    burial = _burial_environment(world, loss_node, deposition_mode, timeline["loss_bc"], discovery["discovery_year_ce"], rng)
    corrosion = _corrosion_state(alloy, burial, dims, rng)
    present_mass = float(mass_kg * (1.0 - corrosion["metal_loss_fraction"] * .55))
    return {
        "schema": ARTIFACT_TRUTH_VERSION,
        "artifact_id": artifact_id,
        "identity": {
            "object_class": object_class,
            "mass_kg_initial": round(float(mass_kg), 6),
            "mass_kg_present": round(present_mass, 6),
            "dimensions": dims,
            "prestige_index": round(float(base.OBJECT_CLASSES[object_class]["status"]), 5),
        },
        "material": {
            "source_mix": {k: round(v, 7) for k, v in source_mix.items()},
            "source_entropy": round(_entropy(source_mix), 6),
            "bulk_alloy_wt_pct": alloy,
            "trace_ppm": {k: round(float(v), 4) for k, v in trace.items()},
            "lead_isotopes": {k: round(float(v), 7) for k, v in isotopes.items()},
            "recycled_fraction_proxy": round(float(np.clip(.16 * recycle_count + .04 * len(source_mix), 0, .92)), 6),
        },
        "manufacture": manufacture,
        "timeline": timeline,
        "loss": {
            "date_bc": timeline["loss_bc"],
            "deposition_mode": deposition_mode,
            "site": _node_payload(world, loss_node),
        },
        "burial_environment": burial,
        "corrosion": corrosion,
        "find_context": discovery,
    }


def enrich_legacy_catalogue_row(world: Any, row: MutableMapping[str, Any], seed: int) -> MutableMapping[str, Any]:
    if "artifact_truth" in row:
        return row
    truth = row.get("truth", {})
    object_class = str(row.get("class", "fitting"))
    production_bc = int(row.get("date_center_bc", 1300))
    source_mix = truth.get("source_mix") or {}
    recycle_fraction = float(truth.get("recycle_fraction", 0.0))
    recycle_count = max(0, int(round(recycle_fraction / max(.08, 1.0 - recycle_fraction))))
    repair_count = int(truth.get("repair_count", 0))
    workshop_id = truth.get("workshop_id")
    workshop = _workshop_by_id(world, workshop_id)
    production_node = str(workshop.node_id if workshop is not None else truth.get("workshop_node") or truth.get("route", [next(iter(world.nodes))])[0])
    route = truth.get("route_nodes_truth") or truth.get("route") or []
    loss_node = None
    if route:
        # Prefer exact route node nearest the public findspot.
        fp = row.get("findspot", {})
        if "lon" in fp and "lat" in fp:
            loss_node = min(route, key=lambda n: base.haversine_km(float(fp["lon"]), float(fp["lat"]), world.nodes[n].lon, world.nodes[n].lat) if n in world.nodes else 1e9)
        else:
            loss_node = route[-1]
    if not loss_node or loss_node not in world.nodes:
        fp = row.get("findspot", {})
        loss_node = min(world.nodes, key=lambda n: base.haversine_km(float(fp.get("lon", 0)), float(fp.get("lat", 0)), world.nodes[n].lon, world.nodes[n].lat))
    dep_mode = str(row.get("deposition_mode_truth", "settlement_loss"))
    row["artifact_truth"] = build_artifact_truth(
        world, artifact_id=str(row.get("object_id", "unknown")), object_class=object_class,
        production_bc=production_bc, source_mix=source_mix, recycle_count=recycle_count,
        repair_count=repair_count, production_node=production_node, loss_node=str(loss_node),
        deposition_mode=dep_mode, route_nodes=route, workshop_id=workshop_id,
        mass_kg=float(row.get("mass_kg", base.OBJECT_CLASSES[object_class]["mean_kg"])), seed=seed,
    )
    return row


def enrich_round3_candidate(world: Any, row: MutableMapping[str, Any], seed: int) -> MutableMapping[str, Any]:
    if "artifact_truth" in row:
        return row
    prod = row["production_cell_truth"]; dep = row["deposition_truth"]; bio = row["biography_truth"]
    artifact_id = str(row.get("candidate_id", "candidate"))
    recycle_count = int(bio.get("recycle_count", 0)); repair_count = int(bio.get("repair_count", 0))
    workshop_id = bio.get("workshop_id") or bio.get("workshop_member_truth")
    route = shortest_physical_path(world, str(prod["origin_node"]), str(dep["node_id"]))
    row["artifact_truth"] = build_artifact_truth(
        world, artifact_id=artifact_id, object_class=str(prod["object_class"]),
        production_bc=int(prod["date_bc"]), source_mix=bio.get("source_mix") or {},
        recycle_count=recycle_count, repair_count=repair_count,
        production_node=str(prod["origin_node"]), loss_node=str(dep["node_id"]),
        deposition_mode=str(dep["mode"]), route_nodes=route, workshop_id=workshop_id,
        mass_kg=None, seed=seed,
    )
    return row
