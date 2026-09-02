#!/usr/bin/env python3
from __future__ import annotations

"""Assemble the phase-07 canonical root manifest from compact shard fragments.

This is numerically equivalent to v3_phase07_assemble.py, but consumes the
lossless projections emitted only after each immutable shard has passed its
normal roundtrip validation.  It never needs the hundreds of gigabytes of shard
NetCDF files in one runner.
"""

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping

import netCDF4  # noqa: F401

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
PROJECT_ROOT = HERE.parent.parent

import v3_phase07_canonical as canonical
import v3_phase07_fragment as fragment_io
import v3_phase07_manifest as manifest


POOL_IDENTITY_FIELDS = ("node_id", "date_bc", "mode", "hydro_realization_id")


def fragment_name(start: int, stop: int) -> str:
    return f"atolia_v3_canonical_{int(start):06d}_{int(stop):06d}.fragment.json"


def preflight_fragments(
    fragment_dir: Path,
    *,
    population_cells: int,
    chunk_cells: int,
    expected_world_build_id: str | None = None,
) -> list[tuple[Path, dict[str, Any]]]:
    """Validate the entire compact-fragment set before any global merge begins."""
    population = int(population_cells)
    chunk = int(chunk_cells)
    if population <= 0 or chunk <= 0:
        raise ValueError("population_cells and chunk_cells must be positive")

    fragment_dir = Path(fragment_dir)
    expected_shards = int(math.ceil(population / chunk))
    paths = sorted(fragment_dir.rglob("*.fragment.json"))
    if len(paths) != expected_shards:
        raise RuntimeError(
            f"phase-07 fragment preflight expected {expected_shards} fragments, found {len(paths)}"
        )

    by_ordinal: dict[int, tuple[Path, dict[str, Any]]] = {}
    by_range: dict[tuple[int, int], Path] = {}
    by_hash: dict[str, Path] = {}
    world_ids: set[str] = set()

    for path in paths:
        frag = fragment_io.read_fragment(path)
        ordinal = int(frag["chunk_ordinal"])
        start = int(frag["global_cell_start"])
        stop = int(frag["global_cell_stop"])
        digest = str(frag["fragment_sha256"])
        world_id = str(frag["world_build_id"])
        record = frag["record"]

        if ordinal < 0 or ordinal >= expected_shards:
            raise RuntimeError(f"fragment {path.name} has out-of-plan ordinal {ordinal}")
        if not (0 <= start < stop <= population):
            raise RuntimeError(f"fragment {path.name} has invalid cell range {start}:{stop}")
        expected_start = ordinal * chunk
        expected_stop = min(population, expected_start + chunk)
        if (start, stop) != (expected_start, expected_stop):
            raise RuntimeError(
                f"fragment {path.name} range {start}:{stop} does not match ordinal {ordinal} "
                f"plan {expected_start}:{expected_stop}"
            )
        expected_name = fragment_name(expected_start, expected_stop)
        if path.name != expected_name:
            raise RuntimeError(f"fragment ordinal {ordinal} has unexpected filename {path.name}")
        expected_shard_name = f"atolia_v3_canonical_{expected_start:06d}_{expected_stop:06d}.nc"
        if str(frag.get("shard_name")) != expected_shard_name:
            raise RuntimeError(f"fragment {path.name} envelope shard name does not match canonical plan")
        if str(record.get("shard_name")) != expected_shard_name:
            raise RuntimeError(f"fragment {path.name} record shard name does not match canonical plan")
        if int(record.get("cell_count", -1)) != stop - start:
            raise RuntimeError(f"fragment {path.name} cell_count does not match its range")
        if ordinal in by_ordinal:
            raise RuntimeError(
                f"duplicate fragment ordinal {ordinal}: {by_ordinal[ordinal][0].name} and {path.name}"
            )
        if (start, stop) in by_range:
            raise RuntimeError(
                f"duplicate fragment range {start}:{stop}: {by_range[(start, stop)].name} and {path.name}"
            )
        if digest in by_hash:
            raise RuntimeError(
                f"duplicate fragment hash {digest}: {by_hash[digest].name} and {path.name}"
            )

        by_ordinal[ordinal] = (path, frag)
        by_range[(start, stop)] = path
        by_hash[digest] = path
        world_ids.add(world_id)

    missing_ordinals = [ordinal for ordinal in range(expected_shards) if ordinal not in by_ordinal]
    if missing_ordinals:
        raise RuntimeError(f"phase-07 fragment preflight missing ordinals {missing_ordinals}")
    if len(world_ids) != 1:
        raise RuntimeError(f"phase-07 fragment preflight found {len(world_ids)} world identities")
    only_world_id = next(iter(world_ids))
    if expected_world_build_id is not None and only_world_id != str(expected_world_build_id):
        raise RuntimeError("phase-07 fragment set belongs to a different canonical world")

    ordered = [by_ordinal[ordinal] for ordinal in range(expected_shards)]
    previous_stop = 0
    for ordinal, (path, frag) in enumerate(ordered):
        start = int(frag["global_cell_start"])
        stop = int(frag["global_cell_stop"])
        if start != previous_stop:
            raise RuntimeError(
                f"phase-07 fragment coverage gap/overlap before ordinal {ordinal}: "
                f"expected start {previous_stop}, got {start} ({path.name})"
            )
        previous_stop = stop
    if previous_stop != population:
        raise RuntimeError(
            f"phase-07 fragment coverage ends at {previous_stop}, expected {population}"
        )

    print(
        json.dumps(
            {
                "phase07_fragment_preflight": {
                    "count": len(ordered),
                    "expected_count": expected_shards,
                    "coverage": [0, population],
                    "world_build_id": only_world_id,
                    "first_fragment": ordered[0][0].name,
                    "last_fragment": ordered[-1][0].name,
                }
            },
            sort_keys=True,
        ),
        file=sys.stderr,
        flush=True,
    )
    return ordered


def _pool_origin(path: Path, frag: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "fragment": path.name,
        "chunk_ordinal": int(frag["chunk_ordinal"]),
        "global_cell_start": int(frag["global_cell_start"]),
        "global_cell_stop": int(frag["global_cell_stop"]),
    }


def _merge_pool_with_diagnostics(
    aggregate: dict[str, dict[str, Any]],
    origins: dict[str, tuple[dict[str, Any], dict[str, Any]]],
    row: Mapping[str, Any],
    *,
    path: Path,
    frag: Mapping[str, Any],
) -> None:
    """Merge one pool row, emitting the exact conflicting pair on identity collision."""
    pid = str(row["deposition_pool_id"])
    current_row = dict(row)
    current_origin = _pool_origin(path, frag)
    if pid in aggregate:
        dst = aggregate[pid]
        differing = [field for field in POOL_IDENTITY_FIELDS if str(dst[field]) != str(row[field])]
        if differing:
            first_origin, first_row = origins[pid]
            diagnostic = {
                "error": "global_deposition_pool_identity_collision",
                "deposition_pool_id": pid,
                "differing_identity_fields": differing,
                "first": {"source_fragment": first_origin, "record": first_row},
                "second": {"source_fragment": current_origin, "record": current_row},
            }
            print(
                "PHASE07_DEPOSITION_POOL_COLLISION\n"
                + json.dumps(diagnostic, indent=2, sort_keys=True, allow_nan=False),
                file=sys.stderr,
                flush=True,
            )
            raise RuntimeError(
                f"global deposition pool identity collision for {pid}; differing fields: "
                + ", ".join(differing)
            )
    else:
        origins[pid] = (current_origin, current_row)
    canonical._merge_pool(aggregate, row)


def assemble_fragments(
    hypothesis: Mapping[str, Any],
    *,
    fragment_dir: Path,
    out_path: Path,
    population_cells: int,
    chunk_cells: int,
    world_seed: int = canonical.CANONICAL_WORLD_SEED,
    workshops: int = canonical.CANONICAL_WORKSHOPS,
    steps: int = canonical.CANONICAL_STEPS,
    nodes: int = canonical.CANONICAL_NODES,
) -> dict[str, Any]:
    population = int(population_cells)
    chunk = int(chunk_cells)
    if population <= 0 or chunk <= 0:
        raise ValueError("population_cells and chunk_cells must be positive")

    config = canonical._config(
        hypothesis,
        world_seed=world_seed,
        workshops=workshops,
        steps=steps,
        nodes=nodes,
        population_cells=population,
        materialized_cells=population,
        chunk_cells=chunk,
    )
    build_id = manifest.world_build_id(config)
    fragment_dir = Path(fragment_dir)
    fragments = preflight_fragments(
        fragment_dir,
        population_cells=population,
        chunk_cells=chunk,
        expected_world_build_id=build_id,
    )

    shard_records: list[dict[str, Any]] = []
    pool_aggregate: dict[str, dict[str, Any]] = {}
    pool_origins: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    tool_aggregate: dict[str, dict[str, Any]] = {}
    workshop_signatures: set[str] = set()
    hydro_signatures: set[str] = set()
    fragment_hashes: list[str] = []
    recovery_overlays: list[dict[str, Any]] = []

    for ordinal, (path, frag) in enumerate(fragments):
        start = ordinal * chunk
        stop = min(population, start + chunk)
        record = dict(frag["record"])
        expected_shard_name = f"atolia_v3_canonical_{start:06d}_{stop:06d}.nc"
        if str(frag["world_build_id"]) != build_id:
            raise RuntimeError(f"fragment {ordinal} belongs to a different canonical world")
        if (
            int(frag["chunk_ordinal"]),
            int(frag["global_cell_start"]),
            int(frag["global_cell_stop"]),
        ) != (ordinal, start, stop):
            raise RuntimeError(f"fragment {ordinal} chunk coordinates do not match canonical plan")
        if str(record["shard_name"]) != expected_shard_name:
            raise RuntimeError(f"fragment {ordinal} shard name does not match canonical plan")

        recovery = frag.get("recovery")
        if recovery is not None:
            # The embedded record remains the immutable physical source record.
            # Only the public logical root receives the exact capsule-backed count.
            record["external_exchange_tails"] = int(
                recovery["canonical_external_exchange_tails"]
            )
            recovery_overlays.append({
                "chunk_ordinal": ordinal,
                "source_fragment_sha256": str(recovery["source_fragment_sha256"]),
                "repaired_fragment_sha256": str(frag["fragment_sha256"]),
                "source_hydro_realization_id": str(recovery["source_hydro_realization_id"]),
                "canonical_hydro_realization_id": str(recovery["canonical_hydro_realization_id"]),
                "source_hydro_realization_signature": str(
                    recovery["source_hydro_realization_signature"]
                ),
                "canonical_hydro_realization_signature": str(
                    recovery["canonical_hydro_realization_signature"]
                ),
                "source_chunk_sha256": str(recovery["source_chunk_sha256"]),
                "source_phase05_sha256": str(recovery["source_phase05_sha256"]),
                "replay_capsule_sha256": str(recovery.get("replay_capsule_sha256", "")),
                "hydro_identity_replacement_count": int(
                    recovery["hydro_identity_replacement_count"]
                ),
                "hydro_context_replacement_count": int(
                    recovery["hydro_context_replacement_count"]
                ),
                "source_external_exchange_tails": int(
                    recovery["source_external_exchange_tails"]
                ),
                "external_exchange_count_delta": int(
                    recovery["external_exchange_count_delta"]
                ),
                "canonical_external_exchange_tails": int(
                    recovery["canonical_external_exchange_tails"]
                ),
            })

        record["_flow_summary"] = frag["flow_summary"]
        record["_static_workshop_signature"] = str(frag["static_workshop_signature"])
        record["_hydro_signature"] = str(frag["hydro_realization_signature"])
        workshop_signatures.add(record["_static_workshop_signature"])
        hydro_signatures.add(record["_hydro_signature"])
        for row in frag["deposition_pools"]:
            _merge_pool_with_diagnostics(
                pool_aggregate,
                pool_origins,
                row,
                path=path,
                frag=frag,
            )
        for row in frag["tool_use"]:
            canonical._merge_tool_use(tool_aggregate, row)
        shard_records.append(record)
        fragment_hashes.append(str(frag["fragment_sha256"]))

    if len(workshop_signatures) != 1:
        raise RuntimeError("phase-07 workshop static truth differs across manifest fragments")
    if len(hydro_signatures) != 1:
        raise RuntimeError("phase-07 hydro realization differs across manifest fragments")

    pools = canonical._final_pools(pool_aggregate)
    tool_use = [tool_aggregate[key] for key in sorted(tool_aggregate)]
    flow = canonical._aggregate_flow(shard_records)
    public_shards = [{k: v for k, v in row.items() if not k.startswith("_")} for row in shard_records]

    if sum(int(row["cell_count"]) for row in public_shards) != population:
        raise RuntimeError("phase-07 fragment shard cell coverage does not close")
    if public_shards[0]["global_cell_start"] != 0 or public_shards[-1]["global_cell_stop"] != population:
        raise RuntimeError("phase-07 fragment shard endpoints do not cover the population")
    for a, b in zip(public_shards[:-1], public_shards[1:]):
        if int(a["global_cell_stop"]) != int(b["global_cell_start"]):
            raise RuntimeError("phase-07 fragment shard coverage has a gap or overlap")

    totals = {
        "loss_strata": sum(int(row["loss_strata"]) for row in shard_records),
        "particles": sum(int(row["particles"]) for row in shard_records),
        "batches": sum(int(row["batches"]) for row in shard_records),
        "operations": sum(int(row["operations"]) for row in shard_records),
        "external_exchange_tails": sum(int(row["external_exchange_tails"]) for row in shard_records),
        "deposition_assignments": sum(int(row["deposition_assignments"]) for row in shard_records),
        "archaeology_rows": sum(int(row["archaeology_rows"]) for row in shard_records),
        "global_shared_deposition_pools": sum(int(row["member_count"]) > 1 for row in pools),
        "static_workshop_signature": next(iter(workshop_signatures)),
        "hydro_realization_signature": next(iter(hydro_signatures)),
        **flow,
    }

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary = manifest.write_manifest(
        out_path,
        config=config,
        shards=public_shards,
        deposition_pools=pools,
        tool_use=tool_use,
        totals=totals,
    )
    recovery_summary = None
    if recovery_overlays:
        recovery_summary = manifest.append_recovery_metadata(out_path, recovery_overlays)
        summary["recovery"] = recovery_summary
    read = manifest.read_manifest(out_path)
    if read["phase07_manifest_sha256"] != summary["phase07_manifest_sha256"]:
        raise RuntimeError("phase-07 fragment manifest roundtrip hash mismatch")
    if read["world_build_id"] != build_id:
        raise RuntimeError("phase-07 fragment manifest world identity mismatch")
    if int(read["config"]["materialized_cells"]) != population:
        raise RuntimeError("phase-07 fragment manifest is not a full population")
    if recovery_summary is not None:
        if read.get("recovery", {}).get("recovery_overlay_sha256") != recovery_summary[
            "recovery_overlay_sha256"
        ]:
            raise RuntimeError("phase-07 recovery overlay manifest roundtrip hash mismatch")

    return {
        "latest_phase": manifest.V3_PHASE07_PHASE,
        "canonical_full": summary,
        "roundtrip": {
            "manifest_hash_equal": True,
            "world_build_id_equal": True,
            "global_cell_coverage_closed": True,
            "workshop_static_equal_across_fragments": True,
            "hydro_realization_equal_across_fragments": True,
            "global_deposition_pools_merged": True,
            "global_tool_use_merged": True,
            **({"recovery_overlay_hash_equal": True} if recovery_summary is not None else {}),
        },
        "flow_summary": flow,
        "fragment_set": {
            "schema": fragment_io.FRAGMENT_SCHEMA,
            "hash_policy": fragment_io.FRAGMENT_HASH_POLICY,
            "count": len(fragment_hashes),
            "first_sha256": fragment_hashes[0],
            "last_sha256": fragment_hashes[-1],
            "repaired_count": len(recovery_overlays),
        },
        "runner": {
            "population_cells": population,
            "materialized_cells": population,
            "chunk_cells": chunk,
            "shards": len(public_shards),
            "assembly_only": True,
            "source_kind": "lossless-manifest-fragments",
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Assemble Atolia v3 phase-07 canonical manifest from fragments")
    ap.add_argument("--hypothesis", type=Path, default=Path("hypotheses/atolia_atesis_1800_1000_v0.json"))
    ap.add_argument("--fragment-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--population-cells", type=int, required=True)
    ap.add_argument("--chunk-cells", type=int, required=True)
    ap.add_argument("--world-seed", type=int, default=canonical.CANONICAL_WORLD_SEED)
    ap.add_argument("--workshops", type=int, default=canonical.CANONICAL_WORKSHOPS)
    ap.add_argument("--steps", type=int, default=canonical.CANONICAL_STEPS)
    ap.add_argument("--nodes", type=int, default=canonical.CANONICAL_NODES)
    args = ap.parse_args()

    hypothesis_path = args.hypothesis if args.hypothesis.is_absolute() else PROJECT_ROOT / args.hypothesis
    hypothesis = json.loads(hypothesis_path.read_text(encoding="utf-8"))
    result = assemble_fragments(
        hypothesis,
        fragment_dir=args.fragment_dir,
        out_path=args.out,
        population_cells=args.population_cells,
        chunk_cells=args.chunk_cells,
        world_seed=args.world_seed,
        workshops=args.workshops,
        steps=args.steps,
        nodes=args.nodes,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
