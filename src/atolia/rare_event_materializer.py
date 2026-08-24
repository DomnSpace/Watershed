from __future__ import annotations

import hashlib
import math
from dataclasses import asdict
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

import numpy as np

import provenance_field as base
import provenance_field_mediterranean as med
import intensity_circulation as intensity


MATERIALIZER_VERSION = "rare-event-materializer-v1"

# Approximate probability that a *loss* reaches a materializable archaeological
# candidate. Round 4 will split this into explicit survival/discovery/record hazards.
DEPOSITION_SURVIVAL_PRIOR = {
    "wetland": .090,
    "river": .070,
    "hoard": .055,
    "wreck": .085,
    "funerary": .040,
    "settlement": .020,
    "workshop": .015,
    "fortification": .018,
    "field_loss": .012,
    "ritual": .048,
    "unknown": .018,
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
    survival = sum(float(p) * DEPOSITION_SURVIVAL_PRIOR.get(mode, .018) for mode, p in zip(modes, probs))
    # Long-distance/cross-field losses receive only a modest candidate-retention boost.
    # This is computational importance sampling, not an archaeological truth claim.
    exceptional = 1.0 + .18 * min(3.0, stratum.expected_field_crossings) + .12 * min(3.0, stratum.expected_physical_crossings)
    return float(np.clip(survival * exceptional, 1e-5, .35))


def expected_candidate_intensity(stratum: intensity.LossStratum) -> float:
    return float(stratum.loss_intensity * materialization_probability(stratum))


def allocate_candidate_budget(
    reports: Sequence[intensity.CellFlowReport],
    target_candidates: int = 100_000,
) -> List[Tuple[intensity.LossStratum, float, int]]:
    """Allocate a finite individual-biography budget over loss strata.

    Returns (stratum, archaeological expected intensity, number_to_instantiate).
    Each instantiated biography receives an importance weight later, so allocating
    more rows to rare/interesting strata does not alter the hidden economy.
    """
    strata = [s for r in reports for s in r.loss_strata if s.loss_intensity > 0]
    if not strata:
        return []
    expected = np.asarray([expected_candidate_intensity(s) for s in strata], dtype=float)
    # sqrt allocation protects rare strata without allowing giant local strata to
    # consume the entire computational budget.
    allocation_mass = np.sqrt(np.maximum(expected, 0.0))
    if allocation_mass.sum() <= 0:
        return []
    allocation_mass /= allocation_mass.sum()
    raw = allocation_mass * int(target_candidates)
    counts = np.floor(raw).astype(int)
    remainder = int(target_candidates) - int(counts.sum())
    if remainder > 0:
        frac_order = np.argsort(-(raw - counts))[:remainder]
        counts[frac_order] += 1
    return [(s, float(e), int(n)) for s, e, n in zip(strata, expected, counts) if n > 0]


def _sample_source_mix(rng: np.random.Generator, base_mix: Mapping[str, float], recycle_count: int) -> Dict[str, float]:
    keys, probs = _normalized(base_mix)
    concentration = max(4.0, 24.0 / (1.0 + .45 * recycle_count))
    draw = rng.dirichlet(np.maximum(.05, probs * concentration))
    # Recycling can introduce a small generic mixed-source component without changing
    # workshop identity. This is latent provenance, not a player-facing label.
    out = {k: float(v) for k, v in zip(keys, draw)}
    if recycle_count > 0:
        intrusion = float(np.clip(rng.beta(1.2, 8.0) * min(.35, .06 * recycle_count), 0, .30))
        if intrusion > 0:
            out = {k: v * (1.0 - intrusion) for k, v in out.items()}
            out["recycled_external_mix"] = intrusion
    total = sum(out.values()) or 1.0
    return {k: float(v / total) for k, v in out.items()}


def _workshop_identity(world: Any, stratum: intensity.LossStratum, rng: np.random.Generator) -> Dict[str, Any]:
    """Workshop lineage is sampled independently from metal/source provenance."""
    cell = stratum.production_cell
    region = med.REGION_BY_NODE.get(cell.origin, "other")
    # Stable guild family from production context, plus stochastic workshop member.
    guild_seed = _seed64("guild", cell.bundle_family, region, cell.date_bc // 100)
    guild_family = f"g{guild_seed % 97:02d}"
    workshop_member = int(rng.integers(0, 9))
    strength = float(np.clip(rng.beta(2.0, 2.8) * (.75 + .25 * (cell.object_class in {"sword", "dagger", "vessel"})), .03, .98))
    return {
        "guild_family_truth": guild_family,
        "workshop_member_truth": f"{guild_family}-w{workshop_member:02d}",
        "workshop_signature_strength_truth": strength,
    }


def _sample_deposition(rng: np.random.Generator, weights: Mapping[str, float]) -> str:
    keys, probs = _normalized(weights)
    return str(rng.choice(keys, p=probs))


def materialize_biographies(
    world: Any,
    reports: Sequence[intensity.CellFlowReport],
    target_candidates: int = 100_000,
    seed: int = 1,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    allocations = allocate_candidate_budget(reports, target_candidates)
    rows: List[Dict[str, Any]] = []
    for stratum_index, (s, expected, count) in enumerate(allocations):
        cell = s.production_cell
        row_weight = expected / max(1, count)
        for j in range(count):
            rng = np.random.default_rng(_seed64(seed, cell.bundle_id, cell.object_class, cell.date_bc, s.node_id, s.step, j))
            recycle_count = max(0, int(rng.poisson(max(0.0, s.expected_recycle_count))))
            repair_count = max(0, int(rng.poisson(max(0.0, s.expected_repair_count + .18 * recycle_count))))
            source_mix = _sample_source_mix(rng, cell.source_mix, recycle_count)
            workshop = _workshop_identity(world, s, rng)
            deposition = _sample_deposition(rng, s.deposition_mode_weights)
            node = world.nodes[s.node_id]
            # Materialized biographies deliberately retain hidden truth separately from
            # future noisy observations. No POARI/career field is computed here.
            rows.append({
                "candidate_id": f"IC-{len(rows):07d}",
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
                    **workshop,
                },
                "archaeological_candidate_intensity": float(expected),
            })
    summary = {
        "model_version": MATERIALIZER_VERSION,
        "target_candidates": int(target_candidates),
        "materialized_candidates": len(rows),
        "represented_candidate_intensity": float(sum(float(r["importance_weight"]) for r in rows)),
        "loss_strata_used": len(allocations),
        "importance_sampling": "sqrt(expected_archaeological_candidate_intensity)",
        "workshop_source_independence": True,
    }
    return rows, summary
