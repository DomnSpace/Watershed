from __future__ import annotations

"""NetCDF append/read support for Atolia v3 phase-05 environmental/deposition truth."""

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from netCDF4 import Dataset

import v3_hydro_exchange_deposition as phase05


V3_PHASE05_SCHEMA = "atolia-v3-hydro-exchange-deposition-v1"
V3_PHASE05_PHASE = "atolia-v3-05-hydro-exchange-deposition"
PHASE05_HASH_POLICY = "canonical-float-12sig-v1"

TABLE_LAYOUT = {
    "hydro_evidence": ("hydro", "evidence", "hydro_evidence"),
    "hydro_ensemble": ("hydro", "ensemble", "hydro_ensemble"),
    "hydro_realization": ("hydro", "realization", "hydro_realization"),
    "external_exchange": ("exchange", "tails", "external_exchange"),
    "deposition_assignments": ("deposition", "assignments", "deposition_assignment"),
    "deposition_pools": ("deposition", "pools", "deposition_pool"),
    "archaeology": ("archaeology", "observation", "archaeology_observation"),
}

SCHEMAS: dict[str, tuple[tuple[str, str], ...]] = {
    "hydro_evidence": (
        ("evidence_id", "str"), ("a", "str"), ("b", "str"),
        ("evidence_kind", "str"), ("provenance", "str"), ("mode", "str"),
        ("confidence", "f8"), ("navigability", "f8"), ("empirical", "bool"),
    ),
    "hydro_ensemble": (
        ("edge_id", "str"), ("a", "str"), ("b", "str"), ("mode", "str"),
        ("probability", "f8"), ("navigability", "f8"), ("structural", "bool"),
        ("evidence_ids_json", "str"), ("empirical_evidence_count", "i4"),
        ("probability_basis", "str"),
    ),
    "hydro_realization": (
        ("realization_id", "str"), ("edge_id", "str"), ("a", "str"),
        ("b", "str"), ("mode", "str"), ("realized", "bool"),
        ("draw", "f8"), ("probability", "f8"), ("navigability", "f8"),
        ("structural", "bool"),
    ),
    "external_exchange": (
        ("exchange_id", "str"), ("particle_id", "str"),
        ("external_component_id", "str"), ("trigger", "str"),
        ("contact_probability", "f8"), ("contact_intensity", "f8"),
        ("node_id", "str"), ("date_bc", "i4"), ("represented_weight", "f8"),
    ),
    "deposition_assignments": (
        ("particle_id", "str"), ("loss_site_id", "str"),
        ("deposition_pool_id", "str"), ("hydro_realization_id", "str"),
        ("node_id", "str"), ("date_bc", "i4"), ("mode", "str"),
        ("mode_probability", "f8"), ("mode_weights_json", "str"),
        ("represented_weight", "f8"), ("expected_field_crossings", "f8"),
        ("expected_physical_crossings", "f8"), ("hydro_context_score", "f8"),
    ),
    "deposition_pools": (
        ("deposition_pool_id", "str"), ("node_id", "str"), ("date_bc", "i4"),
        ("mode", "str"), ("member_count", "i4"), ("represented_weight", "f8"),
        ("hydro_realization_id", "str"), ("hydro_context_score", "f8"),
    ),
    "archaeology": (
        ("particle_id", "str"), ("deposition_pool_id", "str"),
        ("represented_loss_weight", "f8"), ("p_survival", "f8"),
        ("survival_weight", "f8"), ("p_discovery", "f8"),
        ("discovery_weight", "f8"), ("p_record", "f8"),
        ("recorded_weight", "f8"),
    ),
}


def _canonical_float(value: float) -> float:
    x = float(value)
    if not math.isfinite(x):
        raise ValueError("phase-05 hash cannot canonicalize non-finite float")
    if x == 0.0:
        return 0.0
    return float(format(x, ".12g"))


def _hash_plain(value: Any) -> Any:
    if isinstance(value, np.generic):
        return _hash_plain(value.item())
    if isinstance(value, float):
        return _canonical_float(value)
    if isinstance(value, Mapping):
        return {str(k): _hash_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_hash_plain(v) for v in value]
    return value


def phase05_hash(tables: Mapping[str, Sequence[Mapping[str, Any]]]) -> str:
    payload = {
        "hash_policy": PHASE05_HASH_POLICY,
        "tables": {
            name: [_hash_plain(dict(row)) for row in tables[name]]
            for name in TABLE_LAYOUT
        },
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _serialization_rows(tables: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    out = {name: [dict(row) for row in rows] for name, rows in tables.items()}
    for row in out["hydro_ensemble"]:
        row["evidence_ids_json"] = json.dumps(row.pop("evidence_ids"), sort_keys=True, separators=(",", ":"))
    for row in out["deposition_assignments"]:
        row["mode_weights_json"] = json.dumps(row.pop("mode_weights"), sort_keys=True, separators=(",", ":"))
    return out


def _root_group(ds: Any, name: str) -> Any:
    return ds.groups.get(name) or ds.createGroup(name)


def _write_table(
    parent: Any,
    name: str,
    dim_name: str,
    rows: Sequence[Mapping[str, Any]],
    schema: Sequence[tuple[str, str]],
) -> None:
    group = parent.createGroup(name)
    group.createDimension(dim_name, len(rows))
    for field, kind in schema:
        values = [row[field] for row in rows]
        if kind == "str":
            var = group.createVariable(field, str, (dim_name,))
            if values:
                var[:] = np.asarray([str(v) for v in values], dtype=object)
            continue
        dtype = "i1" if kind == "bool" else kind
        var = group.createVariable(field, dtype, (dim_name,), zlib=True, complevel=4, shuffle=True)
        if values:
            if kind == "bool":
                var[:] = np.asarray([1 if bool(v) else 0 for v in values], dtype=np.int8)
            else:
                var[:] = np.asarray(values)


def append_phase05(
    path: Path,
    *,
    layer: phase05.Phase05Layer,
    world_seed: int,
    phase01_spine_sha256: str,
    phase02_biography_sha256: str,
    phase03_metallurgy_sha256: str,
    phase04_workshop_sha256: str,
) -> dict[str, Any]:
    path = Path(path)
    tables = phase05.flatten_phase05(layer)
    digest = phase05_hash(tables)
    serial = _serialization_rows(tables)

    with Dataset(path, "a") as ds:
        collisions = {"hydro", "exchange", "deposition", "archaeology"}.intersection(ds.groups)
        if collisions:
            raise RuntimeError("phase-05 groups already exist: " + ", ".join(sorted(collisions)))
        if str(getattr(ds, "phase04_workshop_sha256", "")) != str(phase04_workshop_sha256):
            raise RuntimeError("phase-05 append does not match phase-04 workshop hash")

        ds.latest_phase = V3_PHASE05_PHASE
        ds.phase05_schema = V3_PHASE05_SCHEMA
        ds.phase05_model_version = phase05.PHASE05_MODEL_VERSION
        ds.phase05_hash_policy = PHASE05_HASH_POLICY
        ds.phase05_world_seed = int(world_seed)
        ds.phase05_hydro_evidence_status = layer.hydro_evidence_status
        ds.phase05_exchange_status = layer.exchange_status
        ds.phase05_deposition_status = layer.deposition_status
        ds.phase05_observation_status = layer.observation_status
        ds.phase05_spine_sha256 = str(phase01_spine_sha256)
        ds.phase05_biography_sha256 = str(phase02_biography_sha256)
        ds.phase05_metallurgy_sha256 = str(phase03_metallurgy_sha256)
        ds.phase05_workshop_sha256 = str(phase04_workshop_sha256)
        ds.phase05_sha256 = digest

        roots: dict[str, Any] = {}
        for table_name, (root_name, child_name, dim_name) in TABLE_LAYOUT.items():
            root = roots.get(root_name)
            if root is None:
                root = _root_group(ds, root_name)
                roots[root_name] = root
            _write_table(root, child_name, dim_name, serial[table_name], SCHEMAS[table_name])

    realized = sum(bool(row["realized"]) for row in tables["hydro_realization"])
    total_loss = sum(float(row["represented_loss_weight"]) for row in tables["archaeology"])
    total_survival = sum(float(row["survival_weight"]) for row in tables["archaeology"])
    total_discovery = sum(float(row["discovery_weight"]) for row in tables["archaeology"])
    total_recorded = sum(float(row["recorded_weight"]) for row in tables["archaeology"])
    shared_pools = sum(int(row["member_count"]) > 1 for row in tables["deposition_pools"])
    return {
        "path": str(path),
        "phase": V3_PHASE05_PHASE,
        "schema": V3_PHASE05_SCHEMA,
        "model_version": phase05.PHASE05_MODEL_VERSION,
        "hash_policy": PHASE05_HASH_POLICY,
        "phase05_sha256": digest,
        "phase01_spine_sha256": str(phase01_spine_sha256),
        "phase02_biography_sha256": str(phase02_biography_sha256),
        "phase03_metallurgy_sha256": str(phase03_metallurgy_sha256),
        "phase04_workshop_sha256": str(phase04_workshop_sha256),
        "hydro_evidence_status": layer.hydro_evidence_status,
        "exchange_status": layer.exchange_status,
        "deposition_status": layer.deposition_status,
        "observation_status": layer.observation_status,
        "hydro_evidence": len(tables["hydro_evidence"]),
        "hydro_ensemble": len(tables["hydro_ensemble"]),
        "hydro_realized": int(realized),
        "external_exchange_tails": len(tables["external_exchange"]),
        "deposition_assignments": len(tables["deposition_assignments"]),
        "deposition_pools": len(tables["deposition_pools"]),
        "shared_deposition_pools": int(shared_pools),
        "archaeology_rows": len(tables["archaeology"]),
        "represented_loss_weight": float(total_loss),
        "survival_weight": float(total_survival),
        "discovery_weight": float(total_discovery),
        "recorded_weight": float(total_recorded),
    }


def _read_strings(var: Any) -> list[str]:
    values = var[:]
    return [value.decode("utf-8") if isinstance(value, bytes) else str(value) for value in values]


def _read_table(group: Any, dim_name: str, schema: Sequence[tuple[str, str]]) -> list[dict[str, Any]]:
    count = len(group.dimensions[dim_name])
    columns: dict[str, list[Any]] = {}
    for field, kind in schema:
        var = group.variables[field]
        if kind == "str":
            columns[field] = _read_strings(var)
        else:
            raw = var[:]
            if kind == "bool":
                columns[field] = [bool(int(v)) for v in raw]
            elif kind in {"i8", "i4"}:
                columns[field] = [int(v) for v in raw]
            else:
                columns[field] = [float(v) for v in raw]
    return [{field: columns[field][i] for field, _ in schema} for i in range(count)]


def read_phase05(path: Path) -> dict[str, Any]:
    path = Path(path)
    with Dataset(path, "r") as ds:
        serial: dict[str, list[dict[str, Any]]] = {}
        for table_name, (root_name, child_name, dim_name) in TABLE_LAYOUT.items():
            serial[table_name] = _read_table(ds.groups[root_name].groups[child_name], dim_name, SCHEMAS[table_name])

        tables = {name: [dict(row) for row in rows] for name, rows in serial.items()}
        for row in tables["hydro_ensemble"]:
            row["evidence_ids"] = json.loads(row.pop("evidence_ids_json"))
        for row in tables["deposition_assignments"]:
            row["mode_weights"] = json.loads(row.pop("mode_weights_json"))

        stored_policy = str(ds.phase05_hash_policy)
        if stored_policy != PHASE05_HASH_POLICY:
            raise RuntimeError(f"phase-05 hash policy mismatch: {stored_policy!r}")
        stored = str(ds.phase05_sha256)
        computed = phase05_hash(tables)
        if stored != computed:
            raise RuntimeError(f"v3 phase-05 hash mismatch: stored={stored} computed={computed}")

        return {
            "phase": str(ds.latest_phase),
            "schema": str(ds.phase05_schema),
            "model_version": str(ds.phase05_model_version),
            "hash_policy": stored_policy,
            "world_seed": int(ds.phase05_world_seed),
            "hydro_evidence_status": str(ds.phase05_hydro_evidence_status),
            "exchange_status": str(ds.phase05_exchange_status),
            "deposition_status": str(ds.phase05_deposition_status),
            "observation_status": str(ds.phase05_observation_status),
            "phase01_spine_sha256": str(ds.phase05_spine_sha256),
            "phase02_biography_sha256": str(ds.phase05_biography_sha256),
            "phase03_metallurgy_sha256": str(ds.phase05_metallurgy_sha256),
            "phase04_workshop_sha256": str(ds.phase05_workshop_sha256),
            "phase05_sha256": stored,
            **tables,
        }
