#!/usr/bin/env python3
from __future__ import annotations

"""Build exactly one durable Atolia v3 phase-07 canonical shard.

This is the cloud-matrix worker. Every invocation rebuilds the same canonical
world, materializes one global production-cell interval, writes one immutable
NetCDF shard, validates its phase-07 marker, and exits. No manifest is written
here; v3_phase07_assemble.py merges independently uploaded shards afterwards.
"""

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any, Mapping

import netCDF4  # noqa: F401

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
PROJECT_ROOT = HERE.parent.parent

import build_v3_master
import intensity_circulation as intensity
import release_candidate_invariants as release_invariants
import v3_phase07_canonical as canonical
import v3_phase07_manifest as manifest


def _stage(message: str, started: float | None = None) -> float:
    now = time.perf_counter()
    if started is None:
        print(f"phase07 worker: {message}", file=sys.stderr, flush=True)
    else:
        print(
            f"phase07 worker: {message} in {now - started:.3f}s",
            file=sys.stderr,
            flush=True,
        )
    return now


def build_one_shard(
    hypothesis: Mapping[str, Any],
    *,
    out_dir: Path,
    start: int,
    stop: int,
    chunk_cells: int,
    expected_population: int | None = None,
    world_seed: int = canonical.CANONICAL_WORLD_SEED,
    workshops: int = canonical.CANONICAL_WORKSHOPS,
    steps: int = canonical.CANONICAL_STEPS,
    nodes: int = canonical.CANONICAL_NODES,
) -> dict[str, Any]:
    if chunk_cells <= 0:
        raise ValueError("chunk_cells must be positive")
    if start < 0 or stop <= start:
        raise ValueError("invalid phase-07 shard interval")

    worker_started = _stage(
        f"start cells {start}:{stop}; seed={world_seed}; workshops={workshops}; "
        f"steps={steps}; nodes={nodes}"
    )
    release_version = release_invariants.install()
    world = canonical.archaeology.TemporalFieldArchaeologicalWorld(
        hypothesis,
        seed=int(world_seed),
        target_geography_nodes=int(nodes),
    )
    world_started = _stage("building canonical static world")
    world.build(workshop_count=int(workshops))
    world_finished = _stage("canonical static world built", world_started)

    mass_error = float(release_invariants.production_mass_error(world))
    tolerance = build_v3_master._production_mass_tolerance_kg(world)
    if abs(mass_error) > tolerance:
        raise RuntimeError("phase-07 durable shard production mass invariant failed")

    cells_started = _stage("enumerating canonical production cells")
    all_cells = intensity.production_cells(world)
    population = len(all_cells)
    cells_finished = _stage(
        f"production cells enumerated ({population})", cells_started
    )
    if expected_population is not None and population != int(expected_population):
        raise RuntimeError(
            f"phase-07 population changed: expected {expected_population}, got {population}"
        )
    if stop > population:
        raise ValueError(f"shard stop {stop} exceeds population {population}")

    ordinal, remainder = divmod(int(start), int(chunk_cells))
    if remainder:
        raise ValueError("shard start is not aligned to chunk_cells")
    expected_stop = min(population, start + int(chunk_cells))
    if int(stop) != expected_stop:
        raise ValueError(f"shard stop must be {expected_stop} for start={start}")

    # materialized_cells is deliberately the *whole* population. A single shard
    # belongs to the canonical full product; it is not a verification-prefix world.
    config = canonical._config(
        hypothesis,
        world_seed=world_seed,
        workshops=workshops,
        steps=steps,
        nodes=nodes,
        population_cells=population,
        materialized_cells=population,
        chunk_cells=chunk_cells,
    )
    build_id = manifest.world_build_id(config)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"atolia_v3_canonical_{start:06d}_{stop:06d}.nc"
    path = out_dir / name
    if path.exists():
        path.unlink()

    materialize_started = _stage(
        f"materializing phases 01-05 for {stop - start} canonical cells"
    )
    record, _read04, _read05 = canonical._build_shard(
        world,
        all_cells,
        out_path=path,
        global_indices=list(range(start, stop)),
        ordinal=ordinal,
        config=config,
        release_version=str(release_version),
        production_mass_error_kg=mass_error,
    )
    materialize_finished = _stage(
        "canonical shard materialized", materialize_started
    )

    validate_started = _stage("validating immutable shard roundtrip")
    checked, _, _ = canonical._read_existing_shard(
        path,
        expected_world_build_id=build_id,
        ordinal=ordinal,
        start=start,
        stop=stop,
    )
    if checked["chunk_sha256"] != record["chunk_sha256"]:
        raise RuntimeError("phase-07 durable shard roundtrip hash mismatch")
    validate_finished = _stage("immutable shard validated", validate_started)

    public_record = {k: v for k, v in record.items() if not k.startswith("_")}
    completed = time.perf_counter()
    summary = {
        "phase": manifest.V3_PHASE07_PHASE,
        "product_scope": config["product_scope"],
        "world_build_id": build_id,
        "population_cells": population,
        "chunk_cells": int(chunk_cells),
        "shard": public_record,
        "path": str(path),
        "bytes": int(path.stat().st_size),
        "release_invariants_version": str(release_version),
        "production_mass_error_kg": mass_error,
        "timing_seconds": {
            "world_build": float(world_finished - world_started),
            "production_cells": float(cells_finished - cells_started),
            "materialize_phases_01_05": float(materialize_finished - materialize_started),
            "roundtrip_validation": float(validate_finished - validate_started),
            "total": float(completed - worker_started),
        },
    }
    (out_dir / f"{name}.json").write_text(
        json.dumps(summary, sort_keys=True, indent=2), encoding="utf-8"
    )
    _stage(
        f"complete cells {start}:{stop}; {path.stat().st_size} bytes",
        worker_started,
    )
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description="Build one durable Atolia v3 phase-07 shard")
    ap.add_argument("--hypothesis", type=Path, default=Path("hypotheses/atolia_atesis_1800_1000_v0.json"))
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--start", type=int, required=True)
    ap.add_argument("--stop", type=int, required=True)
    ap.add_argument("--chunk-cells", type=int, required=True)
    ap.add_argument("--expected-population", type=int, default=None)
    ap.add_argument("--world-seed", type=int, default=canonical.CANONICAL_WORLD_SEED)
    ap.add_argument("--workshops", type=int, default=canonical.CANONICAL_WORKSHOPS)
    ap.add_argument("--steps", type=int, default=canonical.CANONICAL_STEPS)
    ap.add_argument("--nodes", type=int, default=canonical.CANONICAL_NODES)
    args = ap.parse_args()

    hypothesis_path = args.hypothesis if args.hypothesis.is_absolute() else PROJECT_ROOT / args.hypothesis
    out_dir = args.out_dir if args.out_dir.is_absolute() else PROJECT_ROOT / args.out_dir
    hypothesis = json.loads(hypothesis_path.read_text(encoding="utf-8"))
    result = build_one_shard(
        hypothesis,
        out_dir=out_dir,
        start=args.start,
        stop=args.stop,
        chunk_cells=args.chunk_cells,
        expected_population=args.expected_population,
        world_seed=args.world_seed,
        workshops=args.workshops,
        steps=args.steps,
        nodes=args.nodes,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    host_emit = globals().get("emit")
    if callable(host_emit):
        host_emit(result)


if __name__ == "__main__":
    main()
