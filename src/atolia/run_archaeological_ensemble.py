#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

import numpy as np

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import archaeology_field_world as afw
import intensity_circulation as intensity
import rare_event_materializer as materializer
import archaeological_condensation_v3 as condensation


def _flatten_distribution(report: Mapping[str, Any]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    dist = report["stages"]["catalogue_30k"]["distribution"]
    for axis, values in dist.items():
        for key, value in values.items():
            out[f"{axis}/{key}"] = float(value)
    return out


def _family_metrics(report: Mapping[str, Any]) -> Dict[str, float]:
    dist = report["stages"]["catalogue_30k"]["distribution"]
    dep = dist.get("deposition_region", {})
    prod = dist.get("production_region", {})
    distance = dist.get("distance_bin", {})
    phys = dist.get("physical_crossings", {})
    field = dist.get("field_crossings", {})
    obj = dist.get("object_class", {})
    return {
        "rhine_deposition_share": float(dep.get("rhine", 0.0)),
        "lower_danube_deposition_share": float(dep.get("lower_danube", 0.0)),
        "aegean_deposition_share": float(dep.get("aegean", 0.0) + dep.get("crete", 0.0) + dep.get("western_anatolia", 0.0)),
        "britain_channel_deposition_share": float(dep.get("severn_britain", 0.0)),
        "mediterranean_deposition_share": float(dep.get("western_mediterranean", 0.0) + dep.get("central_mediterranean", 0.0) + dep.get("aegean", 0.0) + dep.get("crete", 0.0)),
        "long_distance_share": float(distance.get("700-1400", 0.0) + distance.get("1400+", 0.0)),
        "cross_system_share": float(phys.get("2", 0.0) + phys.get("3+", 0.0) + field.get("2", 0.0) + field.get("3+", 0.0)),
        "sword_share": float(obj.get("sword", 0.0)),
    }


def run_one(hypothesis: Mapping[str, Any], seed: int, steps: int, candidates: int, catalogue: int) -> Dict[str, Any]:
    world = afw.ArchaeologyFieldWorld(hypothesis, seed=seed)
    world._build_graph()
    world._build_bundles()
    reports, flow_summary = intensity.propagate_world(world, max_steps=steps)
    rows, materializer_summary = materializer.materialize_biographies(world, reports, target_candidates=candidates, seed=seed)
    condensation.assign_observation_truth(rows)
    cat, catalogue_summary = condensation.weighted_poisson_catalogue(rows, target_catalogue=catalogue, seed=seed)
    waterfall = condensation.waterfall_report(reports, rows, cat)
    return {
        "seed": seed,
        "flow": flow_summary,
        "materializer": materializer_summary,
        "catalogue": catalogue_summary,
        "waterfall": waterfall,
        "family_metrics": _family_metrics(waterfall),
    }


def summarize_ensemble(runs: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    metrics: Dict[str, List[float]] = defaultdict(list)
    distribution_values: Dict[str, List[float]] = defaultdict(list)
    for run in runs:
        for k, v in run["family_metrics"].items():
            metrics[k].append(float(v))
        for k, v in _flatten_distribution(run["waterfall"]).items():
            distribution_values[k].append(float(v))

    def stats(vals: Sequence[float]) -> Dict[str, float]:
        a = np.asarray(vals, dtype=float)
        return {
            "mean": float(a.mean()), "sd": float(a.std(ddof=0)),
            "p05": float(np.quantile(a, .05)), "p50": float(np.quantile(a, .50)),
            "p95": float(np.quantile(a, .95)), "min": float(a.min()), "max": float(a.max()),
        }

    return {
        "ensemble_size": len(runs),
        "seed_range": [int(runs[0]["seed"]), int(runs[-1]["seed"])] if runs else [],
        "family_metrics": {k: stats(v) for k, v in sorted(metrics.items())},
        "catalogue_distribution": {k: stats(v) for k, v in sorted(distribution_values.items())},
        "calibration_rule": "Tune broad priors only for systematic ensemble deviations; never tune to a preferred single-seed map.",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Run deterministic Round-4 archaeology ensembles")
    ap.add_argument("--hypothesis", type=Path, default=Path("hypotheses/atolia_atesis_1800_1000_v0.json"))
    ap.add_argument("--seed-start", type=int, default=1)
    ap.add_argument("--runs", type=int, default=20)
    ap.add_argument("--steps", type=int, default=28)
    ap.add_argument("--candidates", type=int, default=100_000)
    ap.add_argument("--catalogue", type=int, default=30_000)
    ap.add_argument("--out", type=Path, default=Path("output/archaeological_ensemble.json"))
    args = ap.parse_args()
    hypothesis = json.loads(args.hypothesis.read_text(encoding="utf-8"))
    runs = []
    for seed in range(args.seed_start, args.seed_start + args.runs):
        print(f"round4 seed {seed} ...", file=sys.stderr, flush=True)
        runs.append(run_one(hypothesis, seed, args.steps, args.candidates, args.catalogue))
    payload = {
        "model_version": condensation.CONDENSATION_VERSION,
        "parameters": {"steps": args.steps, "candidates": args.candidates, "catalogue": args.catalogue},
        "ensemble": summarize_ensemble(runs),
        "runs": runs,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload["ensemble"], indent=2))


if __name__ == "__main__":
    main()
