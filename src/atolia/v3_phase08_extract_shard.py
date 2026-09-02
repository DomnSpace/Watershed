#!/usr/bin/env python3
from __future__ import annotations

"""Single-pass Phase-08 projection for one immutable Phase-07 NetCDF shard.

The first Phase-08 prototype deliberately reused ``phase07._read_existing_shard``
for source validation, but that helper reads Phase-01..05 itself; the prototype
then re-read Phase-01..03 to build empirical profiles. That is harmless for unit
fixtures and needlessly expensive for 0.5--1.9 GB production shards.

This executable keeps the same Phase-08 fragment schema and projection logic but
loads every Phase-01..05 table exactly once, validates all frozen hashes and row
counts against the Phase-07 chunk marker, applies the logical hydro mend in
memory, then discards the physical source after the caller has written the compact
fragment.
"""

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping

from netCDF4 import Dataset

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import v3_biography_netcdf
import v3_metallurgy_netcdf
import v3_netcdf
import v3_phase05_netcdf
import v3_phase07_manifest as phase07_manifest
import v3_phase08_runtime_fragment as phase08
import v3_workshop_netcdf


def _read_marker(path: Path) -> dict[str, Any]:
    with Dataset(path, "r") as ds:
        group = ds.groups.get("canonical_chunk")
        if group is None:
            raise RuntimeError("source shard lacks Phase-07 canonical chunk marker")
        return json.loads(str(group.record_json))


def _expect_equal(label: str, found: object, expected: object) -> None:
    if found != expected:
        raise RuntimeError(
            f"Phase-08 source validation mismatch for {label}: "
            f"found={found!r} expected={expected!r}"
        )


def read_validated_source_shard(
    path: Path,
    *,
    certificate: Mapping[str, Any],
    ordinal: int,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    """Load each Phase-01..05 table once and validate the frozen Phase-07 record."""
    path = Path(path)
    record = _read_marker(path)
    _expect_equal("chunk_ordinal", int(record["chunk_ordinal"]), int(ordinal))
    _expect_equal(
        "world_build_id",
        str(record["world_build_id"]),
        str(certificate["world_build_id"]),
    )

    spine = v3_netcdf.read_spine_master(path)
    biography = v3_biography_netcdf.read_biography(path)
    metallurgy = v3_metallurgy_netcdf.read_metallurgy(path)
    workshop = v3_workshop_netcdf.read_workshop_layer(path)
    phase05 = v3_phase05_netcdf.read_phase05(path)

    _expect_equal(
        "phase01_spine_sha256",
        str(record["phase01_spine_sha256"]),
        str(spine["spine_sha256"]),
    )
    _expect_equal(
        "phase02_biography_sha256",
        str(record["phase02_biography_sha256"]),
        str(biography["biography_sha256"]),
    )
    _expect_equal(
        "phase03_metallurgy_sha256",
        str(record["phase03_metallurgy_sha256"]),
        str(metallurgy["metallurgy_sha256"]),
    )
    _expect_equal(
        "phase04_workshop_sha256",
        str(record["phase04_workshop_sha256"]),
        str(workshop["workshop_sha256"]),
    )
    _expect_equal(
        "phase05_sha256",
        str(record["phase05_sha256"]),
        str(phase05["phase05_sha256"]),
    )
    _expect_equal(
        "chunk_sha256",
        str(record["chunk_sha256"]),
        phase07_manifest.chunk_hash(record),
    )

    count_checks = {
        "loss_strata": len(spine["loss_strata"]),
        "particles": len(biography["particles"]),
        "batches": len(biography["batches"]),
        "operations": len(workshop["operations"]),
        "external_exchange_tails": len(phase05["external_exchange"]),
        "deposition_assignments": len(phase05["deposition_assignments"]),
        "archaeology_rows": len(phase05["archaeology"]),
    }
    for field, observed in count_checks.items():
        _expect_equal(field, int(record[field]), int(observed))

    return record, spine, biography, metallurgy, workshop, phase05


def extract_runtime_fragment(
    *,
    shard_path: Path,
    certificate_path: Path,
    ordinal: int,
    out_path: Path,
    capsule_path: Path | None = None,
) -> dict[str, Any]:
    shard_path = Path(shard_path)
    certificate_path = Path(certificate_path)
    out_path = Path(out_path)

    certificate = phase08._read_json(certificate_path)
    phase08.validate_certificate(certificate)
    entry = phase08.certificate_entry(certificate, ordinal)

    record, spine, biography, metallurgy, workshop, source05 = read_validated_source_shard(
        shard_path,
        certificate=certificate,
        ordinal=ordinal,
    )
    _expect_equal(
        "repair source_chunk_sha256",
        str(record["chunk_sha256"]),
        str(entry["source_chunk_sha256"]),
    )
    _expect_equal(
        "repair source_phase05_sha256",
        str(record["phase05_sha256"]),
        str(entry["source_phase05_sha256"]),
    )

    capsule = None
    capsule_sha = ""
    if capsule_path is not None:
        capsule_path = Path(capsule_path)
        capsule = phase08._read_json(capsule_path)
        capsule_sha = phase08._file_sha256(capsule_path)
        _expect_equal(
            "replay_capsule_sha256",
            capsule_sha,
            str(entry.get("replay_capsule_sha256", "")),
        )
    elif str(entry.get("replay_capsule_sha256", "")):
        raise RuntimeError("Phase-08 affected shard requires --capsule")

    canonical05 = phase08.canonicalize_phase05(
        source05,
        certificate=certificate,
        entry=entry,
        capsule=capsule,
    )
    profiles = phase08.build_empirical_profiles(
        world_build_id=str(certificate["world_build_id"]),
        spine=spine,
        biography=biography,
        metallurgy=metallurgy,
        workshop=workshop,
        phase05=canonical05,
    )

    payload: dict[str, Any] = {
        "schema": phase08.SCHEMA,
        "hash_policy": phase08.HASH_POLICY,
        "projection_policy": phase08.PROJECTION_POLICY,
        "world_build_id": str(certificate["world_build_id"]),
        "chunk_ordinal": int(ordinal),
        "global_cell_start": int(record["global_cell_start"]),
        "global_cell_stop": int(record["global_cell_stop"]),
        "source": {
            "shard_name": shard_path.name,
            "chunk_sha256": str(record["chunk_sha256"]),
            "phase01_spine_sha256": str(record["phase01_spine_sha256"]),
            "phase02_biography_sha256": str(record["phase02_biography_sha256"]),
            "phase03_metallurgy_sha256": str(record["phase03_metallurgy_sha256"]),
            "phase04_workshop_sha256": str(record["phase04_workshop_sha256"]),
            "phase05_sha256": str(record["phase05_sha256"]),
        },
        "recovery": {
            "certificate_sha256": str(certificate["certificate_sha256"]),
            "action": str(entry["action"]),
            "canonical_hydro_realization_token": phase08.anonymous_token(
                str(certificate["world_build_id"]),
                "hydro",
                certificate["canonical_hydro_realization_id"],
            ),
            "external_exchange_count_delta": int(
                entry.get("external_exchange_count_delta", 0)
            ),
            "replay_capsule_sha256": capsule_sha,
        },
        "profile_count": len(profiles),
        "totals": {
            "represented_weight": float(
                math.fsum(row["lineage"]["represented_weight"] for row in profiles)
            ),
            "recorded_weight": float(
                math.fsum(row["archaeology"]["recorded_weight"] for row in profiles)
            ),
            "external_tail_count": sum(
                row["external_tail"] is not None for row in profiles
            ),
        },
        "profiles": profiles,
    }
    payload["fragment_sha256"] = phase08.fragment_hash(payload)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    checked = phase08._read_json(out_path)
    if str(checked["fragment_sha256"]) != phase08.fragment_hash(checked):
        raise RuntimeError("Phase-08 runtime fragment roundtrip hash mismatch")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shard", type=Path, required=True)
    parser.add_argument("--certificate", type=Path, required=True)
    parser.add_argument("--ordinal", type=int, required=True)
    parser.add_argument("--capsule", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = extract_runtime_fragment(
        shard_path=args.shard,
        certificate_path=args.certificate,
        ordinal=args.ordinal,
        capsule_path=args.capsule,
        out_path=args.out,
    )
    print(
        json.dumps(
            {
                "schema": result["schema"],
                "world_build_id": result["world_build_id"],
                "chunk_ordinal": result["chunk_ordinal"],
                "profile_count": result["profile_count"],
                "fragment_sha256": result["fragment_sha256"],
                "totals": result["totals"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
