#!/usr/bin/env python3
from __future__ import annotations

"""Build the Atolia v2 world directly into NetCDF4.

There is no giant JSON intermediate.  Benchmark mode exercises exactly the same
schema and event engine as full mode, but on a scaled subset of production cells.
Full mode deliberately refuses provisional geochemistry and hydrology unless the
caller explicitly overrides those scientific gates.
"""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Dict, Iterable, Mapping, Sequence

import numpy as np

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import archaeology_temporal_world as archaeology
import guild_model
import intensity_circulation as intensity
import provenance_field as base
import release_candidate_invariants as release_invariants
import v2_config as cfg
import v2_netcdf as nc
import v2_workshop_tools as workshop_tools


def _seed64(*parts: object) -> int:
    raw = "|".join(str(p) for p in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")


def _safe_entropy(mix: Mapping[str, float]) -> float:
    arr = np.asarray([max(0.0, float(v)) for v in mix.values()], dtype=float)
    arr = arr[arr > 0]
    if arr.size <= 1:
        return 0.0
    arr /= arr.sum()
    return float(-np.sum(arr * np.log(arr)) / math.log(arr.size))


def _norm_mix(mix: Mapping[str, float]) -> Dict[str, float]:
    out = {str(k): max(0.0, float(v)) for k, v in mix.items()}
    total = sum(out.values())
    if total <= 0:
        return {}
    return {k: v / total for k, v in out.items() if v > 0}


def _atesis_source_fraction(mix: Mapping[str, float]) -> float:
    norm = _norm_mix(mix)
    return float(sum(norm.get(s, 0.0) for s in cfg.ATESIS_SOURCE_IDS))


def _representative_object_mass() -> float:
    rows = [(float(v["weight"]), float(v["mean_kg"])) for v in base.OBJECT_CLASSES.values()]
    denom = sum(w for w, _ in rows)
    return sum(w * m for w, m in rows) / max(1e-12, denom)


def _cell_base_mass(cell: intensity.ProductionCell) -> float:
    return float(cell.production_intensity) * float(base.OBJECT_CLASSES[cell.object_class]["mean_kg"])


def _solve_atesis_tilt(base_weight: np.ndarray, a: np.ndarray, target_share: float) -> np.ndarray:
    if base_weight.size == 0:
        return base_weight
    target = float(np.clip(target_share, 0.0, 1.0))
    amin, amax = float(np.min(a)), float(np.max(a))
    if target <= amin + 1e-12 or target >= amax - 1e-12 or abs(amax - amin) < 1e-12:
        return base_weight.copy()
    lo, hi = -40.0, 40.0
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        z = np.clip(mid * a, -80.0, 80.0)
        w = base_weight * np.exp(z)
        share = float(np.sum(w * a) / max(1e-18, np.sum(w)))
        if share < target:
            lo = mid
        else:
            hi = mid
    z = np.clip(0.5 * (lo + hi) * a, -80.0, 80.0)
    return base_weight * np.exp(z)


def _tin_affinity(object_class: str) -> float:
    return {
        "sword": 1.30, "dagger": 1.20, "spearhead": 1.15, "axe": 1.05,
        "chisel": .95, "sickle": .92, "knife": .92, "vessel": 1.05,
        "ornament": .90, "figurine": .90, "fitting": .85, "ring": .72,
        "pin": .70, "bead": .55, "awl": .70, "ingot": .80, "scrap": .82,
    }.get(str(object_class), .85)


def _allocate_ledgers(all_cells: Sequence[intensity.ProductionCell], selected: Sequence[intensity.ProductionCell],
                      config: cfg.V2WorldConfig, mode: str) -> tuple[list[Dict[str, Any]], Dict[str, float]]:
    all_base = np.asarray([max(1e-18, _cell_base_mass(c)) for c in all_cells], dtype=float)
    sel_base = np.asarray([max(1e-18, _cell_base_mass(c)) for c in selected], dtype=float)
    scale = 1.0 if mode == "full" else float(np.sum(sel_base) / max(1e-18, np.sum(all_base)))
    target_cu = float(config.primary_cu_tonnes) * 1000.0 * scale
    target_sn = float(config.primary_sn_tonnes) * 1000.0 * scale
    target_atesis_share = float(config.atesis_primary_cu_tonnes / max(1e-12, config.primary_cu_tonnes))
    a = np.asarray([_atesis_source_fraction(c.source_mix) for c in selected], dtype=float)
    tilted = _solve_atesis_tilt(sel_base, a, target_atesis_share)
    cu = target_cu * tilted / max(1e-18, tilted.sum())
    realized_share = float(np.sum(cu * a) / max(1e-18, cu.sum()))

    sn_weight = np.asarray([cu_i * _tin_affinity(c.object_class) for cu_i, c in zip(cu, selected)], dtype=float)
    sn = target_sn * sn_weight / max(1e-18, sn_weight.sum())

    rep_mass = _representative_object_mass()
    objectization = config.objectization_fraction_prior(rep_mass)
    rows: list[Dict[str, Any]] = []
    for c, cu_kg, sn_kg, af in zip(selected, cu, sn, a):
        mean_mass = max(.005, float(base.OBJECT_CLASSES[c.object_class]["mean_kg"]))
        tracked_cu = float(cu_kg) * objectization
        # A Cu-equivalent lineage count intentionally remains separate from total
        # metal mass; Step-1 accounting calibrates the explicit object population.
        lineages = tracked_cu / mean_mass
        rows.append({
            "cell": c,
            "primary_cu_kg": float(cu_kg),
            "primary_sn_kg": float(sn_kg),
            "objectized_primary_cu_kg": tracked_cu,
            "objectized_primary_sn_kg": float(sn_kg) * objectization,
            "represented_initial_lineages": float(lineages),
            "atesis_source_fraction": float(af),
        })
    meta = {
        "benchmark_scale_fraction": scale,
        "scaled_primary_cu_target_kg": target_cu,
        "scaled_primary_sn_target_kg": target_sn,
        "realized_atesis_primary_cu_share": realized_share,
        "objectization_fraction": objectization,
        "representative_object_mass_kg": rep_mass,
    }
    return rows, meta


def _load_geochemistry(path: Path | None) -> Dict[str, Any]:
    if path is None:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("geochemistry file must contain an object")
    sources = payload.get("sources", payload)
    if not isinstance(sources, Mapping):
        raise ValueError("geochemistry sources must be a mapping")
    return {str(k): dict(v) for k, v in sources.items() if isinstance(v, Mapping)}


def _fallback_pb_ppm(source_id: str, seed: int) -> float:
    rng = np.random.default_rng(_seed64(seed, source_id, "pb-ppm-fallback"))
    return float(np.exp(rng.normal(math.log(550.0), 1.0)))


def _source_geochem(world: Any, source_id: str, external: Mapping[str, Any], seed: int) -> Dict[str, Any]:
    src = world.sources[source_id]
    supplied = dict(external.get(source_id, {}))
    pb_iso = dict(supplied.get("pb_isotopes", {}))
    if not pb_iso:
        pb_iso = {
            "Pb206_204": float(src.isotope_mean.get("Pb206_204", 18.2)),
            "Pb207_204": float(src.isotope_mean.get("Pb207_204", 15.6)),
            "Pb208_204": float(src.isotope_mean.get("Pb208_204", 38.2)),
        }
    return {
        "pb_ppm": float(supplied.get("pb_ppm", _fallback_pb_ppm(source_id, seed))),
        "pb_isotopes": pb_iso,
        "element_ppm": {str(k): float(v) for k, v in dict(supplied.get("element_ppm", {})).items()},
    }


def _pb_inventory(pb_mass_kg: float, ratios: Mapping[str, float]) -> Dict[str, float]:
    r206 = max(0.0, float(ratios.get("Pb206_204", 18.2)))
    r207 = max(0.0, float(ratios.get("Pb207_204", 15.6)))
    r208 = max(0.0, float(ratios.get("Pb208_204", 38.2)))
    raw = np.asarray([1.0, r206, r207, r208], dtype=float)
    raw /= max(1e-18, raw.sum())
    return {name: float(pb_mass_kg * frac) for name, frac in zip(cfg.PB_ISOTOPES, raw)}


def _initial_chemistry(world: Any, row: Mapping[str, Any], geochem: Mapping[str, Any], seed: int) -> tuple[Dict[str, float], Dict[str, float]]:
    mix = _norm_mix(row["cell"].source_mix)
    cu = float(row["objectized_primary_cu_kg"])
    sn = float(row["objectized_primary_sn_kg"])
    elements = {name: 0.0 for name in cfg.ELEMENTS}
    elements["Cu"] = cu
    elements["Sn"] = sn
    pb_inventory = {name: 0.0 for name in cfg.PB_ISOTOPES}
    for sid, fraction in mix.items():
        if sid not in world.sources:
            continue
        g = _source_geochem(world, sid, geochem, seed)
        source_cu = cu * fraction
        pb_mass = source_cu * float(g["pb_ppm"]) * 1e-6
        elements["Pb"] += pb_mass
        inv = _pb_inventory(pb_mass, g["pb_isotopes"])
        for name in cfg.PB_ISOTOPES:
            pb_inventory[name] += inv[name]
        for element, ppm in g["element_ppm"].items():
            if element in elements and element not in {"Cu", "Sn", "Pb"}:
                elements[element] += source_cu * max(0.0, float(ppm)) * 1e-6
        trace = world.sources[sid].trace_mean
        if "Ag_ppm" in trace and "Ag" not in g["element_ppm"]:
            elements["Ag"] += source_cu * max(0.0, float(trace["Ag_ppm"])) * 1e-6
    return elements, pb_inventory


def _ore_distance(world: Any, cell: intensity.ProductionCell) -> float:
    mix = _norm_mix(cell.source_mix)
    if cell.origin not in world.nodes:
        return 0.0
    origin = world.nodes[cell.origin]
    total = 0.0
    for sid, fraction in mix.items():
        src = world.sources.get(sid)
        if src is not None:
            total += fraction * base.haversine_km(src.lon, src.lat, origin.lon, origin.lat)
    return float(total)


def _load_hydro(path: Path | None) -> list[Dict[str, Any]]:
    if path is None:
        return []
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = payload.get("features", payload) if isinstance(payload, Mapping) else payload
    if not isinstance(rows, list):
        raise ValueError("hydro evidence must be a list or {'features': [...]} object")
    return [dict(r) for r in rows if isinstance(r, Mapping)]


def _edge_km(world: Any, a: str, b: str) -> float:
    na, nb = world.nodes[a], world.nodes[b]
    return float(base.haversine_km(na.lon, na.lat, nb.lon, nb.lat))


def _water_kind(kind: str) -> bool:
    return str(kind) in {"river", "coast", "hub"}


def _provisional_hydro(world: Any, seed: int, multiplier: float) -> list[Dict[str, Any]]:
    rng = np.random.default_rng(_seed64(seed, "hydro-a1"))
    rows: list[Dict[str, Any]] = []
    existing: set[tuple[str, str]] = set()
    for edge in world.edges:
        key = tuple(sorted((str(edge.a), str(edge.b))))
        existing.add(key)
        mode = str(edge.mode)
        water = any(x in mode.lower() for x in ("river", "coast", "sea", "lagoon"))
        rows.append({"a": edge.a, "b": edge.b, "provenance": "observed_model_graph", "mechanism": mode,
                     "probability": 1.0, "realized": True, "navigability": .85 if water else .12,
                     "observed": True, "mode": mode, "atesis_crossing": _provisional_atesis_edge(edge.a, edge.b)})
    candidate_nodes = [n for n in world.nodes.values() if _water_kind(n.kind)]
    candidates: list[tuple[float, Dict[str, Any]]] = []
    for i, a in enumerate(candidate_nodes):
        for b in candidate_nodes[i + 1:]:
            key = tuple(sorted((a.id, b.id)))
            if key in existing:
                continue
            km = _edge_km(world, a.id, b.id)
            if km > 95.0:
                continue
            kind_bonus = .22 * float(a.kind == "river") + .22 * float(b.kind == "river") + .15 * float(a.kind == "hub" or b.kind == "hub")
            p = float(np.clip(.07 + .62 * math.exp(-km / 38.0) + kind_bonus, .03, .88))
            navigability = float(np.clip(.18 + .55 * p + rng.normal(0, .08), .05, .95))
            score = p * (.55 + .45 * navigability)
            candidates.append((score, {"a": a.id, "b": b.id, "provenance": "inferred", "mechanism": "minor_channel_or_wetland_connector",
                                       "probability": p, "realized": bool(rng.random() < p), "navigability": navigability,
                                       "observed": False, "mode": "river_inferred", "atesis_crossing": _provisional_atesis_edge(a.id, b.id)}))
    target_extra = max(0, int(round((max(1.0, multiplier) - 1.0) * len(existing))))
    candidates.sort(key=lambda x: x[0], reverse=True)
    rows.extend(row for _, row in candidates[:target_extra])
    return rows


def _provisional_atesis_edge(a: str, b: str) -> bool:
    aa = any(h in str(a).lower() for h in cfg.ATESIS_NODE_HINTS)
    bb = any(h in str(b).lower() for h in cfg.ATESIS_NODE_HINTS)
    return bool(aa != bb)


def _merge_hydro(world: Any, supplied: Sequence[Mapping[str, Any]], seed: int, multiplier: float) -> list[Dict[str, Any]]:
    if not supplied:
        return _provisional_hydro(world, seed, multiplier)
    rows = _provisional_hydro(world, seed, 1.0)
    known = {tuple(sorted((r["a"], r["b"]))) for r in rows}
    for raw in supplied:
        a, b = str(raw["a"]), str(raw["b"])
        if a not in world.nodes or b not in world.nodes:
            raise ValueError(f"hydro feature references unknown node: {a} - {b}")
        key = tuple(sorted((a, b)))
        if key in known:
            continue
        p = float(np.clip(raw.get("probability", raw.get("confidence", .5)), 0.0, 1.0))
        rows.append({"a": a, "b": b, "provenance": str(raw.get("provenance", "inferred")),
                     "mechanism": str(raw.get("mechanism", "palaeochannel_candidate")), "probability": p,
                     "realized": bool(raw.get("realized", p >= .5)), "navigability": float(np.clip(raw.get("navigability", .45), 0.0, 1.0)),
                     "observed": bool(raw.get("observed", False)), "mode": str(raw.get("mode", "river_inferred")),
                     "atesis_crossing": bool(raw.get("atesis_crossing", _provisional_atesis_edge(a, b)))})
        known.add(key)
    return rows


def _adjacency(world: Any, hydro: Sequence[Mapping[str, Any]]) -> Dict[str, list[Dict[str, Any]]]:
    out: Dict[str, list[Dict[str, Any]]] = {node: [] for node in world.nodes}
    for row in hydro:
        if not bool(row.get("realized", False)):
            continue
        a, b = str(row["a"]), str(row["b"])
        if a not in out or b not in out:
            continue
        mode = str(row.get("mode", row.get("mechanism", "land")))
        water = any(x in mode.lower() for x in ("river", "sea", "coast", "lagoon", "wetland"))
        info = {"km": _edge_km(world, a, b), "mode": mode, "water": water,
                "navigability": float(row.get("navigability", .2)), "atesis_crossing": bool(row.get("atesis_crossing", False))}
        out[a].append({"to": b, **info})
        out[b].append({"to": a, **info})
    return out


def _draw_carrier(object_class: str, rng: np.random.Generator) -> str:
    rows = cfg.CARRIER_BY_CLASS.get(object_class, (("household_local", .65), ("merchant_pack", .35)))
    names = [r[0] for r in rows]
    p = np.asarray([max(0.0, float(r[1])) for r in rows], dtype=float)
    p /= p.sum()
    return str(rng.choice(names, p=p))


def _draw_object_class(date_bc: int, rng: np.random.Generator) -> str:
    names, weights = [], []
    for name, spec in base.OBJECT_CLASSES.items():
        if int(spec["start"]) >= date_bc >= int(spec["end"]):
            names.append(name)
            weights.append(float(spec["weight"]))
    if not names:
        names = list(base.OBJECT_CLASSES)
        weights = [float(base.OBJECT_CLASSES[n]["weight"]) for n in names]
    p = np.asarray(weights, dtype=float); p /= p.sum()
    return str(rng.choice(names, p=p))


def _status(object_class: str) -> float:
    return float(base.OBJECT_CLASSES.get(object_class, {}).get("status", .4))


def _operation_for_class(object_class: str) -> str:
    if object_class in {"sword", "dagger", "spearhead", "axe", "knife", "sickle", "chisel"}:
        return "edge_treatment"
    if object_class == "vessel":
        return "sheetwork"
    if object_class in {"ring", "pin", "bead", "ornament"}:
        return "wirework" if object_class in {"ring", "pin"} else "finishing"
    if object_class == "figurine":
        return "lost_wax"
    if object_class in {"scrap", "ingot"}:
        return "batching"
    return "casting"


def _guild_entropy(affinities: Mapping[str, float]) -> float:
    return _safe_entropy({k: max(0.0, float(v)) for k, v in affinities.items()})


def _pick_workshop(node_id: str, date_bc: int, ecologies_by_node: Mapping[str, Sequence[Any]], rng: np.random.Generator) -> Any | None:
    rows = [e for e in ecologies_by_node.get(node_id, ()) if int(e.start_bc) >= date_bc >= int(e.end_bc)]
    if not rows:
        rows = list(ecologies_by_node.get(node_id, ()))
    if not rows:
        return None
    weight = np.asarray([max(.01, float(e.recent_volume) * (.35 + .65 * float(e.quality_memory))) for e in rows], dtype=float)
    weight /= weight.sum()
    return rows[int(rng.choice(len(rows), p=weight))]


def _workshop_process(ecology: Any | None, operation: str) -> tuple[float, float, float, float]:
    if ecology is None:
        return .28, 0.0, 0.0, 0.0
    quality = workshop_tools.operation_capability(ecology, operation, operator_skill=.35 + .62 * ecology.quality_memory,
                                                  material_fit=.78, support_fit=.82, thermal_fit=.80, measurement_fit=.76)
    depths = [float(t.lineage_depth) for t in ecology.tools]
    return float(np.clip(quality, 0.0, 1.5)), _guild_entropy(ecology.guild_affinities), float(np.mean(depths)) if depths else 0.0, float(max(depths)) if depths else 0.0


def _home_distance(world: Any, node_id: str, home: str) -> float:
    if node_id not in world.nodes or home not in world.nodes:
        return 0.0
    a, b = world.nodes[node_id], world.nodes[home]
    return float(base.haversine_km(a.lon, a.lat, b.lon, b.lat))


def _choose_edge(world: Any, adjacency: Mapping[str, Sequence[Mapping[str, Any]]], node: str, home: str,
                 carrier: str, water_probability: float, rng: np.random.Generator) -> Mapping[str, Any] | None:
    edges = list(adjacency.get(node, ()))
    if not edges:
        return None
    water = [e for e in edges if bool(e["water"])]
    use_water = bool(water and rng.random() < water_probability)
    candidates = water if use_water else edges
    scores = []
    for e in candidates:
        nxt = str(e["to"])
        score = 1.0 / max(1.0, float(e["km"]))
        if bool(e["water"]):
            score *= .35 + 1.65 * float(e.get("navigability", .3))
        if carrier in {"household_local", "farmer_craft_local"}:
            score *= math.exp(-max(0.0, _home_distance(world, nxt, home) - _home_distance(world, node, home)) / 28.0)
        elif carrier in {"warrior_frontier", "mounted_retinue"}:
            kind = str(world.nodes[nxt].kind)
            score *= 1.6 if kind in {"pass", "river", "hub", "coast"} else 1.0
        elif carrier in {"broker_scrap_stock", "merchant_pack", "river_boat_cargo", "coastal_boat_cargo", "open_sea_cargo"}:
            kind = str(world.nodes[nxt].kind)
            score *= 1.8 if kind in {"hub", "coast", "river"} else .8
        scores.append(max(1e-12, score))
    p = np.asarray(scores, dtype=float); p /= p.sum()
    return candidates[int(rng.choice(len(candidates), p=p))]


def _terminal_kind(carrier: str, water: bool, conflict: float, status: float, rng: np.random.Generator) -> str:
    names = ["loss", "retire", "grave", "ritual", "hoard_failed_retrieval", "boat_wreck", "combat_loss", "workshop_debris", "catastrophic_abandonment"]
    w = np.asarray([.25, .23, .09, .06, .10, .02, .03, .10, .12], dtype=float)
    if water:
        w[names.index("boat_wreck")] += .16
        w[names.index("loss")] += .08
    if conflict > .35:
        w[names.index("combat_loss")] += .18 * conflict
        w[names.index("hoard_failed_retrieval")] += .14 * conflict
        w[names.index("catastrophic_abandonment")] += .12 * conflict
    if status > .7:
        w[names.index("grave")] += .08
        w[names.index("ritual")] += .07
        w[names.index("hoard_failed_retrieval")] += .06
    if carrier in {"workshop_stock", "broker_scrap_stock"}:
        w[names.index("workshop_debris")] += .20
    w = np.clip(w, 1e-6, None); w /= w.sum()
    return str(rng.choice(names, p=w))


def _aggregation_id(node_id: str, date_bc: int, terminal: str) -> int:
    if terminal not in {"grave", "ritual", "hoard_failed_retrieval", "boat_wreck", "catastrophic_abandonment"}:
        return -1
    bucket = int(round(date_bc / 25.0) * 25)
    return int(_seed64("agg", node_id, bucket, terminal) & ((1 << 63) - 1))


def _source_external_fraction(cell: intensity.ProductionCell) -> float:
    external_tokens = ("cyprus", "levant", "egypt", "aegean", "hatti", "anatol", "britain", "severn", "western_med")
    text = f"{cell.bundle_family} {cell.bundle_id}".lower()
    return .12 if any(token in text for token in external_tokens) else (.04 if "prestige" in text or "tail" in text else 0.0)


def _simulate_particle(*, writer: nc.DirectV2Writer, world: Any, cell_id: int, ledger: Mapping[str, Any],
                       particle_index: int, particle_count: int, adjacency: Mapping[str, Sequence[Mapping[str, Any]]],
                       ecologies_by_node: Mapping[str, Sequence[Any]], config: cfg.V2WorldConfig,
                       geochem: Mapping[str, Any], world_seed: int) -> Dict[str, Any]:
    cell: intensity.ProductionCell = ledger["cell"]
    rng = np.random.default_rng(_seed64(world_seed, cell.bundle_id, cell.object_class, cell.date_bc, particle_index, "v2-particle"))
    fraction = 1.0 / max(1, particle_count)
    elements, pb = _initial_chemistry(world, ledger, geochem, world_seed)
    elements = {k: v * fraction for k, v in elements.items()}
    pb = {k: v * fraction for k, v in pb.items()}
    lineages = float(ledger["represented_initial_lineages"]) * fraction
    episodes = lineages
    eligible_atesis_episodes = 0.0
    metal_ever_crossed = False
    current_episode_counted = False
    object_class = str(cell.object_class)
    carrier = _draw_carrier(object_class, rng)
    node = str(cell.origin)
    home = node
    date_bc = int(cell.date_bc)
    remelts = repairs = workshop_transitions = broker_cycles = water_count = ownership = 0.0
    cumulative_distance = current_distance = 0.0
    ore_distance = _ore_distance(world, cell)
    source_entropy = _safe_entropy(_norm_mix(cell.source_mix))
    technical_memory = 1.0
    network = .05 + .18 * _status(object_class)
    metal_age = current_age = 0.0
    external_fraction = _source_external_fraction(cell)
    atesis_crossings = 0.0

    ecology = _pick_workshop(node, date_bc, ecologies_by_node, rng)
    manufacture_quality, guild_entropy, tool_depth_mean, tool_depth_max = _workshop_process(ecology, _operation_for_class(object_class))
    if ecology is not None:
        writer.append_event(f"manufacture@{ecology.workshop_id}", cell_id=cell_id, node_id=node, date_bc=date_bc,
                            represented_weight=lineages, value=manufacture_quality)

    last_water = False
    terminal = "retire"
    max_events = int(config.max_life_events)
    for event_index in range(max_events):
        if date_bc <= config.world_end_bc:
            terminal = "retire"
            break
        # One event represents an interval containing zero or more active daily shifts;
        # it is not a daily simulation.
        dt = float(np.clip(rng.gamma(1.8, 1.25), .08, 8.0))
        metal_age += dt
        current_age += dt
        date_bc = max(config.world_end_bc, int(round(cell.date_bc - metal_age)))

        status = _status(object_class)
        conflict = float(np.clip(.04 + .20 * float(carrier in {"warrior_frontier", "mounted_retinue"}) +
                                 .12 * math.sin((_seed64(node) % 1000) * .01 + date_bc * .033) ** 2, 0.0, .65))
        bulk = min(1.0, float(base.OBJECT_CLASSES[object_class]["mean_kg"]) / 4.8)
        local_water = any(bool(e["water"]) for e in adjacency.get(node, ()))
        p_water = 1.0 / (1.0 + math.exp(-(-3.0 + 1.15 * float(local_water) + 1.55 * network +
                                             .30 * math.log1p(cumulative_distance / 80.0) + .75 * status +
                                             1.15 * float(carrier in {"merchant_pack", "broker_scrap_stock", "river_boat_cargo", "coastal_boat_cargo", "open_sea_cargo"}) +
                                             .65 * conflict - .70 * bulk)))
        activity = {
            "household_local": .34, "farmer_craft_local": .42, "warrior_frontier": .72, "mounted_retinue": .80,
            "mobile_pastoral": .65, "merchant_pack": .68, "river_boat_cargo": .72, "coastal_boat_cargo": .72,
            "open_sea_cargo": .58, "court_gift_prestige": .34, "marriage_inheritance_personal": .30,
            "repairer_mobile": .62, "workshop_stock": .16, "broker_scrap_stock": .46,
        }.get(carrier, .4)
        last_water = False
        if rng.random() < activity:
            edge = _choose_edge(world, adjacency, node, home, carrier, p_water, rng)
            if edge is not None:
                node = str(edge["to"])
                km = float(edge["km"])
                cumulative_distance += km
                current_distance += km
                last_water = bool(edge["water"])
                if last_water:
                    water_count += 1.0
                    network = min(1.0, network + .08 + .05 * float(edge.get("navigability", .3)))
                else:
                    network = min(1.0, network + .015)
                if bool(edge.get("atesis_crossing", False)):
                    atesis_crossings += 1.0
                    if not metal_ever_crossed:
                        metal_ever_crossed = True
                        eligible_atesis_episodes = episodes
                        current_episode_counted = True
                    elif not current_episode_counted:
                        eligible_atesis_episodes += lineages
                        current_episode_counted = True

        p_owner = .025 + .035 * status + .045 * conflict + .035 * float(carrier in {"merchant_pack", "court_gift_prestige"})
        if rng.random() < p_owner:
            ownership += 1.0
            network = min(1.0, network + .06)
            if rng.random() < .28:
                home = node
            carrier = _draw_carrier(object_class, rng)

        # Rare external-network contact enriches network history, not metal mass.
        if rng.random() < (.002 + .006 * status + .008 * float(carrier in {"merchant_pack", "coastal_boat_cargo", "open_sea_cargo", "court_gift_prestige"})):
            external_fraction = min(1.0, external_fraction + float(rng.uniform(.02, .12)))
            network = min(1.0, network + .10)
            writer.append_event("external_exchange_contact", cell_id=cell_id, node_id=node, date_bc=date_bc,
                                represented_weight=lineages, value=external_fraction)

        p_repair = .018 + .040 * float(object_class in {"sword", "dagger", "axe", "vessel", "sickle", "knife"}) + .020 * (1.0 - min(1.0, manufacture_quality))
        if rng.random() < p_repair:
            repairs += 1.0
            rep_ecology = _pick_workshop(node, date_bc, ecologies_by_node, rng)
            repair_q, ge, dm, dx = _workshop_process(rep_ecology, "repair")
            technical_memory *= float(np.clip(.94 + .04 * repair_q, .82, .995))
            manufacture_quality = .78 * manufacture_quality + .22 * repair_q
            guild_entropy = max(guild_entropy, ge)
            tool_depth_mean = .8 * tool_depth_mean + .2 * dm
            tool_depth_max = max(tool_depth_max, dx)
            if rep_ecology is not None:
                writer.append_event(f"repair@{rep_ecology.workshop_id}", cell_id=cell_id, node_id=node, date_bc=date_bc,
                                    represented_weight=lineages, value=repair_q)

        shock = .002 + .010 * last_water + .012 * conflict + .003 * status + .004 * float(node != home)
        if rng.random() < shock:
            terminal = _terminal_kind(carrier, last_water, conflict, status, rng)
            break

        mean_life = {"sword":18,"dagger":14,"spearhead":12,"axe":13,"sickle":9,"chisel":12,"awl":10,"knife":8,
                     "ring":22,"pin":16,"bead":25,"ornament":24,"vessel":19,"figurine":35,"fitting":10,"ingot":4,"scrap":2}.get(object_class,12)
        p_end = .025 + .15 / (1.0 + math.exp(-(current_age - mean_life) / max(2.0, mean_life * .22)))
        if rng.random() < p_end:
            recovery = config.pristine_recovery_probability if remelts < .5 else config.recycled_recovery_probability
            recovery *= .75 + .22 * min(1.0, network) + .08 * float(carrier in {"broker_scrap_stock", "workshop_stock"})
            recovery = float(np.clip(recovery, .02, .97))
            if rng.random() >= recovery:
                terminal = _terminal_kind(carrier, last_water, conflict, status, rng)
                break

            # Remelt ends one object episode. Element/isotope inventories are
            # conserved in a1/a2 until calibrated process-transfer priors replace
            # placeholder loss coefficients; technical/morphological memory is not.
            remelts += 1.0
            broker_cycles += float(rng.random() < (.45 + .35 * network))
            workshop_transitions += 1.0
            technical_memory *= float(rng.uniform(.06, .22))
            current_distance = 0.0
            current_age = 0.0
            source_entropy = min(1.0, source_entropy + float(rng.uniform(.01, .055)))
            network = min(1.0, network + .07)
            episodes += lineages
            current_episode_counted = False
            if metal_ever_crossed:
                eligible_atesis_episodes += lineages
                current_episode_counted = True
            object_class = _draw_object_class(date_bc, rng)
            carrier = _draw_carrier(object_class, rng)
            ecology = _pick_workshop(node, date_bc, ecologies_by_node, rng)
            manufacture_quality, ge, dm, dx = _workshop_process(ecology, _operation_for_class(object_class))
            guild_entropy = max(guild_entropy, ge)
            tool_depth_mean = .65 * tool_depth_mean + .35 * dm
            tool_depth_max = max(tool_depth_max, dx)
            if ecology is not None:
                writer.append_event(f"remelt_manufacture@{ecology.workshop_id}", cell_id=cell_id, node_id=node, date_bc=date_bc,
                                    represented_weight=lineages, value=manufacture_quality)
    else:
        terminal = "retire"

    if metal_ever_crossed and not current_episode_counted:
        eligible_atesis_episodes += lineages
        current_episode_counted = True

    moments = {
        "ore_distance_km": ore_distance,
        "cumulative_metal_distance_km": cumulative_distance,
        "current_object_distance_km": current_distance,
        "remelt_count": remelts,
        "repair_count": repairs,
        "workshop_transition_count": workshop_transitions,
        "broker_cycle_count": broker_cycles,
        "source_entropy": source_entropy,
        "technical_memory_fraction": float(np.clip(technical_memory, 0.0, 1.0)),
        "network_embedding": network,
        "water_mode_count": water_count,
        "ownership_transfer_count": ownership,
        "metal_lineage_age_years": metal_age,
        "current_object_age_years": current_age,
        "external_exchange_fraction": external_fraction,
        "atesis_crossing_count": atesis_crossings,
        "manufacture_quality": manufacture_quality,
        "guild_exposure_entropy": guild_entropy,
        "workshop_tool_depth_mean": tool_depth_mean,
        "workshop_tool_depth_max": tool_depth_max,
    }
    aggregation = _aggregation_id(node, date_bc, terminal)
    writer.append_state(cell_id=cell_id, node_id=node, object_class=object_class, carrier=carrier,
                        terminal_kind=terminal, date_bc=date_bc, represented_weight=lineages,
                        metal_mass_kg=sum(elements.values()), represented_lineages=lineages,
                        represented_object_episodes=episodes, moments=moments,
                        element_mass_kg=elements, pb_isotope_inventory=pb, aggregation_id=aggregation)
    return {
        "terminal": terminal,
        "elements": elements,
        "pb": pb,
        "episodes": episodes,
        "atesis_eligible_episodes": eligible_atesis_episodes,
        "metal_mass_kg": sum(elements.values()),
        "max_metal_distance_km": cumulative_distance,
        "max_object_distance_km": current_distance,
        "remelts": remelts,
        "repairs": repairs,
        "water_modes": water_count,
    }


def build(args: argparse.Namespace) -> Dict[str, Any]:
    config = cfg.DEFAULT_CONFIG
    release_version = release_invariants.install()
    hypothesis = json.loads(args.hypothesis.read_text(encoding="utf-8"))
    world = archaeology.TemporalFieldArchaeologicalWorld(hypothesis, seed=args.world_seed)
    print(f"building v2 structural world seed={args.world_seed} workshops={args.workshops}", file=sys.stderr, flush=True)
    world.build(workshop_count=args.workshops)
    mass_error_kg = release_invariants.production_mass_error(world)

    all_cells = intensity.production_cells(world)
    selected = all_cells if args.mode == "full" else all_cells[:max(1, int(args.cell_limit))]
    ledgers, allocation_meta = _allocate_ledgers(all_cells, selected, config, args.mode)

    geochem = _load_geochemistry(args.geochemistry)
    used_sources = {str(s) for c in selected for s in c.source_mix}
    missing_sources = sorted(s for s in used_sources if s not in geochem)
    if args.mode == "full" and missing_sources and not args.allow_legacy_geochemistry:
        raise RuntimeError(
            "full v2 build refuses legacy mean/fallback geochemistry; provide --geochemistry covering "
            f"all used sources (missing {len(missing_sources)}: {missing_sources[:8]}) or explicitly use --allow-legacy-geochemistry"
        )

    supplied_hydro = _load_hydro(args.hydro_evidence)
    if args.mode == "full" and not supplied_hydro and not args.allow_provisional_hydro:
        raise RuntimeError(
            "full v2 build refuses the provisional graph-derived hydro ensemble; provide --hydro-evidence "
            "or explicitly use --allow-provisional-hydro"
        )
    hydro = _merge_hydro(world, supplied_hydro, args.world_seed, config.hydro_candidate_density_multiplier)
    adjacency = _adjacency(world, hydro)

    ecologies = workshop_tools.seed_all_workshop_ecologies(world, args.world_seed)
    ecologies_by_node: Dict[str, list[Any]] = defaultdict(list)
    for ecology in ecologies:
        ecologies_by_node[ecology.node_id].append(ecology)

    model_metadata = {
        "mode": args.mode,
        "release_invariants": release_version,
        "structural_production_mass_error_kg": mass_error_kg,
        "configuration": config.as_dict(),
        "allocation": allocation_meta,
        "geochemistry_mode": "external" if geochem else "legacy_means_plus_deterministic_pb_concentration_fallback",
        "hydrology_mode": "supplied_evidence_plus_structural_edges" if supplied_hydro else "provisional_graph_ensemble",
        "process_element_transfer": "inventory-conserving-a2; no invented remelt fractionation coefficients",
        "benchmark_is_scaled_micro_world": bool(args.mode == "benchmark"),
    }
    writer = nc.DirectV2Writer(args.master, world_seed=args.world_seed, model_metadata=model_metadata,
                               chunk_rows=args.chunk_rows, compression_level=args.compression)
    writer.append_workshops(ecologies)
    writer.append_hydro(hydro)

    initial_elements = Counter()
    terminal_elements = Counter()
    terminal_kinds = Counter()
    total_initial_lineages = 0.0
    total_terminal_episodes = 0.0
    atesis_eligible_episodes = 0.0
    max_metal_distance = 0.0
    max_object_distance = 0.0
    particles = int(args.particles_per_cell)
    try:
        for i, ledger in enumerate(ledgers):
            cell = ledger["cell"]
            cell_payload = {
                "bundle_id": cell.bundle_id, "bundle_family": cell.bundle_family, "date_bc": cell.date_bc,
                "origin": cell.origin, "destination": cell.destination, "object_class": cell.object_class,
                "primary_cu_kg": ledger["primary_cu_kg"], "objectized_primary_cu_kg": ledger["objectized_primary_cu_kg"],
                "represented_initial_lineages": ledger["represented_initial_lineages"],
                "atesis_source_fraction": ledger["atesis_source_fraction"], "source_mix": _norm_mix(cell.source_mix),
            }
            cid = writer.append_cell(cell_payload)
            init_el, _ = _initial_chemistry(world, ledger, geochem, args.world_seed)
            for name, value in init_el.items():
                initial_elements[name] += float(value)
            total_initial_lineages += float(ledger["represented_initial_lineages"])
            for particle_index in range(particles):
                result = _simulate_particle(writer=writer, world=world, cell_id=cid, ledger=ledger,
                                            particle_index=particle_index, particle_count=particles,
                                            adjacency=adjacency, ecologies_by_node=ecologies_by_node,
                                            config=config, geochem=geochem, world_seed=args.world_seed)
                terminal_kinds[result["terminal"]] += float(ledger["represented_initial_lineages"]) / particles
                for name, value in result["elements"].items():
                    terminal_elements[name] += float(value)
                total_terminal_episodes += float(result["episodes"])
                atesis_eligible_episodes += float(result["atesis_eligible_episodes"])
                max_metal_distance = max(max_metal_distance, float(result["max_metal_distance_km"]))
                max_object_distance = max(max_object_distance, float(result["max_object_distance_km"]))
            writer.finish_current_cell()
            if (i + 1) % max(1, int(args.progress_every)) == 0 or i + 1 == len(ledgers):
                print(f"v2 cells {i+1}/{len(ledgers)} states={writer.state_count} profiles={writer.profile_count}", file=sys.stderr, flush=True)

        closure = {name: float(initial_elements[name] - terminal_elements[name]) for name in cfg.ELEMENTS}
        target = float(config.target_atesis_crossing_object_episodes) * (1.0 if args.mode == "full" else allocation_meta["benchmark_scale_fraction"])
        recommended_scale = target / max(1e-18, atesis_eligible_episodes)
        accounting = {
            "mode": args.mode,
            "scaled_world_fraction": allocation_meta["benchmark_scale_fraction"],
            "full_primary_cu_target_kg": config.primary_cu_tonnes * 1000.0,
            "full_atesis_primary_cu_target_kg": config.atesis_primary_cu_tonnes * 1000.0,
            "full_primary_sn_target_kg": config.primary_sn_tonnes * 1000.0,
            "scaled_primary_cu_target_kg": allocation_meta["scaled_primary_cu_target_kg"],
            "scaled_primary_sn_target_kg": allocation_meta["scaled_primary_sn_target_kg"],
            "realized_atesis_primary_cu_share": allocation_meta["realized_atesis_primary_cu_share"],
            "explicit_objectization_fraction": allocation_meta["objectization_fraction"],
            "background_primary_cu_kg": allocation_meta["scaled_primary_cu_target_kg"] * (1.0 - allocation_meta["objectization_fraction"]),
            "represented_initial_lineages": total_initial_lineages,
            "represented_terminal_object_episodes": total_terminal_episodes,
            "atesis_eligible_object_episodes": atesis_eligible_episodes,
            "scaled_atesis_episode_target": target,
            "recommended_objectization_scale_for_freeze": recommended_scale,
            "initial_explicit_element_mass_kg": dict(initial_elements),
            "terminal_explicit_element_mass_kg": dict(terminal_elements),
            "element_closure_error_kg": closure,
            "terminal_weight_by_kind": dict(terminal_kinds),
            "max_cumulative_metal_distance_km": max_metal_distance,
            "max_current_object_distance_km": max_object_distance,
            "hydro_rows": len(hydro),
            "hydro_realized_rows": sum(bool(r.get("realized")) for r in hydro),
            "hydro_inferred_rows": sum(not bool(r.get("observed")) for r in hydro),
            "geochemistry_missing_sources": missing_sources,
            "poari_contract": "POARI routes archaeological inquiry, not artefact selection.",
        }
        writer.finish(accounting)
    finally:
        writer.close()

    runtime_report = None
    if not args.no_runtime:
        runtime_report = nc.build_runtime(args.master, args.runtime, compression_level=args.compression)
    report = {
        "schema": cfg.V2_MASTER_SCHEMA,
        "model_version": cfg.V2_MODEL_VERSION,
        "master": str(args.master),
        "runtime": None if args.no_runtime else str(args.runtime),
        "mode": args.mode,
        "production_cells": len(ledgers),
        "particles_per_cell": particles,
        "workshops": len(ecologies),
        "tools": sum(len(e.tools) for e in ecologies),
        "hydro_rows": len(hydro),
        "allocation": allocation_meta,
        "runtime_report": runtime_report,
    }
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the Atolia metal-lineage v2 world directly into NetCDF4")
    ap.add_argument("--hypothesis", type=Path, default=Path("hypotheses/atolia_atesis_1800_1000_v0.json"))
    ap.add_argument("--world-seed", type=int, default=1300)
    ap.add_argument("--workshops", type=int, default=3200)
    ap.add_argument("--mode", choices=("benchmark", "full"), default="benchmark")
    ap.add_argument("--cell-limit", type=int, default=cfg.DEFAULT_CONFIG.benchmark_cell_limit)
    ap.add_argument("--particles-per-cell", type=int, default=0, help="0 = use mode default")
    ap.add_argument("--geochemistry", type=Path, default=None, help="JSON source covariance/geochemistry product")
    ap.add_argument("--hydro-evidence", type=Path, default=None, help="JSON/converted GIS palaeohydrology feature product")
    ap.add_argument("--allow-legacy-geochemistry", action="store_true")
    ap.add_argument("--allow-provisional-hydro", action="store_true")
    ap.add_argument("--master", type=Path, default=Path("cache/atolia_master_v2.nc"))
    ap.add_argument("--runtime", type=Path, default=Path("cache/atolia_runtime_v2.nc"))
    ap.add_argument("--no-runtime", action="store_true")
    ap.add_argument("--chunk-rows", type=int, default=cfg.DEFAULT_CONFIG.netcdf_chunk_rows)
    ap.add_argument("--compression", type=int, default=cfg.DEFAULT_CONFIG.compression_level)
    ap.add_argument("--progress-every", type=int, default=25)
    args = ap.parse_args()
    if args.particles_per_cell <= 0:
        args.particles_per_cell = cfg.DEFAULT_CONFIG.full_particles_per_cell if args.mode == "full" else cfg.DEFAULT_CONFIG.benchmark_particles_per_cell
    if args.mode == "full":
        args.cell_limit = 0
    report = build(args)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
