#!/usr/bin/env python3
from __future__ import annotations

"""Extract an exact phase-05 counterfactual replay capsule from one source shard.

Recovery-only tooling. The source NetCDF is opened read-only through the ordinary
validated readers. The capsule records every lineage at a hydro-context node that
changes between the recovered minority and chosen observed canonical realization,
then replays only the deterministic external-exchange threshold under canonical
hydro context. Deposition mode/pool identity are verified as hydro-independent;
no source file is mutated.
"""

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
PROJECT_ROOT = HERE.parent.parent

import archaeology_temporal_world as archaeology
import intensity_circulation as intensity
import release_candidate_invariants as release_invariants
import v3_biography_netcdf
import v3_hydro_exchange_deposition as phase05
import v3_phase07_canonical as canonical
import v3_phase07_manifest as manifest


SCHEMA = "atolia-v3-phase07-replay-capsule-v1"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _external_probability(particle: Mapping[str, Any], cell: Any, water: float) -> tuple[float, str, str]:
    component, trigger = phase05._external_component(cell)
    prestige = float(str(particle["object_class"]) in phase05.PRESTIGE_CLASSES)
    distance = min(1500.0, max(0.0, float(particle["cumulative_metal_distance_km"])))
    tagged = float(trigger == "source-or-bundle-tagged")
    probability = phase05._clip(
        .006 + .010 * prestige + .010 * min(1.0, distance / 700.0) + .008 * float(water) + .025 * tagged,
        .001,
        .065,
    )
    return float(probability), str(component), str(trigger)


def _new_external_row(
    particle: Mapping[str, Any],
    *,
    component: str,
    trigger: str,
    probability: float,
    world_seed: int,
) -> dict[str, Any]:
    intensity = .02 + .10 * phase05._uniform01(world_seed, particle["particle_id"], "external-exchange-intensity")
    return {
        "exchange_id": phase05._stable_id("ex", particle["particle_id"], component),
        "particle_id": str(particle["particle_id"]),
        "external_component_id": str(component),
        "trigger": str(trigger),
        "contact_probability": float(probability),
        "contact_intensity": float(intensity),
        "node_id": str(particle["loss_node_id"]),
        "date_bc": int(particle["date_bc"]),
        "represented_weight": float(particle["represented_weight"]),
    }


def extract_capsule(
    *,
    hypothesis: Mapping[str, Any],
    shard_path: Path,
    plan: Mapping[str, Any],
    ordinal: int,
    population_cells: int = 37100,
    chunk_cells: int = 64,
) -> dict[str, Any]:
    ordinal = int(ordinal)
    start = ordinal * int(chunk_cells)
    stop = min(int(population_cells), start + int(chunk_cells))
    config = canonical._config(
        hypothesis,
        world_seed=canonical.CANONICAL_WORLD_SEED,
        workshops=canonical.CANONICAL_WORKSHOPS,
        steps=canonical.CANONICAL_STEPS,
        nodes=canonical.CANONICAL_NODES,
        population_cells=int(population_cells),
        materialized_cells=int(population_cells),
        chunk_cells=int(chunk_cells),
    )
    build_id = manifest.world_build_id(config)
    record, _, read05 = canonical._read_existing_shard(
        Path(shard_path),
        expected_world_build_id=build_id,
        ordinal=ordinal,
        start=start,
        stop=stop,
    )
    bio = v3_biography_netcdf.read_biography(Path(shard_path))

    canonical_rid = str(plan["observed_variants"]["canonical_hydro_realization_id"])
    minority_rid = str(plan["observed_variants"]["minority_hydro_realization_id"])
    affected = {
        str(row["node_id"]): {
            "canonical": float(row["canonical"]),
            "minority": float(row["minority"]),
        }
        for row in plan["observed_boundary"]["affected_nodes"]
    }

    source_realization_ids = {str(row["realization_id"]) for row in read05["hydro_realization"]}
    if source_realization_ids != {minority_rid}:
        raise RuntimeError(
            f"replay shard {ordinal} is not the expected minority realization: "
            f"found={sorted(source_realization_ids)} expected={minority_rid}"
        )

    # Reconstruct only static world + production-cell descriptors. This is enough
    # to reproduce _external_component exactly and deliberately does not rerun
    # circulation, biographies, deposition choices, or archaeology.
    release_invariants.install()
    world = archaeology.TemporalFieldArchaeologicalWorld(
        hypothesis,
        seed=int(canonical.CANONICAL_WORLD_SEED),
        target_geography_nodes=int(canonical.CANONICAL_NODES),
    )
    world.build(workshop_count=int(canonical.CANONICAL_WORKSHOPS))
    all_cells = intensity.production_cells(world)
    if len(all_cells) != int(population_cells):
        raise RuntimeError(f"production cell count changed during replay extraction: {len(all_cells)}")

    assignments = {str(row["particle_id"]): dict(row) for row in read05["deposition_assignments"]}
    old_external = {str(row["particle_id"]): dict(row) for row in read05["external_exchange"]}
    particles = [dict(row) for row in bio["particles"] if str(row["loss_node_id"]) in affected]
    if not particles:
        raise RuntimeError(f"planned affected replay shard {ordinal} contains no affected-node particles")

    replay_rows: list[dict[str, Any]] = []
    actions: Counter[str] = Counter()
    pool_ids: set[str] = set()
    max_old_probability_error = 0.0

    for particle in particles:
        pid = str(particle["particle_id"])
        node = str(particle["loss_node_id"])
        assignment = assignments.get(pid)
        if assignment is None:
            raise RuntimeError(f"missing deposition assignment for affected particle {pid}")
        if str(assignment["node_id"]) != node:
            raise RuntimeError(f"particle/deposition node mismatch for {pid}")
        if str(assignment["hydro_realization_id"]) != minority_rid:
            raise RuntimeError(f"affected assignment is not minority hydro realization for {pid}")

        old_water = float(assignment["hydro_context_score"])
        expected_old_water = float(affected[node]["minority"])
        if abs(old_water - expected_old_water) > 5e-13:
            raise RuntimeError(
                f"minority hydro context mismatch for {pid}: assignment={old_water!r} plan={expected_old_water!r}"
            )
        new_water = float(affected[node]["canonical"])

        cell_index = int(particle["production_cell_index"])
        if not 0 <= cell_index < len(all_cells):
            raise RuntimeError(f"production cell index outside rebuilt population for {pid}")
        cell = all_cells[cell_index]
        rebuilt_bundle_id = str(getattr(cell, "bundle_id", ""))
        if rebuilt_bundle_id != str(particle["bundle_id"]):
            raise RuntimeError(
                f"production cell bundle mismatch for {pid}: particle={particle['bundle_id']!r} rebuilt={rebuilt_bundle_id!r}"
            )

        old_p, component, trigger = _external_probability(particle, cell, old_water)
        new_p, component2, trigger2 = _external_probability(particle, cell, new_water)
        if (component, trigger) != (component2, trigger2):
            raise RuntimeError(f"hydro context unexpectedly changed external component classification for {pid}")
        draw = float(phase05._uniform01(canonical.CANONICAL_WORLD_SEED, pid, "external-exchange-tail"))
        old_expected = bool(draw < old_p)
        new_expected = bool(draw < new_p)
        old_row = old_external.get(pid)
        if bool(old_row is not None) != old_expected:
            raise RuntimeError(
                f"source external threshold does not roundtrip for {pid}: draw={draw} p={old_p} present={old_row is not None}"
            )
        if old_row is not None:
            if (str(old_row["external_component_id"]), str(old_row["trigger"])) != (component, trigger):
                raise RuntimeError(f"source external component/trigger does not roundtrip for {pid}")
            err = abs(float(old_row["contact_probability"]) - old_p)
            max_old_probability_error = max(max_old_probability_error, err)
            if err > 5e-15:
                raise RuntimeError(f"source external contact probability does not roundtrip for {pid}: delta={err}")

        if not old_expected and not new_expected:
            action = "UNCHANGED_ABSENT"
        elif old_expected and new_expected:
            action = "UPDATE"
        elif old_expected and not new_expected:
            action = "REMOVE"
        else:
            action = "ADD"
        actions[action] += 1
        new_row = (
            _new_external_row(
                particle,
                component=component,
                trigger=trigger,
                probability=new_p,
                world_seed=canonical.CANONICAL_WORLD_SEED,
            )
            if new_expected else None
        )
        pool_ids.add(str(assignment["deposition_pool_id"]))

        source_mix_keys = sorted(str(k) for k in getattr(cell, "source_mix", {}).keys())
        replay_rows.append({
            "particle_id": pid,
            "production_cell_index": cell_index,
            "production_cell_id": str(particle["production_cell_id"]),
            "bundle_id": str(particle["bundle_id"]),
            "rebuilt_bundle_family": str(getattr(cell, "bundle_family", "")),
            "rebuilt_source_mix_keys": source_mix_keys,
            "loss_node_id": node,
            "date_bc": int(particle["date_bc"]),
            "object_class": str(particle["object_class"]),
            "cumulative_metal_distance_km": float(particle["cumulative_metal_distance_km"]),
            "represented_weight": float(particle["represented_weight"]),
            "external_component_id": component,
            "external_trigger": trigger,
            "external_draw": draw,
            "old_hydro_context": old_water,
            "canonical_hydro_context": new_water,
            "old_external_probability": old_p,
            "canonical_external_probability": new_p,
            "external_probability_delta": new_p - old_p,
            "old_external_present": old_expected,
            "canonical_external_present": new_expected,
            "external_action": action,
            "old_external_row": old_row,
            "canonical_external_row": new_row,
            "deposition_pool_id": str(assignment["deposition_pool_id"]),
            "deposition_mode": str(assignment["mode"]),
            "old_hydro_realization_id": str(assignment["hydro_realization_id"]),
            "canonical_hydro_realization_id": canonical_rid,
        })

    pool_replacements: list[dict[str, Any]] = []
    for pool in read05["deposition_pools"]:
        if str(pool["deposition_pool_id"]) not in pool_ids:
            continue
        node = str(pool["node_id"])
        if node not in affected:
            raise RuntimeError(f"affected replay pool unexpectedly lies outside affected nodes: {pool['deposition_pool_id']}")
        replacement = dict(pool)
        replacement["hydro_realization_id"] = canonical_rid
        replacement["hydro_context_score"] = float(affected[node]["canonical"])
        pool_replacements.append({
            "deposition_pool_id": str(pool["deposition_pool_id"]),
            "old": dict(pool),
            "canonical": replacement,
        })

    external_count_delta = int(actions["ADD"] - actions["REMOVE"])
    return {
        "schema": SCHEMA,
        "world_build_id": str(record["world_build_id"]),
        "chunk_ordinal": ordinal,
        "global_cell_start": start,
        "global_cell_stop": stop,
        "source_shard": Path(shard_path).name,
        "source_chunk_sha256": str(record["chunk_sha256"]),
        "source_phase05_sha256": str(record["phase05_sha256"]),
        "source_hydro_realization_id": minority_rid,
        "canonical_hydro_realization_id": canonical_rid,
        "affected_particle_count": len(replay_rows),
        "affected_pool_count": len(pool_replacements),
        "external_actions": dict(sorted(actions.items())),
        "external_exchange_count_old": int(record["external_exchange_tails"]),
        "external_exchange_count_delta": external_count_delta,
        "external_exchange_count_canonical": int(record["external_exchange_tails"]) + external_count_delta,
        "max_old_external_probability_roundtrip_error": float(max_old_probability_error),
        "replay_rows": replay_rows,
        "pool_replacements": pool_replacements,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hypothesis", type=Path, default=Path("hypotheses/atolia_atesis_1800_1000_v0.json"))
    ap.add_argument("--shard", type=Path, required=True)
    ap.add_argument("--plan", type=Path, required=True)
    ap.add_argument("--ordinal", type=int, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    hypothesis_path = args.hypothesis if args.hypothesis.is_absolute() else PROJECT_ROOT / args.hypothesis
    report = extract_capsule(
        hypothesis=_read_json(hypothesis_path),
        shard_path=args.shard,
        plan=_read_json(args.plan),
        ordinal=args.ordinal,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "chunk_ordinal": report["chunk_ordinal"],
        "affected_particle_count": report["affected_particle_count"],
        "affected_pool_count": report["affected_pool_count"],
        "external_actions": report["external_actions"],
        "external_exchange_count_delta": report["external_exchange_count_delta"],
        "max_old_external_probability_roundtrip_error": report["max_old_external_probability_roundtrip_error"],
        "out": str(args.out),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
