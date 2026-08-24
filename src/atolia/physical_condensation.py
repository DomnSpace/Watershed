from __future__ import annotations

import hashlib
import math
from typing import Any, Dict, Mapping, MutableMapping, Sequence, Tuple, List

import numpy as np

import archaeological_condensation_v3 as legacy


CONDENSATION_VERSION = "archaeological-condensation-v4-physical"


def _seed64(*parts: Any) -> int:
    return int.from_bytes(hashlib.sha256("|".join(str(x) for x in parts).encode()).digest()[:8], "big")


def survival_probability(row: Mapping[str, Any]) -> float:
    p = legacy.survival_probability(row)
    artifact = row.get("artifact_truth")
    if artifact:
        integrity = float(artifact["corrosion"]["integrity_fraction"])
        metal_loss = float(artifact["corrosion"]["metal_loss_fraction"])
        # Survival is not 'good condition': a heavily mineralized object can survive,
        # but extreme physical loss reduces recognizable archaeological survival.
        physical = .72 + .36 * integrity - .18 * metal_loss
        p *= float(np.clip(physical, .45, 1.08))
    return float(np.clip(p, .02, .97))


def discovery_probability(row: Mapping[str, Any]) -> float:
    p = legacy.discovery_probability(row)
    artifact = row.get("artifact_truth")
    if artifact:
        mass = float(artifact["identity"]["mass_kg_present"])
        context = str(artifact["find_context"]["recovery_method"])
        visibility = .80 + .20 * min(1.0, math.log1p(4 * mass) / math.log(21))
        if "dredging" in context or "controlled" in context or "excavation" in context:
            visibility *= 1.08
        p *= visibility
    return float(np.clip(p, .0002, .09))


def record_probability(row: Mapping[str, Any]) -> float:
    return legacy.record_probability(row)


def observation_probability(row: Mapping[str, Any]) -> Dict[str, float]:
    ps = survival_probability(row); pd = discovery_probability(row); pr = record_probability(row)
    return {"p_survival": ps, "p_discovery": pd, "p_record": pr,
            "p_observed_given_loss": float(ps * pd * pr)}


def expected_archaeological_weight(row: Mapping[str, Any]) -> float:
    return float(row["importance_weight"]) * observation_probability(row)["p_observed_given_loss"]


def assign_observation_truth(rows: Sequence[MutableMapping[str, Any]]) -> None:
    for row in rows:
        obs = observation_probability(row)
        row["observation_truth"] = {"model_version": CONDENSATION_VERSION, **obs,
                                    "expected_archaeological_weight": expected_archaeological_weight(row)}


def weighted_poisson_catalogue(rows: Sequence[Mapping[str, Any]], target_catalogue: int = 30_000,
                               seed: int = 1) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not rows:
        return [], {"target_catalogue": int(target_catalogue), "catalogue_objects": 0}
    weights = np.asarray([expected_archaeological_weight(r) for r in rows], dtype=float)
    weights = np.maximum(weights, 0.0); total = float(weights.sum())
    if total <= 0:
        return [], {"target_catalogue": int(target_catalogue), "catalogue_objects": 0,
                    "represented_archaeological_intensity": 0.0}
    probs = weights / total
    rng = np.random.default_rng(_seed64(seed, "physical_catalogue", len(rows), target_catalogue))
    counts = rng.multinomial(int(target_catalogue), probs)
    out: List[Dict[str, Any]] = []
    reconstruction_weight = total / max(1, int(target_catalogue))
    for idx, n in enumerate(counts):
        if n <= 0: continue
        source = rows[idx]; q = float(probs[idx])
        for _ in range(int(n)):
            out.append({
                "catalogue_id": f"AC-{len(out):06d}",
                "source_candidate_id": source["candidate_id"],
                "catalogue_sampling_probability": q,
                "catalogue_reconstruction_weight": reconstruction_weight,
                "production_cell_truth": dict(source["production_cell_truth"]),
                "deposition_truth": dict(source["deposition_truth"]),
                "biography_truth": dict(source["biography_truth"]),
                "artifact_truth": dict(source["artifact_truth"]),
                "observation_truth": dict(source.get("observation_truth", observation_probability(source))),
            })
    return out, {
        "model_version": CONDENSATION_VERSION,
        "target_catalogue": int(target_catalogue), "catalogue_objects": len(out),
        "represented_archaeological_intensity": total,
        "catalogue_reconstruction_weight": reconstruction_weight,
        "source_candidates": len(rows),
        "effective_source_candidates": float(1.0 / np.sum(probs ** 2)),
        "physical_truth_preserved": True,
    }


def waterfall_report(flow_reports: Sequence[Any], candidate_rows: Sequence[Mapping[str, Any]],
                     catalogue_rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    # Reuse the mature distribution/enrichment reporter, but feed it weights computed
    # from this physical observation model.
    proxy = []
    for r in candidate_rows:
        item = dict(r)
        item["importance_weight"] = float(r["importance_weight"])
        proxy.append(item)
    report = legacy.waterfall_report(flow_reports, proxy, catalogue_rows)
    report["model_version"] = CONDENSATION_VERSION
    report["physical_truth_preserved"] = True
    report["stages"]["survival_discovery_record"]["expected_archaeological_intensity"] = float(
        sum(expected_archaeological_weight(r) for r in candidate_rows)
    )
    return report
