#!/usr/bin/env python3
from __future__ import annotations

"""Assemble Phase-08 compact shard fragments into the Dr. Corrosion sampler root.

The reducer never reopens a Phase-07 NetCDF.  It validates the 580 compact
fragments, sums the empirical weights, creates a deterministic alias table over
shards using recorded archaeological weight, and can bundle the already-gzipped
fragments into a stdlib-readable ZIP.  This archive is deliberately independent
of NumPy and netCDF4; later reduction may make it smaller, but this is already a
browser-compatible sampling boundary rather than developer hidden truth.
"""

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import zipfile
from typing import Any, Mapping, Sequence


SCHEMA = "atolia-v3-phase08-compact-sampler-root-v1"
FRAGMENT_SCHEMA = "atolia-v3-phase08-compact-sampler-fragment-v1"
EXPECTED_SHARDS = 580
EXPECTED_CAPSULE_ORDINALS = {507, 508, 515, 516, 564, 565, 568, 569, 577}


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _read_fragment(path: Path) -> dict[str, Any]:
    try:
        row = json.loads(gzip.decompress(Path(path).read_bytes()).decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"cannot read Phase-08 compact fragment {path}") from exc
    if row.get("schema") != FRAGMENT_SCHEMA:
        raise RuntimeError(f"unsupported Phase-08 compact fragment schema in {path}")
    supplied = str(row.get("fragment_sha256", ""))
    clean = dict(row)
    clean.pop("fragment_sha256", None)
    computed = hashlib.sha256(_stable_json(clean).encode("utf-8")).hexdigest()
    if supplied != computed:
        raise RuntimeError(f"Phase-08 compact fragment hash mismatch: {path}")
    return row


def alias_table(weights: Sequence[float]) -> tuple[list[float], list[int]]:
    """Vose alias table using deterministic index ordering."""
    if not weights:
        return [], []
    clean = [max(0.0, float(value)) for value in weights]
    total = math.fsum(clean)
    if total <= 0.0:
        raise ValueError("alias weights must contain positive mass")
    n = len(clean)
    scaled = [value * n / total for value in clean]
    small = [i for i, value in enumerate(scaled) if value < 1.0]
    large = [i for i, value in enumerate(scaled) if value >= 1.0]
    probability = [1.0] * n
    alias = list(range(n))
    while small and large:
        s = small.pop()
        l = large.pop()
        probability[s] = float(scaled[s])
        alias[s] = int(l)
        scaled[l] = scaled[l] - (1.0 - scaled[s])
        if scaled[l] < 1.0 - 1e-15:
            small.append(l)
        else:
            large.append(l)
    for index in small + large:
        probability[index] = 1.0
        alias[index] = index
    return probability, alias


def assemble(fragment_dir: Path, *, expected_shards: int = EXPECTED_SHARDS) -> tuple[dict[str, Any], list[tuple[Path, dict[str, Any]]]]:
    paths = sorted(Path(fragment_dir).rglob("compact-*.json.gz"))
    if len(paths) != int(expected_shards):
        raise RuntimeError(
            f"expected {expected_shards} Phase-08 compact fragments, found {len(paths)}"
        )
    rows = [(path, _read_fragment(path)) for path in paths]
    rows.sort(key=lambda item: int(item[1]["chunk_ordinal"]))
    ordinals = [int(row["chunk_ordinal"]) for _, row in rows]
    if ordinals != list(range(int(expected_shards))):
        raise RuntimeError("Phase-08 compact shard ordinals are not contiguous 0..N-1")

    world_ids = {str(row["world_build_id"]) for _, row in rows}
    if len(world_ids) != 1:
        raise RuntimeError("Phase-08 compact fragments belong to multiple worlds")
    world_build_id = next(iter(world_ids))

    if int(expected_shards) == EXPECTED_SHARDS:
        capsule_ordinals = {
            int(row["chunk_ordinal"])
            for _, row in rows
            if row["recovery"].get("replay_capsule_sha256")
        }
        if capsule_ordinals != EXPECTED_CAPSULE_ORDINALS:
            raise RuntimeError(
                f"Phase-08 capsule-backed shard set changed: {sorted(capsule_ordinals)}"
            )

    previous_stop = None
    shard_index: list[dict[str, Any]] = []
    for path, row in rows:
        start = int(row["global_cell_start"])
        stop = int(row["global_cell_stop"])
        if previous_stop is not None and start != previous_stop:
            raise RuntimeError(
                f"Phase-08 compact global-cell coverage gap/overlap before ordinal {row['chunk_ordinal']}"
            )
        previous_stop = stop
        shard_index.append({
            "ordinal": int(row["chunk_ordinal"]),
            "member": f"fragments/{int(row['chunk_ordinal']):03d}.json.gz",
            "fragment_sha256": str(row["fragment_sha256"]),
            "source_chunk_sha256": str(row["source"]["chunk_sha256"]),
            "global_cell_start": start,
            "global_cell_stop": stop,
            "cells": int(row["counts"]["cells"]),
            "lineages": int(row["counts"]["lineages"]),
            "profiles": int(row["counts"]["profiles"]),
            "representatives": int(row["counts"]["representatives"]),
            "external_tails": int(row["counts"]["external_tails"]),
            "loss_intensity": float(row["totals"]["loss_intensity"]),
            "represented_weight": float(row["totals"]["represented_weight"]),
            "recorded_weight": float(row["totals"]["recorded_weight"]),
            "recovery_action": str(row["recovery"]["action"]),
            "capsule_backed": bool(row["recovery"].get("replay_capsule_sha256")),
            "compressed_bytes": int(path.stat().st_size),
        })

    recorded_weights = [row["recorded_weight"] for row in shard_index]
    alias_probability, alias_index = alias_table(recorded_weights)
    root: dict[str, Any] = {
        "schema": SCHEMA,
        "world_build_id": world_build_id,
        "shard_count": len(shard_index),
        "global_cell_start": int(shard_index[0]["global_cell_start"]),
        "global_cell_stop": int(shard_index[-1]["global_cell_stop"]),
        "counts": {
            key: int(sum(int(row[key]) for row in shard_index))
            for key in ("cells", "lineages", "profiles", "representatives", "external_tails")
        },
        "totals": {
            key: float(math.fsum(float(row[key]) for row in shard_index))
            for key in ("loss_intensity", "represented_weight", "recorded_weight")
        },
        "shard_alias": {
            "weight": "recorded_weight",
            "probability": alias_probability,
            "alias": alias_index,
        },
        "shards": shard_index,
    }
    root["root_sha256"] = hashlib.sha256(_stable_json(root).encode("utf-8")).hexdigest()
    return root, rows


def write_archive(
    *,
    fragment_dir: Path,
    index_path: Path,
    archive_path: Path | None = None,
    expected_shards: int = EXPECTED_SHARDS,
) -> dict[str, Any]:
    root, rows = assemble(fragment_dir, expected_shards=expected_shards)
    index_path = Path(index_path)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_raw = (_stable_json(root) + "\n").encode("utf-8")
    index_path.write_bytes(gzip.compress(index_raw, compresslevel=9, mtime=0))

    if archive_path is not None:
        archive_path = Path(archive_path)
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("index.json.gz", index_path.read_bytes())
            for path, row in rows:
                member = f"fragments/{int(row['chunk_ordinal']):03d}.json.gz"
                archive.write(path, member)
        root["archive_bytes"] = int(archive_path.stat().st_size)
        root["archive_sha256"] = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    return root


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fragments", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--expected-shards", type=int, default=EXPECTED_SHARDS)
    args = parser.parse_args()
    root = write_archive(
        fragment_dir=args.fragments,
        index_path=args.index,
        archive_path=args.archive,
        expected_shards=args.expected_shards,
    )
    print(json.dumps({
        "schema": root["schema"],
        "world_build_id": root["world_build_id"],
        "shard_count": root["shard_count"],
        "counts": root["counts"],
        "totals": root["totals"],
        "root_sha256": root["root_sha256"],
        "archive_bytes": root.get("archive_bytes"),
        "archive_sha256": root.get("archive_sha256"),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
