from __future__ import annotations

"""Assemble the sealed-game R17 Atolia v3 generative NetCDF.

Inputs are the already validated compact Phase-08 fragments plus the successful
Phase-07 mend certificate/cutoff plan. The output is one small NetCDF. It keeps
no expanded Phase-02..05 lineages and no JSON shard fan-out.
"""

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from netCDF4 import Dataset

import build_v3_master
import v3_phase07_canonical as canonical
import v3_phase07_manifest as phase07_manifest
import v3_phase08_compact_fragment as compact
import v3_phase08_runtime_fragment as phase08
import v3_runtime_v3 as runtime_v3


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_fragment(path: Path) -> dict[str, Any]:
    value = json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
    if value.get("schema") != compact.SCHEMA:
        raise RuntimeError(f"unsupported compact fragment schema in {path}")
    if str(value.get("fragment_sha256", "")) != compact.logical_hash(value):
        raise RuntimeError(f"compact fragment hash mismatch: {path}")
    return value


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _hash_to_u1(text: str) -> np.ndarray:
    return np.frombuffer(bytes.fromhex(text), dtype=np.uint8)


def _bytes_digest(value: bytes) -> np.ndarray:
    return np.frombuffer(value, dtype=np.uint8)


def _profile_rows_for_cell(fragment: Mapping[str, Any], local_cell: int) -> list[dict[str, Any]]:
    columns = {name: i for i, name in enumerate(fragment["columns"]["profile"])}
    nodes = list(fragment["dictionary"]["node"])
    rows: list[dict[str, Any]] = []
    for row in fragment["profiles"]:
        if int(row[columns["cell"]]) != int(local_cell):
            continue
        item: dict[str, Any] = {
            "node_token": str(nodes[int(row[columns["loss_node"]])]),
            "lineage_count": int(row[columns["lineage_count"]]),
            "loss_intensity": float(row[columns["loss_intensity"]]),
            "recorded_weight": float(row[columns["recorded_weight"]]),
            "step_min": int(row[columns["step_min"]]),
            "step_max": int(row[columns["step_max"]]),
        }
        for name in runtime_v3.PROFILE_PHASE01_FIELDS:
            item[f"{name}_mean"] = float(row[columns[f"{name}_mean"]])
            item[f"{name}_variance"] = float(row[columns[f"{name}_variance"]])
        rows.append(item)
    rows.sort(key=lambda item: item["node_token"])
    return rows


def _cell_source_mix(fragment: Mapping[str, Any], local_cell: int) -> dict[str, float]:
    columns = {name: i for i, name in enumerate(fragment["columns"]["cell_source"])}
    sources = list(fragment["dictionary"]["source"])
    out: dict[str, float] = {}
    for row in fragment["cell_sources"]:
        if int(row[columns["cell"]]) != int(local_cell):
            continue
        token = str(sources[int(row[columns["source"]])])
        out[token] = float(row[columns["weight"]])
    return out


def _cell_identity_digest(fragment: Mapping[str, Any], local_cell: int) -> bytes:
    columns = {name: i for i, name in enumerate(fragment["columns"]["cell"])}
    row = fragment["cells"][local_cell]
    dictionaries = fragment["dictionary"]
    return runtime_v3.cell_identity_hash(
        world_build_id=str(fragment["world_build_id"]),
        global_cell_index=int(row[columns["global_cell_index"]]),
        bundle_id=str(dictionaries["bundle"][int(row[columns["bundle"]])]),
        bundle_family=str(dictionaries["family"][int(row[columns["family"]])]),
        object_class=str(dictionaries["object_class"][int(row[columns["object_class"]])]),
        date_bc=int(row[columns["date_bc"]]),
        origin=str(dictionaries["node"][int(row[columns["origin_node"]])]),
        destination=str(dictionaries["node"][int(row[columns["destination_node"]])]),
        production_intensity=float(row[columns["production_intensity"]]),
        circulation_seed_intensity=float(row[columns["circulation_seed_intensity"]]),
        recycle_mean=float(row[columns["recycle_mean"]]),
        source_mix=_cell_source_mix(fragment, local_cell),
        already_tokenized=True,
    )


def _fixed_token_matrix(tokens: list[str]) -> np.ndarray:
    width = max([1, *(len(token.encode("ascii")) for token in tokens)])
    matrix = np.zeros((len(tokens), width), dtype=np.uint8)
    for i, token in enumerate(tokens):
        raw = token.encode("ascii")
        matrix[i, : len(raw)] = np.frombuffer(raw, dtype=np.uint8)
    return matrix


def _runtime_fingerprint(
    *,
    hypothesis_raw: bytes,
    world_build_id: str,
    cell_recorded: np.ndarray,
    cell_loss: np.ndarray,
    cell_lineages: np.ndarray,
    cell_profiles: np.ndarray,
    cell_identity_hashes: np.ndarray,
    cell_profile_hashes: np.ndarray,
    shard_phase01_hashes: np.ndarray,
    override_tokens: list[str],
    override_values: np.ndarray,
    canonical_hydro_id: str,
) -> str:
    h = hashlib.sha256()
    h.update(runtime_v3.RUNTIME_SCHEMA.encode())
    h.update(world_build_id.encode())
    h.update(hypothesis_raw)
    for array, dtype in (
        (cell_recorded, ">f8"),
        (cell_loss, ">f8"),
        (cell_lineages, ">i8"),
        (cell_profiles, ">i8"),
    ):
        h.update(np.asarray(array, dtype=dtype).tobytes(order="C"))
    h.update(np.asarray(cell_identity_hashes, dtype=np.uint8).tobytes(order="C"))
    h.update(np.asarray(cell_profile_hashes, dtype=np.uint8).tobytes(order="C"))
    h.update(np.asarray(shard_phase01_hashes, dtype=np.uint8).tobytes(order="C"))
    for token, value in zip(override_tokens, override_values):
        h.update(token.encode("ascii"))
        h.update(np.asarray([value], dtype=">f8").tobytes())
    h.update(canonical_hydro_id.encode())
    return h.hexdigest()


def build_runtime(
    *,
    fragments_dir: Path,
    cutoff_plan_path: Path,
    repair_certificate_path: Path,
    hypothesis_path: Path,
    out_path: Path,
    expected_shards: int = 580,
    population_cells: int = 37100,
) -> dict[str, Any]:
    paths = sorted(Path(fragments_dir).rglob("compact-*.json.gz"))
    if len(paths) != expected_shards:
        raise RuntimeError(f"expected {expected_shards} compact fragments, found {len(paths)}")
    plan = _read_json(Path(cutoff_plan_path))
    certificate = _read_json(Path(repair_certificate_path))
    hypothesis = json.loads(Path(hypothesis_path).read_text(encoding="utf-8"))
    hypothesis_raw = (runtime_v3.stable_json(hypothesis) + "\n").encode("utf-8")

    first = _read_fragment(paths[0])
    world_build_id = str(first["world_build_id"])
    if str(plan["world_build_id"]) != world_build_id or str(certificate["world_build_id"]) != world_build_id:
        raise RuntimeError("R17 inputs disagree on world_build_id")
    phase08.validate_certificate(certificate)
    supplied_cert_hash = str(certificate["certificate_sha256"])

    config = canonical._config(
        hypothesis,
        world_seed=canonical.CANONICAL_WORLD_SEED,
        workshops=canonical.CANONICAL_WORKSHOPS,
        steps=canonical.CANONICAL_STEPS,
        nodes=canonical.CANONICAL_NODES,
        population_cells=population_cells,
        materialized_cells=population_cells,
        chunk_cells=64,
    )
    rebuilt_world_id = phase07_manifest.world_build_id(config)
    if rebuilt_world_id != world_build_id:
        raise RuntimeError(f"canonical hypothesis/config rebuilds {rebuilt_world_id}, expected {world_build_id}")
    hypothesis_sha = build_v3_master.canonical_hypothesis_sha256(hypothesis)

    cell_recorded = np.zeros(population_cells, dtype=np.float64)
    cell_loss = np.zeros(population_cells, dtype=np.float64)
    cell_lineages = np.zeros(population_cells, dtype=np.int64)
    cell_profiles = np.zeros(population_cells, dtype=np.int32)
    cell_identity_hashes = np.zeros((population_cells, 32), dtype=np.uint8)
    cell_profile_hashes = np.zeros((population_cells, 32), dtype=np.uint8)
    seen = np.zeros(population_cells, dtype=np.uint8)

    shard_phase01_hashes = np.zeros((expected_shards, 32), dtype=np.uint8)
    shard_start = np.zeros(expected_shards, dtype=np.int32)
    shard_stop = np.zeros(expected_shards, dtype=np.int32)

    capsule_count = 0
    total_recorded_profiles: list[float] = []
    total_loss_profiles: list[float] = []
    total_lineages = 0

    # Parse ordinals from filenames so only one decompressed fragment exists in
    # memory at a time. The old reducer's all-at-once fan-in is deliberately not
    # repeated here.
    by_ordinal: dict[int, Path] = {}
    for path in paths:
        name = path.name
        try:
            ordinal = int(name.removeprefix("compact-").removesuffix(".json.gz"))
        except ValueError as exc:
            raise RuntimeError(f"cannot parse compact fragment ordinal from {name}") from exc
        if ordinal in by_ordinal:
            raise RuntimeError(f"duplicate compact fragment ordinal {ordinal}")
        by_ordinal[ordinal] = path
    if sorted(by_ordinal) != list(range(expected_shards)):
        raise RuntimeError("compact fragment ordinals are not contiguous")

    for ordinal in range(expected_shards):
        path = by_ordinal[ordinal]
        fragment = _read_fragment(path)
        if str(fragment["world_build_id"]) != world_build_id:
            raise RuntimeError(f"world mismatch in fragment {ordinal}")
        if int(fragment["chunk_ordinal"]) != ordinal:
            raise RuntimeError(f"filename/payload ordinal mismatch in fragment {ordinal}")
        if str(fragment["recovery"]["certificate_sha256"]) != supplied_cert_hash:
            raise RuntimeError(f"repair certificate mismatch in fragment {ordinal}")
        capsule_count += int(bool(fragment["recovery"].get("replay_capsule_sha256")))
        start = int(fragment["global_cell_start"])
        stop = int(fragment["global_cell_stop"])
        shard_start[ordinal] = start
        shard_stop[ordinal] = stop
        if start != ordinal * 64 or stop != min(population_cells, start + 64):
            raise RuntimeError(f"unexpected compact cell interval at ordinal {ordinal}: {start}:{stop}")
        shard_phase01_hashes[ordinal, :] = _hash_to_u1(str(fragment["source"]["phase01_spine_sha256"]))

        cell_cols = {name: i for i, name in enumerate(fragment["columns"]["cell"])}
        if len(fragment["cells"]) != stop - start:
            raise RuntimeError(f"cell count mismatch in fragment {ordinal}")
        for local, cell_row in enumerate(fragment["cells"]):
            global_index = int(cell_row[cell_cols["global_cell_index"]])
            if global_index != start + local or seen[global_index]:
                raise RuntimeError(f"duplicate/out-of-order global cell {global_index}")
            profiles = _profile_rows_for_cell(fragment, local)
            if not profiles:
                raise RuntimeError(f"cell {global_index} has no compact profiles")
            recorded = math.fsum(float(row["recorded_weight"]) for row in profiles)
            loss = math.fsum(float(row["loss_intensity"]) for row in profiles)
            lineages = sum(int(row["lineage_count"]) for row in profiles)
            cell_recorded[global_index] = recorded
            cell_loss[global_index] = loss
            cell_lineages[global_index] = lineages
            cell_profiles[global_index] = len(profiles)
            cell_identity_hashes[global_index, :] = _bytes_digest(_cell_identity_digest(fragment, local))
            cell_profile_hashes[global_index, :] = _bytes_digest(runtime_v3.profile_checkpoint_hash(profiles))
            seen[global_index] = 1
            total_recorded_profiles.append(recorded)
            total_loss_profiles.append(loss)
            total_lineages += lineages
        del fragment

    if not np.all(seen == 1):
        missing = np.nonzero(seen == 0)[0][:20].tolist()
        raise RuntimeError(f"R17 cell coverage incomplete: {missing}")
    if capsule_count != 9:
        raise RuntimeError(f"expected 9 capsule-backed repaired fragments, found {capsule_count}")

    canonical_hydro_id = str(plan["observed_variants"]["canonical_hydro_realization_id"])
    minority_hydro_id = str(plan["observed_variants"]["minority_hydro_realization_id"])
    if canonical_hydro_id != str(certificate["canonical_hydro_realization_id"]):
        raise RuntimeError("cutoff plan and repair certificate canonical hydro IDs differ")
    affected = list(plan["observed_boundary"]["affected_nodes"])
    override_tokens = [
        phase08.anonymous_token(world_build_id, "node", row["node_id"])
        for row in affected
    ]
    override_values = np.asarray([float(row["canonical"]) for row in affected], dtype=np.float64)
    token_matrix = _fixed_token_matrix(override_tokens)

    fingerprint = _runtime_fingerprint(
        hypothesis_raw=hypothesis_raw,
        world_build_id=world_build_id,
        cell_recorded=cell_recorded,
        cell_loss=cell_loss,
        cell_lineages=cell_lineages,
        cell_profiles=cell_profiles,
        cell_identity_hashes=cell_identity_hashes,
        cell_profile_hashes=cell_profile_hashes,
        shard_phase01_hashes=shard_phase01_hashes,
        override_tokens=override_tokens,
        override_values=override_values,
        canonical_hydro_id=canonical_hydro_id,
    )

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()
    with Dataset(out_path, "w", format="NETCDF4") as ds:
        ds.schema = runtime_v3.RUNTIME_SCHEMA
        ds.generator_version = runtime_v3.GENERATOR_VERSION
        ds.product_kind = "sealed-game-generative-world"
        ds.world_build_id = world_build_id
        ds.world_seed = int(canonical.CANONICAL_WORLD_SEED)
        ds.workshop_count = int(canonical.CANONICAL_WORKSHOPS)
        ds.intensity_steps = int(canonical.CANONICAL_STEPS)
        ds.target_geography_nodes = int(canonical.CANONICAL_NODES)
        ds.population_cells = int(population_cells)
        ds.target_player_objects = int(runtime_v3.TARGET_OBJECTS)
        ds.hypothesis_sha256 = hypothesis_sha
        ds.repair_certificate_sha256 = supplied_cert_hash
        ds.cutoff_plan_sha256 = _sha256_file(Path(cutoff_plan_path))
        ds.canonical_hydro_realization_id = canonical_hydro_id
        ds.minority_hydro_realization_id = minority_hydro_id
        ds.canonical_hydro_realization_signature = str(certificate["canonical_hydro_realization_signature"])
        ds.cell_hash_policy = runtime_v3.CELL_HASH_POLICY
        ds.profile_hash_policy = runtime_v3.PROFILE_HASH_POLICY
        ds.runtime_fingerprint = fingerprint
        ds.hypothesis_storage = "embedded-canonical-json-bytes"
        ds.expansion_policy = "rebuild-selected-cell-then-materialize-selected-lineage"

        ds.createDimension("cell", population_cells)
        ds.createDimension("hash_byte", 32)
        ds.createDimension("shard", expected_shards)
        ds.createDimension("hypothesis_byte", len(hypothesis_raw))
        ds.createDimension("hydro_override", len(override_tokens))
        ds.createDimension("token_byte", token_matrix.shape[1])

        def cv(name: str, dtype: str, dims: tuple[str, ...]):
            return ds.createVariable(name, dtype, dims, zlib=True, complevel=6, shuffle=True)

        cv("cell_recorded_weight", "f8", ("cell",))[:] = cell_recorded
        cv("cell_loss_intensity", "f8", ("cell",))[:] = cell_loss
        cv("cell_lineage_count", "i8", ("cell",))[:] = cell_lineages
        cv("cell_profile_count", "i4", ("cell",))[:] = cell_profiles
        cv("cell_identity_sha256", "u1", ("cell", "hash_byte"))[:, :] = cell_identity_hashes
        cv("cell_profile_sha256", "u1", ("cell", "hash_byte"))[:, :] = cell_profile_hashes
        cv("shard_phase01_sha256", "u1", ("shard", "hash_byte"))[:, :] = shard_phase01_hashes
        cv("shard_global_cell_start", "i4", ("shard",))[:] = shard_start
        cv("shard_global_cell_stop", "i4", ("shard",))[:] = shard_stop
        cv("hypothesis_bytes", "u1", ("hypothesis_byte",))[:] = np.frombuffer(hypothesis_raw, dtype=np.uint8)
        cv("hydro_override_node_token", "u1", ("hydro_override", "token_byte"))[:, :] = token_matrix
        cv("hydro_override_context", "f8", ("hydro_override",))[:] = override_values

    with Dataset(out_path, "r") as ds:
        if str(ds.schema) != runtime_v3.RUNTIME_SCHEMA or str(ds.runtime_fingerprint) != fingerprint:
            raise RuntimeError("R17 NetCDF roundtrip metadata mismatch")
        if not np.array_equal(ds.variables["cell_identity_sha256"][:], cell_identity_hashes):
            raise RuntimeError("R17 cell identity hashes changed in NetCDF roundtrip")
        if not np.array_equal(ds.variables["cell_profile_sha256"][:], cell_profile_hashes):
            raise RuntimeError("R17 cell profile hashes changed in NetCDF roundtrip")

    return {
        "schema": runtime_v3.RUNTIME_SCHEMA,
        "world_build_id": world_build_id,
        "runtime_fingerprint": fingerprint,
        "cells": population_cells,
        "shards": expected_shards,
        "lineages_represented": int(total_lineages),
        "recorded_weight": float(math.fsum(total_recorded_profiles)),
        "loss_intensity": float(math.fsum(total_loss_profiles)),
        "hydro_overrides": len(override_tokens),
        "capsule_backed_shards": capsule_count,
        "bytes": out_path.stat().st_size,
        "output": str(out_path),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fragments", type=Path, required=True)
    ap.add_argument("--cutoff-plan", type=Path, required=True)
    ap.add_argument("--repair-certificate", type=Path, required=True)
    ap.add_argument("--hypothesis", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--expected-shards", type=int, default=580)
    ap.add_argument("--population-cells", type=int, default=37100)
    args = ap.parse_args()
    result = build_runtime(
        fragments_dir=args.fragments,
        cutoff_plan_path=args.cutoff_plan,
        repair_certificate_path=args.repair_certificate,
        hypothesis_path=args.hypothesis,
        out_path=args.out,
        expected_shards=args.expected_shards,
        population_cells=args.population_cells,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
