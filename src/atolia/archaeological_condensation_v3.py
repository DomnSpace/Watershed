from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple

import numpy as np

import intensity_circulation as intensity
import provenance_field as base
import provenance_field_mediterranean as med
import rare_event_materializer as materializer


CONDENSATION_VERSION = "archaeological-condensation-v3"

# These are conditional observation factors applied AFTER a loss has happened.
# They are broad priors, not calibrated archaeological truth tables.
MODE_SURVIVAL = {
    "founder_scrap_hoard": .74,
    "finished_object_hoard": .80,
    "selective_ritual_deposit": .69,
    "personal_wealth_deposit": .63,
    "grave_assemblage": .66,
    "settlement_loss": .44,
    "river_wetland_deposit": .83,
    "workshop_debris": .38,
    "catastrophic_abandonment": .57,
    # Compatibility aliases used by older materializer/test data.
    "wetland": .83, "river": .78, "hoard": .76, "wreck": .84,
    "funerary": .66, "settlement": .44, "workshop": .38,
    "fortification": .50, "field_loss": .34, "ritual": .69, "unknown": .46,
}

MODE_DISCOVERY = {
    "founder_scrap_hoard": .030,
    "finished_object_hoard": .026,
    "selective_ritual_deposit": .013,
    "personal_wealth_deposit": .020,
    "grave_assemblage": .031,
    "settlement_loss": .024,
    "river_wetland_deposit": .008,
    "workshop_debris": .036,
    "catastrophic_abandonment": .033,
    "wetland": .008, "river": .010, "hoard": .028, "wreck": .006,
    "funerary": .031, "settlement": .024, "workshop": .036,
    "fortification": .026, "field_loss": .018, "ritual": .013, "unknown": .018,
}

MODE_RECORD = {
    "founder_scrap_hoard": .66,
    "finished_object_hoard": .72,
    "selective_ritual_deposit": .63,
    "personal_wealth_deposit": .62,
    "grave_assemblage": .76,
    "settlement_loss": .48,
    "river_wetland_deposit": .55,
    "workshop_debris": .40,
    "catastrophic_abandonment": .67,
    "wetland": .55, "river": .56, "hoard": .70, "wreck": .58,
    "funerary": .76, "settlement": .48, "workshop": .40,
    "fortification": .60, "field_loss": .35, "ritual": .63, "unknown": .44,
}

PRESTIGE_CLASSES = {"sword", "dagger", "ornament", "figurine", "vessel", "spearhead"}
LOCAL_BULK_CLASSES = {"awl", "sickle", "chisel", "fitting", "scrap", "axe", "ingot"}


def _sigmoid(x: float) -> float:
    x = float(np.clip(x, -24.0, 24.0))
    return 1.0 / (1.0 + math.exp(-x))


def _seed64(*parts: Any) -> int:
    text = "|".join(str(x) for x in parts)
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")


def survival_probability(row: Mapping[str, Any]) -> float:
    dep = row["deposition_truth"]
    bio = row["biography_truth"]
    prod = row["production_cell_truth"]
    mode = str(dep["mode"])
    obj = str(prod["object_class"])
    base_p = MODE_SURVIVAL.get(mode, .46)
    recycle = float(bio.get("recycle_count", 0.0))
    repairs = float(bio.get("repair_count", 0.0))
    # Repeated repair/recycling can fragment or alter objects; prestige objects often
    # remain more recognizable/materially robust than tiny utilitarian fragments.
    integrity = math.exp(-.045 * recycle - .025 * repairs)
    class_factor = 1.07 if obj in PRESTIGE_CLASSES else (.94 if obj in {"bead", "pin", "awl"} else 1.0)
    return float(np.clip(base_p * integrity * class_factor, .03, .97))


def discovery_probability(row: Mapping[str, Any]) -> float:
    dep = row["deposition_truth"]
    bio = row["biography_truth"]
    prod = row["production_cell_truth"]
    mode = str(dep["mode"])
    obj = str(prod["object_class"])
    distance = float(bio.get("route_distance_km_expected", 0.0))
    crossings = float(bio.get("physical_crossings_expected", 0.0))
    field_cross = float(bio.get("field_crossings_expected", 0.0))
    base_p = MODE_DISCOVERY.get(mode, .018)
    mass = float(base.OBJECT_CLASSES.get(obj, {"mean_kg": .2})["mean_kg"])
    visibility = .65 + .55 * min(1.0, math.log1p(7.0 * mass) / math.log(34.6))
    remoteness = math.exp(-.00011 * distance) * math.exp(-.018 * min(5.0, crossings + 2.0 * field_cross))
    return float(np.clip(base_p * visibility * remoteness, .0003, .08))


def record_probability(row: Mapping[str, Any]) -> float:
    dep = row["deposition_truth"]
    bio = row["biography_truth"]
    prod = row["production_cell_truth"]
    mode = str(dep["mode"])
    obj = str(prod["object_class"])
    base_p = MODE_RECORD.get(mode, .44)
    prestige = 1.10 if obj in PRESTIGE_CLASSES else 1.0
    workshop_fragment_penalty = .88 if mode in {"workshop_debris", "workshop"} else 1.0
    repair_bonus = 1.0 + .015 * min(4.0, float(bio.get("repair_count", 0.0)))
    return float(np.clip(base_p * prestige * workshop_fragment_penalty * repair_bonus, .08, .92))


def observation_probability(row: Mapping[str, Any]) -> Dict[str, float]:
    p_survive = survival_probability(row)
    p_discover = discovery_probability(row)
    p_record = record_probability(row)
    return {
        "p_survival": p_survive,
        "p_discovery": p_discover,
        "p_record": p_record,
        "p_observed_given_loss": float(p_survive * p_discover * p_record),
    }


def expected_archaeological_weight(row: Mapping[str, Any]) -> float:
    p = observation_probability(row)["p_observed_given_loss"]
    # Round-3 importance_weight reconstructs expected candidate intensity represented by this row.
    return float(row["importance_weight"]) * p


def assign_observation_truth(rows: Sequence[MutableMapping[str, Any]]) -> None:
    for row in rows:
        obs = observation_probability(row)
        row["observation_truth"] = {
            "model_version": CONDENSATION_VERSION,
            **{k: float(v) for k, v in obs.items()},
            "expected_archaeological_weight": expected_archaeological_weight(row),
        }


def weighted_poisson_catalogue(
    rows: Sequence[Mapping[str, Any]],
    target_catalogue: int = 30_000,
    seed: int = 1,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Condense weighted rare-event biographies to exactly ~30k rows.

    We sample indices with probability proportional to archaeological expectation,
    then attach Horvitz-like reconstruction weights. This gives rare strata finite
    resolution without changing their represented archaeological mass.
    """
    if not rows:
        return [], {"target_catalogue": int(target_catalogue), "catalogue_objects": 0}
    weights = np.asarray([expected_archaeological_weight(r) for r in rows], dtype=float)
    weights = np.maximum(weights, 0.0)
    total = float(weights.sum())
    if total <= 0:
        return [], {"target_catalogue": int(target_catalogue), "catalogue_objects": 0, "represented_archaeological_intensity": 0.0}
    probs = weights / total
    rng = np.random.default_rng(_seed64(seed, "weighted_poisson_catalogue", len(rows), target_catalogue))
    # Multinomial fixed-size thinning is used after the Poisson/intensity stages so
    # downstream POARI always sees a stable 30k catalogue contract.
    counts = rng.multinomial(int(target_catalogue), probs)
    out: List[Dict[str, Any]] = []
    for idx, n in enumerate(counts):
        if n <= 0:
            continue
        source = rows[idx]
        q = float(probs[idx])
        reconstruction_weight = total / max(1.0, float(target_catalogue))
        for j in range(int(n)):
            item = {
                "catalogue_id": f"AC-{len(out):06d}",
                "source_candidate_id": source["candidate_id"],
                "catalogue_sampling_probability": q,
                "catalogue_reconstruction_weight": reconstruction_weight,
                "production_cell_truth": dict(source["production_cell_truth"]),
                "deposition_truth": dict(source["deposition_truth"]),
                "biography_truth": dict(source["biography_truth"]),
                "observation_truth": dict(source.get("observation_truth", observation_probability(source))),
            }
            out.append(item)
    return out, {
        "model_version": CONDENSATION_VERSION,
        "target_catalogue": int(target_catalogue),
        "catalogue_objects": len(out),
        "represented_archaeological_intensity": total,
        "catalogue_reconstruction_weight": total / max(1, int(target_catalogue)),
        "source_candidates": len(rows),
        "effective_source_candidates": float(1.0 / np.sum(probs ** 2)),
    }


def _bin_distance(km: float) -> str:
    if km < 100: return "0-100"
    if km < 300: return "100-300"
    if km < 700: return "300-700"
    if km < 1400: return "700-1400"
    return "1400+"


def _bin_crossings(x: float) -> str:
    if x < .25: return "0"
    if x < 1.25: return "1"
    if x < 2.25: return "2"
    return "3+"


def _bin_entropy(x: float) -> str:
    if x < .20: return "low"
    if x < .55: return "medium"
    return "high"


def _distribution_from_rows(rows: Sequence[Mapping[str, Any]], weight_key: str | None = None) -> Dict[str, Dict[str, float]]:
    axes: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in rows:
        prod = r.get("production_cell_truth", {})
        dep = r.get("deposition_truth", {})
        bio = r.get("biography_truth", {})
        w = 1.0 if weight_key is None else float(r.get(weight_key, 1.0))
        axes["object_class"][str(prod.get("object_class", "unknown"))] += w
        axes["production_region"][str(prod.get("origin_region", "unknown"))] += w
        axes["deposition_region"][str(dep.get("region", "unknown"))] += w
        axes["deposition_mode"][str(dep.get("mode", "unknown"))] += w
        axes["distance_bin"][_bin_distance(float(bio.get("route_distance_km_expected", 0.0)))] += w
        axes["physical_crossings"][_bin_crossings(float(bio.get("physical_crossings_expected", 0.0)))] += w
        axes["field_crossings"][_bin_crossings(float(bio.get("field_crossings_expected", 0.0)) * 4.0)] += w
        axes["source_entropy"][_bin_entropy(float(bio.get("source_entropy_expected", 0.0)))] += w
        axes["repairs"][_bin_crossings(float(bio.get("repair_count", 0.0)))] += w
        axes["recycling"][_bin_crossings(float(bio.get("recycle_count", 0.0)))] += w
        guild = str(bio.get("guild_family_truth", "unknown"))
        axes["guild_family"][guild] += w
    out: Dict[str, Dict[str, float]] = {}
    for axis, counts in axes.items():
        total = sum(counts.values()) or 1.0
        out[axis] = {k: float(v / total) for k, v in sorted(counts.items())}
    return out


def enrichment_ratios(before: Mapping[str, Mapping[str, float]], after: Mapping[str, Mapping[str, float]]) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    for axis in sorted(set(before) | set(after)):
        keys = sorted(set(before.get(axis, {})) | set(after.get(axis, {})))
        out[axis] = {
            k: float(after.get(axis, {}).get(k, 0.0) / max(1e-12, before.get(axis, {}).get(k, 0.0)))
            for k in keys
        }
    return out


def waterfall_report(
    flow_reports: Sequence[intensity.CellFlowReport],
    candidate_rows: Sequence[Mapping[str, Any]],
    catalogue_rows: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    produced_by_class = defaultdict(float)
    lost_by_class = defaultdict(float)
    for rep in flow_reports:
        produced_by_class[rep.production_cell.object_class] += rep.produced
        lost_by_class[rep.production_cell.object_class] += rep.loss_flux

    # Candidate rows reconstruct the loss/intensity stage through their importance weights.
    loss_dist = _distribution_from_rows(candidate_rows, "importance_weight")
    observed_proxy_rows = []
    for row in candidate_rows:
        rr = dict(row)
        rr["archaeological_weight"] = expected_archaeological_weight(row)
        observed_proxy_rows.append(rr)
    observed_dist = _distribution_from_rows(observed_proxy_rows, "archaeological_weight")
    catalogue_dist = _distribution_from_rows(catalogue_rows, None)

    return {
        "model_version": CONDENSATION_VERSION,
        "stages": {
            "production": {"expected_objects": float(sum(r.produced for r in flow_reports)), "object_class_mass": dict(sorted(produced_by_class.items()))},
            "circulation": {"transfer_flux": float(sum(r.transfer_flux for r in flow_reports)), "recycle_flux": float(sum(r.recycle_flux for r in flow_reports))},
            "loss": {"expected_losses": float(sum(r.loss_flux for r in flow_reports)), "object_class_mass": dict(sorted(lost_by_class.items())), "distribution": loss_dist},
            "survival_discovery_record": {"expected_archaeological_intensity": float(sum(expected_archaeological_weight(r) for r in candidate_rows)), "distribution": observed_dist},
            "catalogue_30k": {"objects": len(catalogue_rows), "distribution": catalogue_dist},
        },
        "enrichment": {
            "loss_to_observed": enrichment_ratios(loss_dist, observed_dist),
            "observed_to_catalogue": enrichment_ratios(observed_dist, catalogue_dist),
            "loss_to_catalogue": enrichment_ratios(loss_dist, catalogue_dist),
        },
    }
