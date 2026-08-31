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


def fragment_name(start: int, stop: int) -> str:
    return f"atolia_v3_canonical_{int(start):06d}_{int(stop):06d}.fragment.json"


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

    shard_records: list[dict[str, Any]] = []
    pool_aggregate: dict[str, dict[str, Any]] = {}
    tool_aggregate: dict[str, dict[str, Any]] = {}
    workshop_signatures: set[str] = set()
    hydro_signatures: set[str] = set()
    fragment_hashes: list[str] = []

    expected_shards = int(math.ceil(population / chunk))
    for ordinal in range(expected_shards):
        start = ordinal * chunk
        stop = min(population, start + chunk)
        path = fragment_dir / fragment_name(start, stop)
        if not path.is_file():
            raise FileNotFoundError(f"missing canonical fragment {path.name}")
        frag = fragment_io.read_fragment(path)
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

        record["_flow_summary"] = frag["flow_summary"]
        record["_static_workshop_signature"] = str(frag["static_workshop_signature"])
        record["_hydro_signature"] = str(frag["hydro_realization_signature"])
        workshop_signatures.add(record["_static_workshop_signature"])
        hydro_signatures.add(record["_hydro_signature"])
        for row in frag["deposition_pools"]:
            canonical._merge_pool(pool_aggregate, row)
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
    read = manifest.read_manifest(out_path)
    if read["phase07_manifest_sha256"] != summary["phase07_manifest_sha256"]:
        raise RuntimeError("phase-07 fragment manifest roundtrip hash mismatch")
    if read["world_build_id"] != build_id:
        raise RuntimeError("phase-07 fragment manifest world identity mismatch")
    if int(read["config"]["materialized_cells"]) != population:
        raise RuntimeError("phase-07 fragment manifest is not a full population")

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
        },
        "flow_summary": flow,
        "fragment_set": {
            "schema": fragment_io.FRAGMENT_SCHEMA,
            "hash_policy": fragment_io.FRAGMENT_HASH_POLICY,
            "count": len(fragment_hashes),
            "first_sha256": fragment_hashes[0],
            "last_sha256": fragment_hashes[-1],
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
