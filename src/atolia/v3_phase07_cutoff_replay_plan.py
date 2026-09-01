#!/usr/bin/env python3
from __future__ import annotations

"""Diagnose the phase-07 hydro cutoff bifurcation and plan exact replay.

This is recovery tooling. It does not mutate source shards or reinterpret the
scientific model. It compares the two recovered hydro realizations, rebuilds the
provisional connector candidate ranking once from the frozen source model, and
identifies the exact minority shards whose downstream phase-05 rows would need
counterfactual replay under one observed canonical realization.
"""

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
PROJECT_ROOT = HERE.parent.parent

import archaeology_temporal_world as archaeology
import release_candidate_invariants as release_invariants
import v3_hydro_exchange_deposition as phase05
import v3_phase07_canonical as canonical


SCHEMA = "atolia-v3-phase07-cutoff-replay-plan-v1"
BOUNDARY_RADIUS = 30


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _hydro_context(realization: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    values: dict[str, list[float]] = defaultdict(list)
    for row in realization:
        if not bool(row["realized"]):
            continue
        values[str(row["a"])].append(float(row["navigability"]))
        values[str(row["b"])].append(float(row["navigability"]))
    return {
        node: sum(rows) / len(rows)
        for node, rows in values.items()
        if rows
    }


def _realization_id(snapshot: Mapping[str, Any]) -> str:
    ids = {str(row["realization_id"]) for row in snapshot["hydro_realization"]}
    if len(ids) != 1:
        raise RuntimeError(f"snapshot expected one realization id, found {sorted(ids)}")
    return next(iter(ids))


def _provisional_ids(snapshot: Mapping[str, Any]) -> set[str]:
    return {
        str(row["edge_id"])
        for row in snapshot["hydro_ensemble"]
        if not bool(row["structural"])
        and not row.get("evidence_ids")
        and str(row.get("probability_basis", "")) == "provisional-short-range-water-connector-prior"
    }


def _candidate_universe(world: Any) -> tuple[list[dict[str, Any]], int, int]:
    evidence = phase05._structural_hydro_evidence(world)
    structural_pairs = {
        phase05._edge_key(row.a, row.b)
        for row in evidence
        if row.evidence_kind == "model_graph_edge"
    }
    water_nodes = sorted(str(node.id) for node in world.nodes.values() if phase05._water_node(node.kind))
    candidates: list[dict[str, Any]] = []
    mode = "minor_channel_or_wetland_connector"
    for index, a in enumerate(water_nodes):
        for b in water_nodes[index + 1:]:
            key = phase05._edge_key(a, b)
            if key in structural_pairs:
                continue
            km = phase05._edge_km(world, a, b)
            if km > phase05.MAX_CANDIDATE_CONNECTOR_KM:
                continue
            probability, navigability, score = phase05._candidate_prior(world, a, b)
            candidates.append({
                "edge_id": phase05._stable_id("hed", a, b, mode),
                "a": a,
                "b": b,
                "km": float(km),
                "probability": float(probability),
                "navigability": float(navigability),
                "score": float(score),
            })
    candidates.sort(key=lambda row: (-row["score"], row["a"], row["b"]))
    target_extra = int(round(
        max(0.0, phase05.CANDIDATE_DENSITY_MULTIPLIER - 1.0)
        * max(1, len(structural_pairs))
    ))
    return candidates, target_extra, len(structural_pairs)


def _float_detail(value: float) -> dict[str, Any]:
    x = float(value)
    return {
        "value": x,
        "hex": x.hex(),
        "ulp": math.ulp(x) if math.isfinite(x) else None,
    }


def _candidate_row(
    row: Mapping[str, Any],
    *,
    rank: int,
    cutoff_score: float,
    selected_a: set[str],
    selected_b: set[str],
) -> dict[str, Any]:
    score = float(row["score"])
    ulp = math.ulp(cutoff_score)
    return {
        "rank_1based": int(rank),
        "edge_id": str(row["edge_id"]),
        "a": str(row["a"]),
        "b": str(row["b"]),
        "observed_in_a": str(row["edge_id"]) in selected_a,
        "observed_in_b": str(row["edge_id"]) in selected_b,
        "km": _float_detail(float(row["km"])),
        "probability": _float_detail(float(row["probability"])),
        "navigability": _float_detail(float(row["navigability"])),
        "score": _float_detail(score),
        "score_delta_from_cutoff": score - cutoff_score,
        "score_delta_from_cutoff_ulps": ((score - cutoff_score) / ulp) if ulp else None,
    }


def build_report(
    *,
    hypothesis: Mapping[str, Any],
    snapshots: Sequence[Mapping[str, Any]],
    fragments: Sequence[Mapping[str, Any]],
    boundary_radius: int = BOUNDARY_RADIUS,
) -> dict[str, Any]:
    if len(snapshots) != 2:
        raise RuntimeError(f"expected two representative hydro snapshots, found {len(snapshots)}")
    snaps = sorted(snapshots, key=lambda row: int(row["chunk_ordinal"]))
    a, b = snaps
    if str(a["world_build_id"]) != str(b["world_build_id"]):
        raise RuntimeError("hydro snapshots belong to different world_build_id values")

    rid_a, rid_b = _realization_id(a), _realization_id(b)
    if rid_a == rid_b:
        raise RuntimeError("representative snapshots do not span both hydro realizations")

    fragment_hydro_counts: Counter[str] = Counter()
    fragment_variant: dict[int, str] = {}
    for frag in fragments:
        ids = {str(row["hydro_realization_id"]) for row in frag.get("deposition_pools", [])}
        if len(ids) != 1:
            raise RuntimeError(
                f"fragment ordinal {frag['chunk_ordinal']} expected one deposition hydro id, found {sorted(ids)}"
            )
        rid = next(iter(ids))
        fragment_hydro_counts[rid] += 1
        fragment_variant[int(frag["chunk_ordinal"])] = rid
    if set(fragment_hydro_counts) != {rid_a, rid_b}:
        raise RuntimeError(
            "recovered fragments and representative snapshots disagree on hydro realization ids: "
            f"fragments={sorted(fragment_hydro_counts)}, snapshots={sorted((rid_a, rid_b))}"
        )

    canonical_rid = max((rid_a, rid_b), key=lambda rid: (fragment_hydro_counts[rid], rid))
    minority_rid = rid_b if canonical_rid == rid_a else rid_a
    canonical_snapshot = a if _realization_id(a) == canonical_rid else b
    minority_snapshot = b if canonical_snapshot is a else a

    selected_a = _provisional_ids(a)
    selected_b = _provisional_ids(b)
    only_a = sorted(selected_a - selected_b)
    only_b = sorted(selected_b - selected_a)
    boundary_ids = set(only_a) | set(only_b)

    context_a = _hydro_context(a["hydro_realization"])
    context_b = _hydro_context(b["hydro_realization"])
    affected_nodes: list[dict[str, Any]] = []
    for node in sorted(set(context_a) | set(context_b)):
        va = float(context_a.get(node, 0.0))
        vb = float(context_b.get(node, 0.0))
        if va != vb:
            canonical_value = va if canonical_snapshot is a else vb
            minority_value = vb if canonical_snapshot is a else va
            delta = canonical_value - minority_value
            affected_nodes.append({
                "node_id": node,
                "a": va,
                "b": vb,
                "canonical": canonical_value,
                "minority": minority_value,
                "canonical_minus_minority": delta,
                "external_probability_delta": 0.008 * delta,
            })
    affected_node_ids = {row["node_id"] for row in affected_nodes}

    affected_ordinals: set[int] = set()
    affected_minority_pool_rows = 0
    affected_canonical_pool_rows = 0
    for frag in fragments:
        ordinal = int(frag["chunk_ordinal"])
        rid = fragment_variant[ordinal]
        touched = False
        for row in frag.get("deposition_pools", []):
            if str(row["node_id"]) not in affected_node_ids:
                continue
            touched = True
            if rid == minority_rid:
                affected_minority_pool_rows += 1
            else:
                affected_canonical_pool_rows += 1
        if touched and rid == minority_rid:
            affected_ordinals.add(ordinal)

    # Rebuild only the static world and hydro candidate ranking. No production-cell
    # propagation or phase-05 materialization is performed here.
    release_invariants.install()
    world = archaeology.TemporalFieldArchaeologicalWorld(
        hypothesis,
        seed=int(canonical.CANONICAL_WORLD_SEED),
        target_geography_nodes=int(canonical.CANONICAL_NODES),
    )
    world.build(workshop_count=int(canonical.CANONICAL_WORKSHOPS))
    candidates, target_extra, structural_count = _candidate_universe(world)
    if target_extra <= 0 or target_extra > len(candidates):
        raise RuntimeError(
            f"invalid hydro candidate cutoff target_extra={target_extra}, candidates={len(candidates)}"
        )

    candidate_by_id = {str(row["edge_id"]): (rank, row) for rank, row in enumerate(candidates, start=1)}
    cutoff_score = float(candidates[target_extra - 1]["score"])
    lo = max(1, target_extra - int(boundary_radius))
    hi = min(len(candidates), target_extra + int(boundary_radius))
    neighborhood = [
        _candidate_row(
            candidates[rank - 1],
            rank=rank,
            cutoff_score=cutoff_score,
            selected_a=selected_a,
            selected_b=selected_b,
        )
        for rank in range(lo, hi + 1)
    ]

    boundary_ranks = []
    missing_boundary = []
    for edge_id in sorted(boundary_ids):
        found = candidate_by_id.get(edge_id)
        if found is None:
            missing_boundary.append(edge_id)
            continue
        rank, row = found
        boundary_ranks.append(
            _candidate_row(
                row,
                rank=rank,
                cutoff_score=cutoff_score,
                selected_a=selected_a,
                selected_b=selected_b,
            )
        )

    rebuilt_selected = {str(row["edge_id"]) for row in candidates[:target_extra]}
    rebuilt_match = {
        "a": rebuilt_selected == selected_a,
        "b": rebuilt_selected == selected_b,
        "intersection_with_a": len(rebuilt_selected & selected_a),
        "intersection_with_b": len(rebuilt_selected & selected_b),
        "rebuilt_selected_count": len(rebuilt_selected),
        "observed_a_selected_count": len(selected_a),
        "observed_b_selected_count": len(selected_b),
    }

    cutoff_ulp = math.ulp(cutoff_score)
    exact_tie = [row for row in candidates if float(row["score"]) == cutoff_score]
    one_ulp_band = [row for row in candidates if abs(float(row["score"]) - cutoff_score) <= cutoff_ulp]
    eight_ulp_band = [row for row in candidates if abs(float(row["score"]) - cutoff_score) <= 8.0 * cutoff_ulp]
    thirtytwo_ulp_band = [row for row in candidates if abs(float(row["score"]) - cutoff_score) <= 32.0 * cutoff_ulp]

    replay_artifacts = []
    population_cells = 37100
    chunk_cells = 64
    for ordinal in sorted(affected_ordinals):
        start = ordinal * chunk_cells
        stop = min(population_cells, start + chunk_cells)
        replay_artifacts.append({
            "chunk_ordinal": ordinal,
            "source_artifact": f"atolia-v3-canonical-shard-{ordinal}",
            "source_shard": f"atolia_v3_canonical_{start:06d}_{stop:06d}.nc",
            "global_cell_start": start,
            "global_cell_stop": stop,
        })

    return {
        "schema": SCHEMA,
        "world_build_id": str(a["world_build_id"]),
        "observed_variants": {
            "a": {"chunk_ordinal": int(a["chunk_ordinal"]), "hydro_realization_id": rid_a},
            "b": {"chunk_ordinal": int(b["chunk_ordinal"]), "hydro_realization_id": rid_b},
            "fragment_counts": dict(sorted(fragment_hydro_counts.items())),
            "recovery_canonical_rule": "observed-majority-realization; no synthetic third topology",
            "canonical_hydro_realization_id": canonical_rid,
            "minority_hydro_realization_id": minority_rid,
        },
        "observed_boundary": {
            "only_a_count": len(only_a),
            "only_b_count": len(only_b),
            "only_a": only_a,
            "only_b": only_b,
            "affected_node_count": len(affected_nodes),
            "affected_nodes": affected_nodes,
        },
        "rebuilt_cutoff": {
            "structural_pair_count": structural_count,
            "candidate_count": len(candidates),
            "target_extra": target_extra,
            "cutoff_rank_1based": target_extra,
            "cutoff_score": _float_detail(cutoff_score),
            "rebuilt_selected_match": rebuilt_match,
            "boundary_radius": int(boundary_radius),
            "neighborhood": neighborhood,
            "boundary_ranks": boundary_ranks,
            "boundary_ids_missing_from_rebuilt_candidate_universe": missing_boundary,
            "tie_band_counts": {
                "exact_score": len(exact_tie),
                "within_1_ulp": len(one_ulp_band),
                "within_8_ulps": len(eight_ulp_band),
                "within_32_ulps": len(thirtytwo_ulp_band),
            },
        },
        "selective_replay": {
            "minority_fragment_count": fragment_hydro_counts[minority_rid],
            "affected_minority_shard_count": len(affected_ordinals),
            "affected_minority_shard_ordinals": sorted(affected_ordinals),
            "affected_minority_pool_rows": affected_minority_pool_rows,
            "affected_canonical_pool_rows": affected_canonical_pool_rows,
            "source_artifacts_needed": replay_artifacts,
            "exact_replay_rule": {
                "hydro_context": "replace minority affected-node context with canonical observed context",
                "external_exchange": "recompute p with canonical context and reuse deterministic particle threshold draw; ADD/REMOVE/UPDATE exactly",
                "deposition_mode": "unchanged; deterministic mode draw and mode weights are hydro-independent",
                "deposition_pool_id": "unchanged; identity is node/date/mode",
                "hydro_realization_id": "replace with canonical observed realization id",
                "archaeology": "unchanged if deposition mode remains unchanged",
            },
            "required_replay_capsule_fields": [
                "particle_id",
                "production_cell_index",
                "loss_node_id",
                "date_bc",
                "object_class",
                "cumulative_metal_distance_km",
                "represented_weight",
                "external_component_or_inputs_needed_to_rederive_it",
                "old_external_exchange_presence",
                "old_external_contact_probability_if_present",
                "deposition_pool_id",
                "deposition_mode",
                "old_hydro_context_score",
                "source_chunk_sha256",
                "source_phase05_sha256",
            ],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hypothesis", type=Path, default=Path("hypotheses/atolia_atesis_1800_1000_v0.json"))
    parser.add_argument("--snapshots-dir", type=Path, required=True)
    parser.add_argument("--fragments-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--boundary-radius", type=int, default=BOUNDARY_RADIUS)
    args = parser.parse_args()

    hypothesis_path = args.hypothesis if args.hypothesis.is_absolute() else PROJECT_ROOT / args.hypothesis
    hypothesis = _read_json(hypothesis_path)
    snapshot_paths = sorted(args.snapshots_dir.glob("**/hydro-*.json"))
    fragment_paths = sorted(args.fragments_dir.glob("**/*.fragment.json"))
    if len(snapshot_paths) != 2:
        raise RuntimeError(f"expected 2 hydro snapshots, found {len(snapshot_paths)}")
    if len(fragment_paths) != 580:
        raise RuntimeError(f"expected 580 recovered fragments, found {len(fragment_paths)}")

    report = build_report(
        hypothesis=hypothesis,
        snapshots=[_read_json(path) for path in snapshot_paths],
        fragments=[_read_json(path) for path in fragment_paths],
        boundary_radius=args.boundary_radius,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "schema": report["schema"],
        "canonical_hydro_realization_id": report["observed_variants"]["canonical_hydro_realization_id"],
        "minority_hydro_realization_id": report["observed_variants"]["minority_hydro_realization_id"],
        "boundary_counts": [
            report["observed_boundary"]["only_a_count"],
            report["observed_boundary"]["only_b_count"],
        ],
        "affected_nodes": report["observed_boundary"]["affected_node_count"],
        "candidate_cutoff_rank": report["rebuilt_cutoff"]["cutoff_rank_1based"],
        "rebuilt_match": report["rebuilt_cutoff"]["rebuilt_selected_match"],
        "tie_band_counts": report["rebuilt_cutoff"]["tie_band_counts"],
        "affected_minority_shards": report["selective_replay"]["affected_minority_shard_count"],
        "out": str(args.out),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
