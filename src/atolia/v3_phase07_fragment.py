#!/usr/bin/env python3
from __future__ import annotations

"""Lossless compact manifest fragments for Atolia v3 phase-07 shards.

A fragment is not a replacement for the immutable NetCDF shard.  It is a small,
read-only projection containing exactly the information the canonical root
manifest assembler needs after the shard itself has already passed the normal
phase-07 roundtrip validation.

The projection deliberately preserves Python/NetCDF float values through normal
JSON round-tripping instead of applying the manifest's 10-significant-digit hash
projection before global aggregation.  This keeps fragment assembly numerically
identical to direct shard assembly while allowing the hundreds of large shard
artifacts to stay distributed.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping

import numpy as np

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
PROJECT_ROOT = HERE.parent.parent

import v3_phase07_canonical as canonical
import v3_phase07_manifest as manifest


FRAGMENT_SCHEMA = "atolia-v3-phase07-manifest-fragment-v1"
FRAGMENT_HASH_POLICY = "lossless-json-float-roundtrip-v1"
RECOVERY_OVERLAY_SCHEMA = "atolia-v3-phase07-hydro-repair-overlay-v1"
RECOVERY_OVERLAY_POLICY = (
    "immutable-source-record-preserved; canonical-hydro-identity-and-context-projected; "
    "external-exchange-delta-capsule-backed"
)


def _plain_exact(value: Any) -> Any:
    """Convert numpy/container values to exact JSON-compatible Python values."""
    if isinstance(value, np.generic):
        return _plain_exact(value.item())
    if isinstance(value, float):
        x = float(value)
        if not math.isfinite(x):
            raise ValueError("phase-07 fragment cannot contain non-finite float")
        return x
    if isinstance(value, Mapping):
        return {str(k): _plain_exact(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_exact(v) for v in value]
    return value


def _stable_exact_json(value: Any) -> str:
    return json.dumps(
        _plain_exact(value),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _fragment_hash(payload_without_hash: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        _stable_exact_json(payload_without_hash).encode("utf-8")
    ).hexdigest()


def build_fragment(
    record: Mapping[str, Any],
    read04: Mapping[str, Any],
    read05: Mapping[str, Any],
    *,
    source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a compact fragment from one already validated canonical shard."""
    for key in ("_flow_summary", "_static_workshop_signature", "_hydro_signature"):
        if key not in record:
            raise ValueError(f"validated phase-07 record is missing {key}")

    public_record = {k: v for k, v in record.items() if not str(k).startswith("_")}
    if manifest.chunk_hash(public_record) != str(public_record["chunk_sha256"]):
        raise RuntimeError("phase-07 fragment source record has invalid chunk hash")

    payload: dict[str, Any] = {
        "schema": FRAGMENT_SCHEMA,
        "hash_policy": FRAGMENT_HASH_POLICY,
        "world_build_id": str(public_record["world_build_id"]),
        "chunk_ordinal": int(public_record["chunk_ordinal"]),
        "global_cell_start": int(public_record["global_cell_start"]),
        "global_cell_stop": int(public_record["global_cell_stop"]),
        "shard_name": str(public_record["shard_name"]),
        "record": public_record,
        "flow_summary": record["_flow_summary"],
        "static_workshop_signature": str(record["_static_workshop_signature"]),
        "hydro_realization_signature": str(record["_hydro_signature"]),
        "deposition_pools": list(read05["deposition_pools"]),
        "tool_use": list(read04["tool_use"]),
        "source": dict(source or {}),
    }
    exact = _plain_exact(payload)
    exact["fragment_sha256"] = _fragment_hash(exact)
    return exact


def write_fragment(
    path: Path,
    record: Mapping[str, Any],
    read04: Mapping[str, Any],
    read05: Mapping[str, Any],
    *,
    source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    fragment = build_fragment(record, read04, read05, source=source)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(fragment, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    checked = read_fragment(path)
    if checked["fragment_sha256"] != fragment["fragment_sha256"]:
        raise RuntimeError("phase-07 fragment roundtrip hash mismatch")
    return checked


def read_fragment(path: Path) -> dict[str, Any]:
    path = Path(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != FRAGMENT_SCHEMA:
        raise RuntimeError(f"unsupported phase-07 fragment schema in {path}")
    if payload.get("hash_policy") != FRAGMENT_HASH_POLICY:
        raise RuntimeError(f"unsupported phase-07 fragment hash policy in {path}")
    supplied = str(payload.get("fragment_sha256", ""))
    body = dict(payload)
    body.pop("fragment_sha256", None)
    expected = _fragment_hash(body)
    if supplied != expected:
        raise RuntimeError(f"phase-07 fragment hash mismatch in {path}")

    record = payload["record"]
    if manifest.chunk_hash(record) != str(record["chunk_sha256"]):
        raise RuntimeError(f"phase-07 fragment chunk hash mismatch in {path}")
    for key in ("world_build_id", "chunk_ordinal", "global_cell_start", "global_cell_stop"):
        if str(payload[key]) != str(record[key]):
            raise RuntimeError(f"phase-07 fragment envelope/record mismatch for {key}")

    recovery = payload.get("recovery")
    if recovery is not None:
        if not isinstance(recovery, Mapping):
            raise RuntimeError(f"phase-07 fragment recovery overlay is not an object in {path}")
        if recovery.get("schema") != RECOVERY_OVERLAY_SCHEMA:
            raise RuntimeError(f"unsupported phase-07 recovery overlay schema in {path}")
        if recovery.get("policy") != RECOVERY_OVERLAY_POLICY:
            raise RuntimeError(f"unsupported phase-07 recovery overlay policy in {path}")
        if str(recovery.get("source_chunk_sha256")) != str(record["chunk_sha256"]):
            raise RuntimeError(f"phase-07 recovery source chunk hash mismatch in {path}")
        if str(recovery.get("source_phase05_sha256")) != str(record["phase05_sha256"]):
            raise RuntimeError(f"phase-07 recovery source phase-05 hash mismatch in {path}")
        if int(recovery.get("source_external_exchange_tails", -1)) != int(
            record["external_exchange_tails"]
        ):
            raise RuntimeError(f"phase-07 recovery source external count mismatch in {path}")
        expected_external = int(record["external_exchange_tails"]) + int(
            recovery.get("external_exchange_count_delta", 0)
        )
        if int(recovery.get("canonical_external_exchange_tails", -1)) != expected_external:
            raise RuntimeError(f"phase-07 recovery canonical external count mismatch in {path}")
        if expected_external < 0:
            raise RuntimeError(f"phase-07 recovery canonical external count is negative in {path}")
        if str(payload["hydro_realization_signature"]) != str(
            recovery.get("canonical_hydro_realization_signature")
        ):
            raise RuntimeError(f"phase-07 recovery hydro signature mismatch in {path}")
        canonical_rid = str(recovery.get("canonical_hydro_realization_id"))
        pool_ids = {str(row["hydro_realization_id"]) for row in payload["deposition_pools"]}
        if pool_ids != {canonical_rid}:
            raise RuntimeError(f"phase-07 recovery deposition hydro identity mismatch in {path}")
        if int(recovery.get("hydro_identity_replacement_count", -1)) != len(
            payload["deposition_pools"]
        ):
            raise RuntimeError(f"phase-07 recovery pool replacement count mismatch in {path}")
    return payload


def extract_fragment_from_shard(
    hypothesis: Mapping[str, Any],
    *,
    shard_path: Path,
    out_path: Path,
    start: int,
    stop: int,
    population_cells: int,
    chunk_cells: int,
    world_seed: int = canonical.CANONICAL_WORLD_SEED,
    workshops: int = canonical.CANONICAL_WORKSHOPS,
    steps: int = canonical.CANONICAL_STEPS,
    nodes: int = canonical.CANONICAL_NODES,
    source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Read one existing shard and emit a fragment without mutating the shard."""
    population = int(population_cells)
    chunk = int(chunk_cells)
    start = int(start)
    stop = int(stop)
    if population <= 0 or chunk <= 0:
        raise ValueError("population_cells and chunk_cells must be positive")
    ordinal, remainder = divmod(start, chunk)
    if remainder:
        raise ValueError("fragment shard start is not aligned to chunk_cells")
    expected_stop = min(population, start + chunk)
    if stop != expected_stop:
        raise ValueError(f"fragment shard stop must be {expected_stop} for start={start}")

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
    record, read04, read05 = canonical._read_existing_shard(
        Path(shard_path),
        expected_world_build_id=build_id,
        ordinal=ordinal,
        start=start,
        stop=stop,
    )
    return write_fragment(
        Path(out_path),
        record,
        read04,
        read05,
        source=source,
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Extract compact manifest data from one immutable phase-07 shard")
    ap.add_argument("--hypothesis", type=Path, default=Path("hypotheses/atolia_atesis_1800_1000_v0.json"))
    ap.add_argument("--shard", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--start", type=int, required=True)
    ap.add_argument("--stop", type=int, required=True)
    ap.add_argument("--population-cells", type=int, required=True)
    ap.add_argument("--chunk-cells", type=int, required=True)
    ap.add_argument("--world-seed", type=int, default=canonical.CANONICAL_WORLD_SEED)
    ap.add_argument("--workshops", type=int, default=canonical.CANONICAL_WORKSHOPS)
    ap.add_argument("--steps", type=int, default=canonical.CANONICAL_STEPS)
    ap.add_argument("--nodes", type=int, default=canonical.CANONICAL_NODES)
    ap.add_argument("--source-run-id", default="")
    ap.add_argument("--source-artifact", default="")
    args = ap.parse_args()

    hypothesis_path = args.hypothesis if args.hypothesis.is_absolute() else PROJECT_ROOT / args.hypothesis
    hypothesis = json.loads(hypothesis_path.read_text(encoding="utf-8"))
    source = {
        key: value
        for key, value in {
            "mode": "read-only-artifact-recovery",
            "run_id": str(args.source_run_id),
            "artifact": str(args.source_artifact),
        }.items()
        if value
    }
    result = extract_fragment_from_shard(
        hypothesis,
        shard_path=args.shard,
        out_path=args.out,
        start=args.start,
        stop=args.stop,
        population_cells=args.population_cells,
        chunk_cells=args.chunk_cells,
        world_seed=args.world_seed,
        workshops=args.workshops,
        steps=args.steps,
        nodes=args.nodes,
        source=source,
    )
    print(json.dumps({
        "fragment": str(args.out),
        "fragment_sha256": result["fragment_sha256"],
        "world_build_id": result["world_build_id"],
        "chunk_ordinal": result["chunk_ordinal"],
        "global_cell_start": result["global_cell_start"],
        "global_cell_stop": result["global_cell_stop"],
        "deposition_pools": len(result["deposition_pools"]),
        "tool_use": len(result["tool_use"]),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
