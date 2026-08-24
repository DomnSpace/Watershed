from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Mapping, Sequence, Tuple

import numpy as np

import artifact_physical_truth as physical_truth
import guild_model
import intensity_circulation as intensity
import provenance_field_mediterranean as med


MATERIALIZER_VERSION = "rare-event-materializer-v2-physical-truth"

# Approximate probability that a *loss* reaches the finite computational candidate
# pool. Round 4 subsequently applies explicit survival/discovery/record probabilities.
DEPOSITION_SURVIVAL_PRIOR = {
    "wetland": .090, "river": .070, "hoard": .055, "wreck": .085,
    "funerary": .040, "settlement": .020, "workshop": .015,
    "fortification": .018, "field_loss": .012, "ritual": .048, "unknown": .018,
    "founder_scrap_hoard": .055, "finished_object_hoard": .060,
    "selective_ritual_deposit": .050, "personal_wealth_deposit": .042,
    "grave_assemblage": .045, "settlement_loss": .020,
    "river_wetland_deposit": .080, "workshop_debris": .015,
    "catastrophic_abandonment": .055,
}


def _seed64(*parts: Any) -> int:
    text = "|".join(str(x) for x in parts)
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")


def _normalized(m: Mapping[str, float]) -> Tuple[List[str], np.ndarray]:
    keys = list(m)
    arr = np.asarray([max(0.0, float(m[k])) for k in keys], dtype=float)
    if arr.sum() <= 0:
        arr[:] = 1.0
    arr /= arr.sum()
    return keys, arr


def materialization_probability(stratum: intensity.LossStratum) -> float:
    modes, probs = _normalized(stratum.deposition_mode_weights)
    retention = sum(float(p) * DEPOSITION_SURVIVAL_PRIOR.get(mode, .018) for mode, p in zip(modes, probs))
    exceptional = 1.0 + .18 * min(3.0, stratum.expected_field_crossings) + .12 * min(3.0, stratum.expected_physical_crossings)
    return float(np.clip(retention * exceptional, 1e-5, .35))


def expected_candidate_intensity(stratum: intensity.LossStratum) -> float:
    return float(stratum.loss_intensity * materialization_probability(stratum))


def allocate_candidate_budget(reports: Sequence[intensity.CellFlowReport], target_candidates: int = 100_000) -> List[Tuple[intensity.LossStratum, float, int]]:
    strata = [s for r in reports for s in r.loss_strata if s.loss_intensity > 0]
    if not strata:
        return []
    expected = np.asarray([expected_candidate_intensity(s) for s in strata], dtype=float)
    allocation_mass = np.sqrt(np.maximum(expected, 0.0))
    if allocation_mass.sum() <= 0:
        return []
    allocation_mass /= allocation_mass.sum()
    raw = allocation_mass * int(target_candidates)
    counts = np.floor(raw).astype(int)
    remainder = int(target_candidates) - int(counts.sum())
    if remainder > 0:
        counts[np.argsort(-(raw - counts))[:remainder]] += 1
    return [(s, float(e), int(n)) for s, e, n in zip(strata, expected, counts) if n > 0]


def _sample_source_mix(rng: np.random.Generator, base_mix: Mapping[str, float], recycle_count: int) -> Dict[str, float]:
    keys, probs = _normalized(base_mix)
    concentration = max(4.0, 24.0 / (1.0 + .45 * recycle_count))
    draw = rng.dirichlet(np.maximum(.05, probs * concentration))
    out = {k: float(v) for k, v in zip(keys, draw)}
    if recycle_count > 0:
        intrusion = float(np.clip(rng.beta(1.2, 8.0) * min(.35, .06 * recycle_count), 0, .30))
        if intrusion > 0:
            out = {k: v * (1.0 - intrusion) for k, v in out.items()}
            out["recycled_external_mix"] = intrusion
    total = sum(out.values()) or 1.0
    return {k: float(v / total) for k, v in out.items()}


def _sample_deposition(rng: np.random.Generator, weights: Mapping[str, float]) -> str:
    keys, probs = _normalized(weights)
    return str(rng.choice(keys, p=probs))


def _actual_workshop_summary(world: Any, artifact_truth: Mapping[str, Any]) -> Dict[str, Any]:
    m = artifact_truth["manufacture"]
    affinities = dict(m.get("guild_affinities", {}))
    primary = m.get("primary_guild_id")
    return {
        "workshop_id": m.get("workshop_id"),
        "workshop_node": m.get("workshop_node_id"),
        "lineage_id": m.get("lineage_id"),
        # Compatibility names now point to real model entities instead of hash placeholders.
        "guild_family_truth": primary,
        "workshop_member_truth": m.get("workshop_id"),
        "workshop_signature_strength_truth": float(affinities.get(primary, 0.0)) if primary else 0.0,
        "guild_affinity_vector": affinities,
        "manufacturing_operations": list(m.get("operations", ())),
    }


def materialize_biographies(
    world: Any,
    reports: Sequence[intensity.CellFlowReport],
    target_candidates: int = 100_000,
    seed: int = 1,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not getattr(world, "workshops", None) or not getattr(world, "sources", None):
        raise RuntimeError("Round-3 materialization requires a fully built world with real sources and workshops; call world.build(...).")
    allocations = allocate_candidate_budget(reports, target_candidates)
    rows: List[Dict[str, Any]] = []
    for s, expected, count in allocations:
        cell = s.production_cell
        row_weight = expected / max(1, count)
        for j in range(count):
            candidate_id = f"IC-{len(rows):07d}"
            rng = np.random.default_rng(_seed64(seed, cell.bundle_id, cell.object_class, cell.date_bc, s.node_id, s.step, j))
            recycle_count = max(0, int(rng.poisson(max(0.0, s.expected_recycle_count))))
            repair_count = max(0, int(rng.poisson(max(0.0, s.expected_repair_count + .18 * recycle_count))))
            source_mix = _sample_source_mix(rng, cell.source_mix, recycle_count)
            deposition = _sample_deposition(rng, s.deposition_mode_weights)
            node = world.nodes[s.node_id]
            row: Dict[str, Any] = {
                "candidate_id": candidate_id,
                "model_version": MATERIALIZER_VERSION,
                "importance_weight": float(row_weight),
                "production_cell_truth": {
                    "bundle_id": cell.bundle_id,
                    "bundle_family": cell.bundle_family,
                    "object_class": cell.object_class,
                    "date_bc": cell.date_bc,
                    "origin_node": cell.origin,
                    "origin_region": med.REGION_BY_NODE.get(cell.origin, "other"),
                    "destination_intent_node": cell.destination,
                },
                "deposition_truth": {
                    "node_id": s.node_id,
                    "region": med.REGION_BY_NODE.get(s.node_id, "other"),
                    "lon": float(node.lon), "lat": float(node.lat),
                    "mode": deposition, "loss_step": int(s.step),
                },
                "biography_truth": {
                    "route_distance_km_expected": float(s.route_distance_from_origin_km),
                    "field_crossings_expected": float(s.expected_field_crossings),
                    "physical_crossings_expected": float(s.expected_physical_crossings),
                    "recycle_count": recycle_count,
                    "repair_count": repair_count,
                    "source_mix": source_mix,
                    "source_entropy_expected": float(s.expected_source_entropy),
                    "transport_field_mix": dict(s.field_mix),
                },
                "archaeological_candidate_intensity": float(expected),
            }
            physical_truth.enrich_round3_candidate(world, row, seed)
            row["biography_truth"].update(_actual_workshop_summary(world, row["artifact_truth"]))
            rows.append(row)
    summary = {
        "model_version": MATERIALIZER_VERSION,
        "target_candidates": int(target_candidates),
        "materialized_candidates": len(rows),
        "represented_candidate_intensity": float(sum(float(r["importance_weight"]) for r in rows)),
        "loss_strata_used": len(allocations),
        "importance_sampling": "sqrt(expected_archaeological_candidate_intensity)",
        "workshop_source_independence": True,
        "actual_world_workshops_used": len({r["artifact_truth"]["manufacture"]["workshop_id"] for r in rows}),
        "physical_truth_schema": physical_truth.ARTIFACT_TRUTH_VERSION,
    }
    return rows, summary
