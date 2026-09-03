#!/usr/bin/env python3
from __future__ import annotations

"""Preserve the exact Phase-01 generative spine before Phase-07 artifacts expire.

This is deliberately narrower than the empirical Phase-08 extractor.  It opens one
immutable Phase-07 carrier, validates its Phase-01 hash, and writes a deterministic
gzip JSON sidecar containing the complete Phase-01 spine.  No Phase-02..05 table is
read and no hydro repair is recomputed: the Phase-07 hydro mend only changes Phase-05.

The sidecar is a developer recovery boundary, not a player-visible runtime.  Raw
Phase-01 identifiers are retained so a later reducer can reproduce the old compact
runtime exactly before applying the final anti-spoiler projection.
"""

import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping

from netCDF4 import Dataset

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import v3_netcdf


SCHEMA = "atolia-v3-phase08-phase01-rescue-v1"
HASH_POLICY = "phase01-spine-sha256-exact; json-binary64-roundtrip; deterministic-gzip-mtime0"


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _read_chunk_record(path: Path) -> dict[str, Any]:
    with Dataset(path, "r") as ds:
        group = ds.groups.get("canonical_chunk")
        if group is None:
            raise RuntimeError("source shard lacks Phase-07 canonical chunk marker")
        return json.loads(str(group.record_json))


def _without_hash(payload: Mapping[str, Any]) -> dict[str, Any]:
    clean = copy.deepcopy(dict(payload))
    clean.pop("rescue_sha256", None)
    return clean


def rescue_hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_stable_json(_without_hash(payload)).encode("utf-8")).hexdigest()


def _validate_phase01_payload(payload: Mapping[str, Any]) -> None:
    if payload.get("schema") != SCHEMA:
        raise RuntimeError(f"unsupported Phase-01 rescue schema: {payload.get('schema')!r}")

    source = dict(payload["source"])
    spine = dict(payload["spine"])
    cells = list(spine["cells"])
    losses = list(spine["loss_strata"])

    recomputed_spine = v3_netcdf.spine_hash(cells, losses, dict(spine["flow_summary"]))
    if recomputed_spine != str(spine["spine_sha256"]):
        raise RuntimeError(
            "Phase-01 rescue spine hash mismatch: "
            f"stored={spine['spine_sha256']} recomputed={recomputed_spine}"
        )
    if recomputed_spine != str(source["phase01_spine_sha256"]):
        raise RuntimeError("Phase-01 rescue no longer matches the immutable source marker")

    start = int(payload["global_cell_start"])
    stop = int(payload["global_cell_stop"])
    ordinal = int(payload["chunk_ordinal"])
    if int(source["chunk_ordinal"]) != ordinal:
        raise RuntimeError("Phase-01 rescue/source ordinal mismatch")
    if int(source["global_cell_start"]) != start or int(source["global_cell_stop"]) != stop:
        raise RuntimeError("Phase-01 rescue/source cell interval mismatch")

    cell_ids = [int(row["cell_index"]) for row in cells]
    if cell_ids != list(range(start, stop)):
        raise RuntimeError("Phase-01 rescue cells are not the exact contiguous source interval")
    if any(not (start <= int(row["cell_index"]) < stop) for row in losses):
        raise RuntimeError("Phase-01 rescue contains a loss stratum outside its cell interval")

    supplied = str(payload.get("rescue_sha256", ""))
    expected = rescue_hash(payload)
    if not supplied or supplied != expected:
        raise RuntimeError("Phase-01 rescue payload hash mismatch")


def build_rescue_payload(*, shard_path: Path, ordinal: int) -> dict[str, Any]:
    shard_path = Path(shard_path)
    record = _read_chunk_record(shard_path)
    if int(record["chunk_ordinal"]) != int(ordinal):
        raise RuntimeError(
            f"source ordinal mismatch: marker={record['chunk_ordinal']} requested={ordinal}"
        )

    # read_spine_master validates the stored Phase-01 SHA-256 before returning.
    spine = v3_netcdf.read_spine_master(shard_path)
    if str(spine["spine_sha256"]) != str(record["phase01_spine_sha256"]):
        raise RuntimeError("Phase-07 marker and Phase-01 spine SHA-256 disagree")

    # Keep every value participating in v3_netcdf.spine_hash plus the metadata
    # required to identify/rebuild the same generative Phase-01 product.
    spine_payload = {
        key: copy.deepcopy(spine[key])
        for key in (
            "schema",
            "phase",
            "world_seed",
            "workshop_count",
            "intensity_steps",
            "hypothesis_sha256",
            "release_invariants_version",
            "production_mass_error_kg",
            "target_geography_nodes",
            "intensity_model_version",
            "spine_sha256",
            "flow_summary",
            "cells",
            "loss_strata",
        )
    }

    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "hash_policy": HASH_POLICY,
        "world_build_id": str(record["world_build_id"]),
        "chunk_ordinal": int(ordinal),
        "global_cell_start": int(record["global_cell_start"]),
        "global_cell_stop": int(record["global_cell_stop"]),
        "source": {
            "shard_name": str(record["shard_name"]),
            "chunk_ordinal": int(record["chunk_ordinal"]),
            "global_cell_start": int(record["global_cell_start"]),
            "global_cell_stop": int(record["global_cell_stop"]),
            "chunk_sha256": str(record["chunk_sha256"]),
            "phase01_spine_sha256": str(record["phase01_spine_sha256"]),
        },
        "spine": spine_payload,
    }
    payload["rescue_sha256"] = rescue_hash(payload)
    _validate_phase01_payload(payload)
    return payload


def write_rescue(*, shard_path: Path, ordinal: int, out_path: Path) -> dict[str, Any]:
    payload = build_rescue_payload(shard_path=shard_path, ordinal=ordinal)
    raw = (_stable_json(payload) + "\n").encode("utf-8")
    compressed = gzip.compress(raw, compresslevel=9, mtime=0)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(compressed)

    checked = json.loads(gzip.decompress(out_path.read_bytes()))
    _validate_phase01_payload(checked)
    if checked != payload:
        raise RuntimeError("Phase-01 rescue JSON/gzip roundtrip changed the payload")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shard", type=Path, required=True)
    parser.add_argument("--ordinal", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    payload = write_rescue(
        shard_path=args.shard,
        ordinal=args.ordinal,
        out_path=args.out,
    )
    print(
        json.dumps(
            {
                "schema": payload["schema"],
                "world_build_id": payload["world_build_id"],
                "chunk_ordinal": payload["chunk_ordinal"],
                "global_cell_start": payload["global_cell_start"],
                "global_cell_stop": payload["global_cell_stop"],
                "cells": len(payload["spine"]["cells"]),
                "loss_strata": len(payload["spine"]["loss_strata"]),
                "phase01_spine_sha256": payload["spine"]["spine_sha256"],
                "rescue_sha256": payload["rescue_sha256"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
