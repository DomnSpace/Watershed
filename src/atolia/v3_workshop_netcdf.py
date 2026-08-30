from __future__ import annotations

"""NetCDF append/read support for Atolia v3 phase-04 workshop ecology."""

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from netCDF4 import Dataset

import v3_workshop_ecology as ecology


V3_WORKSHOP_SCHEMA = "atolia-v3-workshop-guild-tools-v1"
V3_WORKSHOP_PHASE = "atolia-v3-04-workshop-guild-tools"
# Derived workshop affinities/capabilities include norm/exp arithmetic whose final
# 11th-12th significant digits can vary across CPU/libm/WASM implementations.
# Full f8 values remain stored; only the reproducibility projection is rounded.
WORKSHOP_HASH_POLICY = "canonical-float-10sig-v1"

TABLE_LAYOUT = {
    "workshops": ("workshops", "catalogue", "workshop"),
    "guilds": ("guilds", "catalogue", "guild"),
    "memberships": ("guilds", "membership", "membership"),
    "tool_archetypes": ("tools", "archetypes", "tool_archetype"),
    "archetype_operations": ("tools", "archetype_operations", "archetype_operation"),
    "tools": ("tools", "instances", "tool"),
    "tool_use": ("tools", "use_summary", "tool_use"),
    "operations": ("process", "operations", "operation"),
    "operation_tools": ("process", "operation_tools", "operation_tool"),
}

SCHEMAS: dict[str, tuple[tuple[str, str], ...]] = {
    "workshops": (
        ("workshop_index", "i8"), ("workshop_id", "str"), ("node_id", "str"),
        ("start_bc", "i4"), ("end_bc", "i4"), ("workers", "i4"),
        ("lineage_id", "str"), ("capacity_weight", "f8"), ("quality_memory", "f8"),
        ("tool_count", "i4"), ("primary_guild_id", "nstr"),
        ("primary_guild_strength", "f8"),
    ),
    "guilds": (
        ("guild_index", "i8"), ("guild_id", "str"), ("developer_name", "str"),
        ("anchor_node", "str"), ("world_mobility_scale", "f8"),
        ("profile_mobility_scale", "f8"), ("convergence_prior", "f8"),
        ("status_bias", "f8"), ("persistence_years", "f8"),
        ("technical_prototype_json", "str"), ("operations_json", "str"),
        ("classes_json", "str"), ("channels_json", "str"),
    ),
    "memberships": (
        ("membership_index", "i8"), ("workshop_index", "i8"), ("guild_index", "i8"),
        ("guild_id", "str"), ("affinity", "f8"), ("primary", "bool"),
    ),
    "tool_archetypes": (
        ("archetype_index", "i8"), ("family", "str"), ("subtype", "str"),
        ("mass_kg", "f8"), ("face_area_mm2", "f8"), ("face_radius_mm", "f8"),
        ("handle_length_mm", "f8"), ("precision_bias", "f8"),
        ("force_bias", "f8"), ("portability", "f8"),
    ),
    "archetype_operations": (
        ("archetype_operation_index", "i8"), ("archetype_index", "i8"),
        ("operation_type", "str"), ("weight", "f8"),
    ),
    "tools": (
        ("tool_index", "i8"), ("tool_id", "str"), ("workshop_index", "i8"),
        ("workshop_id", "str"), ("archetype_index", "i8"), ("family", "str"),
        ("subtype", "str"), ("lineage_depth", "i4"), ("mass_kg", "f8"),
        ("face_area_mm2", "f8"), ("face_radius_mm", "f8"),
        ("handle_length_mm", "f8"), ("precision_bias", "f8"),
        ("force_bias", "f8"), ("portability", "f8"), ("wear", "f8"),
        ("repair_count", "i4"), ("nickname", "str"),
    ),
    "tool_use": (
        ("tool_use_index", "i8"), ("tool_index", "i8"), ("tool_id", "str"),
        ("localized_operation_count", "i8"),
        ("represented_operation_weight", "f8"), ("represented_mass_kg", "f8"),
    ),
    "operations": (
        ("operation_index", "i8"), ("operation_id", "str"), ("particle_id", "str"),
        ("phase02_event_id", "nstr"), ("event_kind", "str"),
        ("object_episode_id", "str"), ("batch_id", "str"),
        ("object_class", "str"), ("operation_type", "str"),
        ("route_position_km", "f8"), ("node_id", "nstr"),
        ("workshop_index", "i8"), ("workshop_id", "nstr"),
        ("assignment_basis", "str"), ("primary_guild_id", "nstr"),
        ("primary_guild_affinity", "f8"), ("tool_set_id", "nstr"),
        ("capability", "f8"), ("operator_skill", "f8"), ("tool_fit", "f8"),
        ("support_fit", "f8"), ("thermal_fit", "f8"),
        ("measurement_fit", "f8"), ("material_fit", "f8"),
        ("represented_weight", "f8"), ("workpiece_mass_kg", "f8"),
        ("localized", "bool"),
    ),
    "operation_tools": (
        ("operation_tool_index", "i8"), ("operation_index", "i8"),
        ("tool_index", "i8"), ("tool_id", "str"), ("rank", "i4"),
        ("selection_score", "f8"),
    ),
}


def _plain(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def _canonical_float(value: float) -> float:
    x = float(value)
    if not math.isfinite(x):
        raise ValueError("phase-04 hash cannot canonicalize non-finite float")
    if x == 0.0:
        return 0.0
    return float(format(x, ".10g"))


def _hash_plain(value: Any, *, field: str | None = None) -> Any:
    if isinstance(value, np.generic):
        return _hash_plain(value.item(), field=field)
    if isinstance(value, float):
        return _canonical_float(value)
    if isinstance(value, Mapping):
        return {str(k): _hash_plain(v, field=str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_hash_plain(v) for v in value]
    if isinstance(value, str) and field is not None and field.endswith("_json"):
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return value
        return _hash_plain(decoded)
    return value


def stable_json(value: Any) -> str:
    return json.dumps(_plain(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def workshop_hash(tables: Mapping[str, Sequence[Mapping[str, Any]]]) -> str:
    payload = {
        "hash_policy": WORKSHOP_HASH_POLICY,
        "tables": {
            name: [_hash_plain(dict(row)) for row in tables[name]]
            for name in TABLE_LAYOUT
        },
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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
        if kind in {"str", "nstr"}:
            var = group.createVariable(field, str, (dim_name,))
            if values:
                var[:] = np.asarray(["" if v is None else str(v) for v in values], dtype=object)
            continue
        dtype = "i1" if kind == "bool" else kind
        var = group.createVariable(field, dtype, (dim_name,), zlib=True, complevel=4, shuffle=True)
        if values:
            if kind == "bool":
                var[:] = np.asarray([1 if bool(v) else 0 for v in values], dtype=np.int8)
            else:
                var[:] = np.asarray(values)


def append_workshop_layer(
    path: Path,
    *,
    layer: ecology.WorkshopLayer,
    world_seed: int,
    phase01_spine_sha256: str,
    phase02_biography_sha256: str,
    phase03_metallurgy_sha256: str,
) -> dict[str, Any]:
    path = Path(path)
    tables = ecology.flatten_workshop_layer(layer)
    digest = workshop_hash(tables)

    with Dataset(path, "a") as ds:
        collisions = {"workshops", "guilds", "tools", "process"}.intersection(ds.groups)
        if collisions:
            raise RuntimeError("phase-04 groups already exist: " + ", ".join(sorted(collisions)))
        if str(getattr(ds, "phase03_metallurgy_sha256", "")) != str(phase03_metallurgy_sha256):
            raise RuntimeError("phase-04 append does not match phase-03 metallurgy hash")

        ds.latest_phase = V3_WORKSHOP_PHASE
        ds.phase04_schema = V3_WORKSHOP_SCHEMA
        ds.phase04_model_version = ecology.WORKSHOP_MODEL_VERSION
        ds.phase04_assignment_policy = ecology.WORKSHOP_ASSIGNMENT_POLICY
        ds.phase04_operator_model_status = ecology.OPERATOR_MODEL_STATUS
        ds.phase04_material_fit_status = ecology.MATERIAL_FIT_STATUS
        ds.phase04_hash_policy = WORKSHOP_HASH_POLICY
        ds.phase04_world_seed = int(world_seed)
        ds.phase04_spine_sha256 = str(phase01_spine_sha256)
        ds.phase04_biography_sha256 = str(phase02_biography_sha256)
        ds.phase04_metallurgy_sha256 = str(phase03_metallurgy_sha256)
        ds.phase04_workshop_sha256 = digest

        roots: dict[str, Any] = {}
        for table_name, (root_name, child_name, dim_name) in TABLE_LAYOUT.items():
            root = roots.get(root_name)
            if root is None:
                root = _root_group(ds, root_name)
                roots[root_name] = root
            _write_table(root, child_name, dim_name, tables[table_name], SCHEMAS[table_name])

    localized = sum(bool(row["localized"]) for row in tables["operations"])
    return {
        "path": str(path),
        "phase": V3_WORKSHOP_PHASE,
        "schema": V3_WORKSHOP_SCHEMA,
        "model_version": ecology.WORKSHOP_MODEL_VERSION,
        "assignment_policy": ecology.WORKSHOP_ASSIGNMENT_POLICY,
        "operator_model_status": ecology.OPERATOR_MODEL_STATUS,
        "material_fit_status": ecology.MATERIAL_FIT_STATUS,
        "hash_policy": WORKSHOP_HASH_POLICY,
        "workshop_sha256": digest,
        "phase01_spine_sha256": str(phase01_spine_sha256),
        "phase02_biography_sha256": str(phase02_biography_sha256),
        "phase03_metallurgy_sha256": str(phase03_metallurgy_sha256),
        "localized_operations": int(localized),
        "unlocalized_operations": int(len(tables["operations"]) - localized),
        **{name: len(rows) for name, rows in tables.items()},
    }


def _read_strings(var: Any, *, nullable: bool) -> list[Any]:
    out = []
    for value in var[:]:
        text = value.decode("utf-8") if isinstance(value, bytes) else str(value)
        out.append(None if nullable and text == "" else text)
    return out


def _read_table(group: Any, dim_name: str, schema: Sequence[tuple[str, str]]) -> list[dict[str, Any]]:
    count = len(group.dimensions[dim_name])
    columns: dict[str, list[Any]] = {}
    for field, kind in schema:
        var = group.variables[field]
        if kind in {"str", "nstr"}:
            columns[field] = _read_strings(var, nullable=(kind == "nstr"))
        else:
            raw = var[:]
            if kind == "bool":
                columns[field] = [bool(int(v)) for v in raw]
            elif kind in {"i8", "i4"}:
                columns[field] = [int(v) for v in raw]
            else:
                columns[field] = [float(v) for v in raw]
    return [{field: columns[field][i] for field, _ in schema} for i in range(count)]


def read_workshop_layer(path: Path) -> dict[str, Any]:
    path = Path(path)
    with Dataset(path, "r") as ds:
        tables: dict[str, list[dict[str, Any]]] = {}
        for table_name, (root_name, child_name, dim_name) in TABLE_LAYOUT.items():
            tables[table_name] = _read_table(
                ds.groups[root_name].groups[child_name], dim_name, SCHEMAS[table_name]
            )

        stored_policy = str(getattr(ds, "phase04_hash_policy", ""))
        if stored_policy != WORKSHOP_HASH_POLICY:
            raise RuntimeError(
                "v3 phase-04 hash policy mismatch: "
                f"stored={stored_policy!r} expected={WORKSHOP_HASH_POLICY!r}"
            )
        stored = str(ds.phase04_workshop_sha256)
        computed = workshop_hash(tables)
        if stored != computed:
            raise RuntimeError(
                f"v3 phase-04 workshop hash mismatch: stored={stored} computed={computed}"
            )
        return {
            "phase": str(ds.latest_phase),
            "schema": str(ds.phase04_schema),
            "model_version": str(ds.phase04_model_version),
            "assignment_policy": str(ds.phase04_assignment_policy),
            "operator_model_status": str(ds.phase04_operator_model_status),
            "material_fit_status": str(ds.phase04_material_fit_status),
            "hash_policy": stored_policy,
            "world_seed": int(ds.phase04_world_seed),
            "phase01_spine_sha256": str(ds.phase04_spine_sha256),
            "phase02_biography_sha256": str(ds.phase04_biography_sha256),
            "phase03_metallurgy_sha256": str(ds.phase04_metallurgy_sha256),
            "workshop_sha256": stored,
            **tables,
        }
