from __future__ import annotations

"""Canonical full-build manifest for Atolia v3 phase 07.

Phase 07 deliberately separates scientific identity from storage layout:

* ``world_build_id`` fingerprints the canonical world/model configuration and is
  independent of shard size;
* ``phase07_manifest_sha256`` fingerprints the exact ordered shard set plus the
  globally merged deposition-pool and tool-use summaries.

The body of the canonical master is stored in bounded NetCDF shards.  The
manifest is therefore the canonical root object consumed by phase 08.
"""

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from netCDF4 import Dataset


V3_PHASE07_SCHEMA = "atolia-v3-canonical-full-manifest-v1"
V3_PHASE07_PHASE = "atolia-v3-07-canonical-full"
PHASE07_HASH_POLICY = "canonical-float-10sig-v1"
RECOVERY_MANIFEST_SCHEMA = "atolia-v3-phase07-recovery-manifest-v1"
RECOVERY_OVERLAY_POLICY = (
    "immutable-source-record-preserved; canonical-hydro-identity-and-context-projected; "
    "external-exchange-delta-capsule-backed"
)


def _canonical_float(value: float) -> float:
    x = float(value)
    if not math.isfinite(x):
        raise ValueError("phase-07 manifest cannot hash non-finite float")
    if x == 0.0:
        return 0.0
    return float(format(x, ".10g"))


def _plain(value: Any) -> Any:
    if isinstance(value, np.generic):
        return _plain(value.item())
    if isinstance(value, float):
        return _canonical_float(value)
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def stable_json(value: Any) -> str:
    return json.dumps(_plain(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def world_build_id(config: Mapping[str, Any]) -> str:
    """Scientific world identity; operational shard sizing is intentionally absent."""
    payload = {
        "schema": V3_PHASE07_SCHEMA,
        "world_seed": int(config["world_seed"]),
        "workshop_count": int(config["workshop_count"]),
        "intensity_steps": int(config["intensity_steps"]),
        "target_geography_nodes": int(config["target_geography_nodes"]),
        "hypothesis_sha256": str(config["hypothesis_sha256"]),
        "intensity_model_version": str(config["intensity_model_version"]),
        "biography_model_version": str(config["biography_model_version"]),
        "metallurgy_model_version": str(config["metallurgy_model_version"]),
        "workshop_model_version": str(config["workshop_model_version"]),
        "phase05_model_version": str(config["phase05_model_version"]),
    }
    return hashlib.sha256(stable_json(payload).encode("utf-8")).hexdigest()


def chunk_hash(record: Mapping[str, Any]) -> str:
    payload = {
        "world_build_id": str(record["world_build_id"]),
        "chunk_ordinal": int(record["chunk_ordinal"]),
        "global_cell_start": int(record["global_cell_start"]),
        "global_cell_stop": int(record["global_cell_stop"]),
        "cell_count": int(record["cell_count"]),
        "loss_strata": int(record["loss_strata"]),
        "phase01_spine_sha256": str(record["phase01_spine_sha256"]),
        "phase02_biography_sha256": str(record["phase02_biography_sha256"]),
        "phase03_metallurgy_sha256": str(record["phase03_metallurgy_sha256"]),
        "phase04_workshop_sha256": str(record["phase04_workshop_sha256"]),
        "phase05_sha256": str(record["phase05_sha256"]),
    }
    return hashlib.sha256(stable_json(payload).encode("utf-8")).hexdigest()


def manifest_hash(
    config: Mapping[str, Any],
    shards: Sequence[Mapping[str, Any]],
    deposition_pools: Sequence[Mapping[str, Any]],
    tool_use: Sequence[Mapping[str, Any]],
    totals: Mapping[str, Any],
) -> str:
    payload = {
        "hash_policy": PHASE07_HASH_POLICY,
        "world_build_id": world_build_id(config),
        "product_scope": str(config["product_scope"]),
        "population_cells": int(config["population_cells"]),
        "materialized_cells": int(config["materialized_cells"]),
        "shards": [_plain(dict(row)) for row in shards],
        "deposition_pools": [_plain(dict(row)) for row in deposition_pools],
        "tool_use": [_plain(dict(row)) for row in tool_use],
        "totals": _plain(dict(totals)),
    }
    return hashlib.sha256(stable_json(payload).encode("utf-8")).hexdigest()


def _string_var(group: Any, name: str, dim: str, values: Sequence[Any]) -> None:
    var = group.createVariable(name, str, (dim,))
    if values:
        var[:] = np.asarray(["" if v is None else str(v) for v in values], dtype=object)


def _numeric_var(group: Any, name: str, dtype: str, dim: str, values: Sequence[Any]) -> None:
    var = group.createVariable(name, dtype, (dim,), zlib=True, complevel=4, shuffle=True)
    if values:
        var[:] = np.asarray(values)


def write_manifest(
    path: Path,
    *,
    config: Mapping[str, Any],
    shards: Sequence[Mapping[str, Any]],
    deposition_pools: Sequence[Mapping[str, Any]],
    tool_use: Sequence[Mapping[str, Any]],
    totals: Mapping[str, Any],
) -> dict[str, Any]:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    build_id = world_build_id(config)
    digest = manifest_hash(config, shards, deposition_pools, tool_use, totals)

    with Dataset(path, "w", format="NETCDF4") as ds:
        ds.schema = V3_PHASE07_SCHEMA
        ds.phase = V3_PHASE07_PHASE
        ds.latest_phase = V3_PHASE07_PHASE
        ds.product_kind = "canonical_full_manifest"
        ds.hash_policy = PHASE07_HASH_POLICY
        ds.world_build_id = build_id
        ds.phase07_manifest_sha256 = digest
        ds.product_scope = str(config["product_scope"])
        ds.world_seed = int(config["world_seed"])
        ds.workshop_count = int(config["workshop_count"])
        ds.intensity_steps = int(config["intensity_steps"])
        ds.target_geography_nodes = int(config["target_geography_nodes"])
        ds.hypothesis_sha256 = str(config["hypothesis_sha256"])
        ds.population_cells = int(config["population_cells"])
        ds.materialized_cells = int(config["materialized_cells"])
        ds.chunk_cells = int(config["chunk_cells"])
        ds.resume_policy = "validated-immutable-shard-reuse-v1"
        ds.deposition_pool_scope = "global-node-date-mode-aggregate"
        ds.tool_use_scope = "global-across-all-canonical-shards"
        ds.model_versions_json = stable_json({
            k: config[k] for k in (
                "intensity_model_version", "biography_model_version",
                "metallurgy_model_version", "workshop_model_version",
                "phase05_model_version",
            )
        })
        ds.totals_json = stable_json(totals)

        gs = ds.createGroup("shards")
        gs.createDimension("shard", len(shards))
        for field in (
            "shard_name", "chunk_sha256", "phase01_spine_sha256",
            "phase02_biography_sha256", "phase03_metallurgy_sha256",
            "phase04_workshop_sha256", "phase05_sha256",
        ):
            _string_var(gs, field, "shard", [row[field] for row in shards])
        for field in (
            "chunk_ordinal", "global_cell_start", "global_cell_stop", "cell_count",
            "loss_strata", "particles", "batches", "operations",
            "external_exchange_tails", "deposition_assignments", "archaeology_rows",
        ):
            _numeric_var(gs, field, "i8", "shard", [int(row[field]) for row in shards])

        gp = ds.createGroup("deposition_pools")
        gp.createDimension("pool", len(deposition_pools))
        for field in ("deposition_pool_id", "node_id", "mode", "hydro_realization_id"):
            _string_var(gp, field, "pool", [row[field] for row in deposition_pools])
        _numeric_var(gp, "date_bc", "i4", "pool", [int(row["date_bc"]) for row in deposition_pools])
        _numeric_var(gp, "member_count", "i8", "pool", [int(row["member_count"]) for row in deposition_pools])
        for field in ("represented_weight", "hydro_context_score"):
            _numeric_var(gp, field, "f8", "pool", [float(row[field]) for row in deposition_pools])

        gt = ds.createGroup("tool_use")
        gt.createDimension("tool", len(tool_use))
        _string_var(gt, "tool_id", "tool", [row["tool_id"] for row in tool_use])
        _numeric_var(gt, "localized_operation_count", "i8", "tool", [int(row["localized_operation_count"]) for row in tool_use])
        _numeric_var(gt, "represented_operation_weight", "f8", "tool", [float(row["represented_operation_weight"]) for row in tool_use])
        _numeric_var(gt, "represented_mass_kg", "f8", "tool", [float(row["represented_mass_kg"]) for row in tool_use])

    return {
        "path": str(path),
        "phase": V3_PHASE07_PHASE,
        "schema": V3_PHASE07_SCHEMA,
        "hash_policy": PHASE07_HASH_POLICY,
        "product_scope": str(config["product_scope"]),
        "world_build_id": build_id,
        "phase07_manifest_sha256": digest,
        "population_cells": int(config["population_cells"]),
        "materialized_cells": int(config["materialized_cells"]),
        "shards": len(shards),
        "global_deposition_pools": len(deposition_pools),
        "global_tools": len(tool_use),
        **{str(k): _plain(v) for k, v in totals.items()},
    }


def recovery_overlay_hash(rows: Sequence[Mapping[str, Any]]) -> str:
    payload = {
        "schema": RECOVERY_MANIFEST_SCHEMA,
        "policy": RECOVERY_OVERLAY_POLICY,
        "overlays": [_plain(dict(row)) for row in rows],
    }
    return hashlib.sha256(stable_json(payload).encode("utf-8")).hexdigest()


def append_recovery_metadata(
    path: Path,
    overlays: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Attach a separately hashed repair lineage to an existing logical manifest.

    The ordinary phase-07 manifest hash continues to cover the logical shard
    counts and globally merged public tables.  This second root commits to the
    immutable source fragment/phase-05 hashes and the exact replay capsules used
    to project minority shards into the chosen observed realization.
    """
    ordered = sorted((_plain(dict(row)) for row in overlays), key=lambda row: int(row["chunk_ordinal"]))
    ordinals = [int(row["chunk_ordinal"]) for row in ordered]
    if len(ordinals) != len(set(ordinals)):
        raise RuntimeError("phase-07 recovery metadata contains duplicate chunk ordinals")
    digest = recovery_overlay_hash(ordered)
    path = Path(path)
    with Dataset(path, "a") as ds:
        if "recovery" in ds.groups:
            raise RuntimeError("phase-07 manifest already contains recovery metadata")
        ds.recovery_schema = RECOVERY_MANIFEST_SCHEMA
        ds.recovery_policy = RECOVERY_OVERLAY_POLICY
        ds.recovery_overlay_sha256 = digest
        ds.recovery_overlay_count = len(ordered)
        group = ds.createGroup("recovery")
        group.createDimension("overlay", len(ordered))
        for field in (
            "source_fragment_sha256",
            "repaired_fragment_sha256",
            "source_hydro_realization_id",
            "canonical_hydro_realization_id",
            "source_hydro_realization_signature",
            "canonical_hydro_realization_signature",
            "source_chunk_sha256",
            "source_phase05_sha256",
            "replay_capsule_sha256",
        ):
            _string_var(group, field, "overlay", [row.get(field, "") for row in ordered])
        for field in (
            "chunk_ordinal",
            "hydro_identity_replacement_count",
            "hydro_context_replacement_count",
            "source_external_exchange_tails",
            "external_exchange_count_delta",
            "canonical_external_exchange_tails",
        ):
            _numeric_var(group, field, "i8", "overlay", [int(row[field]) for row in ordered])
    return {
        "schema": RECOVERY_MANIFEST_SCHEMA,
        "policy": RECOVERY_OVERLAY_POLICY,
        "recovery_overlay_sha256": digest,
        "overlay_count": len(ordered),
        "chunk_ordinals": ordinals,
    }


def _read_strings(group: Any, name: str) -> list[str]:
    return [v.decode("utf-8") if isinstance(v, bytes) else str(v) for v in group.variables[name][:]]


def _read_recovery_metadata(ds: Any) -> dict[str, Any] | None:
    if "recovery" not in ds.groups:
        return None
    if str(getattr(ds, "recovery_schema", "")) != RECOVERY_MANIFEST_SCHEMA:
        raise RuntimeError("phase-07 recovery manifest schema mismatch")
    if str(getattr(ds, "recovery_policy", "")) != RECOVERY_OVERLAY_POLICY:
        raise RuntimeError("phase-07 recovery manifest policy mismatch")
    group = ds.groups["recovery"]
    count = len(group.dimensions["overlay"])
    string_fields = (
        "source_fragment_sha256",
        "repaired_fragment_sha256",
        "source_hydro_realization_id",
        "canonical_hydro_realization_id",
        "source_hydro_realization_signature",
        "canonical_hydro_realization_signature",
        "source_chunk_sha256",
        "source_phase05_sha256",
        "replay_capsule_sha256",
    )
    int_fields = (
        "chunk_ordinal",
        "hydro_identity_replacement_count",
        "hydro_context_replacement_count",
        "source_external_exchange_tails",
        "external_exchange_count_delta",
        "canonical_external_exchange_tails",
    )
    strings = {field: _read_strings(group, field) for field in string_fields}
    integers = {field: group.variables[field][:] for field in int_fields}
    rows = []
    for index in range(count):
        row = {field: strings[field][index] for field in string_fields}
        row.update({field: int(integers[field][index]) for field in int_fields})
        rows.append(row)
    if rows != sorted(rows, key=lambda row: int(row["chunk_ordinal"])):
        raise RuntimeError("phase-07 recovery overlays are not ordered by chunk ordinal")
    if int(getattr(ds, "recovery_overlay_count", -1)) != count:
        raise RuntimeError("phase-07 recovery overlay count mismatch")
    computed = recovery_overlay_hash(rows)
    if computed != str(getattr(ds, "recovery_overlay_sha256", "")):
        raise RuntimeError("phase-07 recovery overlay hash mismatch")
    return {
        "schema": RECOVERY_MANIFEST_SCHEMA,
        "policy": RECOVERY_OVERLAY_POLICY,
        "recovery_overlay_sha256": computed,
        "overlay_count": count,
        "overlays": rows,
    }


def read_manifest(path: Path) -> dict[str, Any]:
    path = Path(path)
    with Dataset(path, "r") as ds:
        gs = ds.groups["shards"]
        n = len(gs.dimensions["shard"])
        sstrings = {name: _read_strings(gs, name) for name in (
            "shard_name", "chunk_sha256", "phase01_spine_sha256",
            "phase02_biography_sha256", "phase03_metallurgy_sha256",
            "phase04_workshop_sha256", "phase05_sha256",
        )}
        sint = {name: gs.variables[name][:] for name in (
            "chunk_ordinal", "global_cell_start", "global_cell_stop", "cell_count",
            "loss_strata", "particles", "batches", "operations",
            "external_exchange_tails", "deposition_assignments", "archaeology_rows",
        )}
        shards = []
        for i in range(n):
            row = {name: sstrings[name][i] for name in sstrings}
            row.update({name: int(sint[name][i]) for name in sint})
            row["world_build_id"] = str(ds.world_build_id)
            shards.append(row)

        gp = ds.groups["deposition_pools"]
        pn = len(gp.dimensions["pool"])
        pstr = {name: _read_strings(gp, name) for name in ("deposition_pool_id", "node_id", "mode", "hydro_realization_id")}
        pools = [
            {
                **{name: pstr[name][i] for name in pstr},
                "date_bc": int(gp.variables["date_bc"][i]),
                "member_count": int(gp.variables["member_count"][i]),
                "represented_weight": float(gp.variables["represented_weight"][i]),
                "hydro_context_score": float(gp.variables["hydro_context_score"][i]),
            }
            for i in range(pn)
        ]

        gt = ds.groups["tool_use"]
        tn = len(gt.dimensions["tool"])
        tids = _read_strings(gt, "tool_id")
        tool_use = [
            {
                "tool_id": tids[i],
                "localized_operation_count": int(gt.variables["localized_operation_count"][i]),
                "represented_operation_weight": float(gt.variables["represented_operation_weight"][i]),
                "represented_mass_kg": float(gt.variables["represented_mass_kg"][i]),
            }
            for i in range(tn)
        ]

        versions = json.loads(str(ds.model_versions_json))
        config = {
            "product_scope": str(ds.product_scope),
            "world_seed": int(ds.world_seed),
            "workshop_count": int(ds.workshop_count),
            "intensity_steps": int(ds.intensity_steps),
            "target_geography_nodes": int(ds.target_geography_nodes),
            "hypothesis_sha256": str(ds.hypothesis_sha256),
            "population_cells": int(ds.population_cells),
            "materialized_cells": int(ds.materialized_cells),
            "chunk_cells": int(ds.chunk_cells),
            **versions,
        }
        totals = json.loads(str(ds.totals_json))
        computed_build_id = world_build_id(config)
        if computed_build_id != str(ds.world_build_id):
            raise RuntimeError("phase-07 world_build_id mismatch")
        computed = manifest_hash(config, shards, pools, tool_use, totals)
        if computed != str(ds.phase07_manifest_sha256):
            raise RuntimeError("phase-07 manifest hash mismatch")
        result = {
            "schema": str(ds.schema),
            "phase": str(ds.phase),
            "hash_policy": str(ds.hash_policy),
            "product_scope": str(ds.product_scope),
            "world_build_id": str(ds.world_build_id),
            "phase07_manifest_sha256": str(ds.phase07_manifest_sha256),
            "config": config,
            "shards": shards,
            "deposition_pools": pools,
            "tool_use": tool_use,
            "totals": totals,
        }
        recovery = _read_recovery_metadata(ds)
        if recovery is not None:
            result["recovery"] = recovery
        return result
