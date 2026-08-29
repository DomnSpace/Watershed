from __future__ import annotations

"""NetCDF append/read support for Atolia v3 phase-03 source metallurgy."""

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from netCDF4 import Dataset

import v3_metal_biography as biography
import v3_source_metallurgy as metallurgy


V3_METALLURGY_SCHEMA = "atolia-v3-source-metallurgy-v1"
V3_METALLURGY_PHASE = "atolia-v3-03-source-metallurgy"

SOURCE_FLOAT_FIELDS = (
    "pb_ppm", "Pb206_204", "Pb207_204", "Pb208_204",
    "Sb_ppm", "Ag_ppm", "Ni_ppm", "Co_ppm", "Bi_ppm",
)
BATCH_FLOAT_FIELDS = (
    "metal_mass_kg", "element_mass_sum_kg", "pb_mass_kg",
    "Pb206_204", "Pb207_204", "Pb208_204",
)


def _plain(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def stable_json(value: Any) -> str:
    return json.dumps(
        _plain(value),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def metallurgy_hash(
    source_rows: Sequence[Mapping[str, Any]],
    tables: Mapping[str, Sequence[Mapping[str, Any]]],
) -> str:
    payload = {
        "sources": [_plain(dict(r)) for r in source_rows],
        **{
            name: [_plain(dict(r)) for r in tables[name]]
            for name in ("chemistry_batches", "elements", "pb_isotopes", "source_pb")
        },
    }
    return hashlib.sha256(stable_json(payload).encode("utf-8")).hexdigest()


def _make_group(parent: Any, name: str, dim_name: str, count: int) -> Any:
    group = parent.createGroup(name)
    group.createDimension(dim_name, int(count))
    return group


def _string_var(group: Any, name: str, dim: str, values: Sequence[Any]) -> None:
    var = group.createVariable(name, str, (dim,))
    if values:
        var[:] = np.asarray(
            ["" if value is None else str(value) for value in values],
            dtype=object,
        )


def _numeric_var(
    group: Any,
    name: str,
    dtype: str,
    dim: str,
    values: Sequence[Any],
) -> None:
    var = group.createVariable(
        name, dtype, (dim,), zlib=True, complevel=4, shuffle=True
    )
    if values:
        var[:] = np.asarray(list(values))


def append_metallurgy(
    path: Path,
    *,
    world: Any,
    lineages: Sequence[biography.MetalLineage],
    chemistry: Sequence[metallurgy.MetallurgyLineage],
    world_seed: int,
    phase01_spine_sha256: str,
    phase02_biography_sha256: str,
) -> dict[str, Any]:
    path = Path(path)
    source_rows = metallurgy.source_table_rows(world)
    tables = metallurgy.flatten_metallurgy(lineages, chemistry)
    digest = metallurgy_hash(source_rows, tables)

    with Dataset(path, "a") as ds:
        collisions = {"sources", "metallurgy"}.intersection(ds.groups)
        if collisions:
            raise RuntimeError(
                "phase-03 groups already exist: " + ", ".join(sorted(collisions))
            )
        if str(getattr(ds, "phase02_biography_sha256", "")) != str(
            phase02_biography_sha256
        ):
            raise RuntimeError("phase-03 append does not match phase-02 biography hash")

        ds.latest_phase = V3_METALLURGY_PHASE
        ds.phase03_schema = V3_METALLURGY_SCHEMA
        ds.phase03_model_version = metallurgy.SOURCE_METALLURGY_VERSION
        ds.phase03_source_calibration_status = metallurgy.SOURCE_CALIBRATION_STATUS
        ds.phase03_process_recipe_status = metallurgy.PROCESS_RECIPE_STATUS
        ds.phase03_world_seed = int(world_seed)
        ds.phase03_spine_sha256 = str(phase01_spine_sha256)
        ds.phase03_biography_sha256 = str(phase02_biography_sha256)
        ds.phase03_metallurgy_sha256 = digest
        ds.phase03_conservation_contract = (
            "element masses and Pb isotope masses are conserved through "
            "phase-02 parent contributions; isotope ratios are derived views"
        )

        gs = ds.createGroup("sources")
        sg = _make_group(gs, "geochemistry", "source", len(source_rows))
        _string_var(sg, "source_id", "source", [r["source_id"] for r in source_rows])
        _string_var(sg, "label", "source", [r["label"] for r in source_rows])
        _string_var(
            sg,
            "calibration_status",
            "source",
            [r["calibration_status"] for r in source_rows],
        )
        for name in SOURCE_FLOAT_FIELDS:
            _numeric_var(sg, name, "f8", "source", [r[name] for r in source_rows])

        gm = ds.createGroup("metallurgy")
        b = tables["chemistry_batches"]
        gb = _make_group(gm, "batches", "chemistry_batch", len(b))
        _numeric_var(
            gb,
            "chemistry_batch_index",
            "i8",
            "chemistry_batch",
            [r["chemistry_batch_index"] for r in b],
        )
        for name in BATCH_FLOAT_FIELDS:
            _numeric_var(gb, name, "f8", "chemistry_batch", [r[name] for r in b])
        for name in ("batch_id", "particle_id", "pb_dominant_source_id", "recipe_status"):
            _string_var(gb, name, "chemistry_batch", [r[name] for r in b])

        e = tables["elements"]
        ge = _make_group(gm, "elements", "element_row", len(e))
        for name in ("element_row_index", "chemistry_batch_index"):
            _numeric_var(ge, name, "i8", "element_row", [r[name] for r in e])
        _string_var(ge, "element", "element_row", [r["element"] for r in e])
        for name in ("mass_kg", "mass_fraction"):
            _numeric_var(ge, name, "f8", "element_row", [r[name] for r in e])

        p = tables["pb_isotopes"]
        gp = _make_group(gm, "pb_isotopes", "pb_isotope_row", len(p))
        for name in ("pb_isotope_row_index", "chemistry_batch_index"):
            _numeric_var(gp, name, "i8", "pb_isotope_row", [r[name] for r in p])
        _string_var(gp, "isotope", "pb_isotope_row", [r["isotope"] for r in p])
        _numeric_var(gp, "mass_kg", "f8", "pb_isotope_row", [r["mass_kg"] for r in p])

        sp = tables["source_pb"]
        gsp = _make_group(gm, "source_pb", "source_pb_row", len(sp))
        for name in ("source_pb_row_index", "chemistry_batch_index"):
            _numeric_var(gsp, name, "i8", "source_pb_row", [r[name] for r in sp])
        _string_var(gsp, "source_id", "source_pb_row", [r["source_id"] for r in sp])
        for name in ("pb_mass_kg", "fraction_of_pb"):
            _numeric_var(gsp, name, "f8", "source_pb_row", [r[name] for r in sp])

    return {
        "path": str(path),
        "phase": V3_METALLURGY_PHASE,
        "schema": V3_METALLURGY_SCHEMA,
        "model_version": metallurgy.SOURCE_METALLURGY_VERSION,
        "source_calibration_status": metallurgy.SOURCE_CALIBRATION_STATUS,
        "process_recipe_status": metallurgy.PROCESS_RECIPE_STATUS,
        "metallurgy_sha256": digest,
        "phase01_spine_sha256": str(phase01_spine_sha256),
        "phase02_biography_sha256": str(phase02_biography_sha256),
        "sources": len(source_rows),
        **{name: len(rows) for name, rows in tables.items()},
    }


def _strings(var: Any, *, none_if_empty: bool = False) -> list[Any]:
    values = var[:]
    out = []
    for value in values:
        text = value.decode("utf-8") if isinstance(value, bytes) else str(value)
        out.append(None if none_if_empty and text == "" else text)
    return out


def _numeric(group: Any, name: str) -> Any:
    return group.variables[name][:]


def _read_sources(group: Any) -> list[dict[str, Any]]:
    n = len(group.dimensions["source"])
    ids = _strings(group.variables["source_id"])
    labels = _strings(group.variables["label"])
    status = _strings(group.variables["calibration_status"])
    arrays = {name: _numeric(group, name) for name in SOURCE_FLOAT_FIELDS}
    rows = []
    for i in range(n):
        row = {
            "source_id": ids[i],
            "label": labels[i],
            "calibration_status": status[i],
        }
        row.update({name: float(values[i]) for name, values in arrays.items()})
        rows.append(row)
    return rows


def _read_batches(group: Any) -> list[dict[str, Any]]:
    n = len(group.dimensions["chemistry_batch"])
    idx = _numeric(group, "chemistry_batch_index")
    arrays = {name: _numeric(group, name) for name in BATCH_FLOAT_FIELDS}
    strings = {
        name: _strings(
            group.variables[name],
            none_if_empty=(name == "pb_dominant_source_id"),
        )
        for name in ("batch_id", "particle_id", "pb_dominant_source_id", "recipe_status")
    }
    rows = []
    for i in range(n):
        row = {"chemistry_batch_index": int(idx[i])}
        row.update({name: float(values[i]) for name, values in arrays.items()})
        row.update({name: values[i] for name, values in strings.items()})
        rows.append(row)
    return rows


def _read_elements(group: Any) -> list[dict[str, Any]]:
    n = len(group.dimensions["element_row"])
    ri = _numeric(group, "element_row_index")
    bi = _numeric(group, "chemistry_batch_index")
    element = _strings(group.variables["element"])
    mass = _numeric(group, "mass_kg")
    frac = _numeric(group, "mass_fraction")
    return [
        {
            "element_row_index": int(ri[i]),
            "chemistry_batch_index": int(bi[i]),
            "element": element[i],
            "mass_kg": float(mass[i]),
            "mass_fraction": float(frac[i]),
        }
        for i in range(n)
    ]


def _read_pb_isotopes(group: Any) -> list[dict[str, Any]]:
    n = len(group.dimensions["pb_isotope_row"])
    ri = _numeric(group, "pb_isotope_row_index")
    bi = _numeric(group, "chemistry_batch_index")
    isotope = _strings(group.variables["isotope"])
    mass = _numeric(group, "mass_kg")
    return [
        {
            "pb_isotope_row_index": int(ri[i]),
            "chemistry_batch_index": int(bi[i]),
            "isotope": isotope[i],
            "mass_kg": float(mass[i]),
        }
        for i in range(n)
    ]


def _read_source_pb(group: Any) -> list[dict[str, Any]]:
    n = len(group.dimensions["source_pb_row"])
    ri = _numeric(group, "source_pb_row_index")
    bi = _numeric(group, "chemistry_batch_index")
    source = _strings(group.variables["source_id"])
    mass = _numeric(group, "pb_mass_kg")
    frac = _numeric(group, "fraction_of_pb")
    return [
        {
            "source_pb_row_index": int(ri[i]),
            "chemistry_batch_index": int(bi[i]),
            "source_id": source[i],
            "pb_mass_kg": float(mass[i]),
            "fraction_of_pb": float(frac[i]),
        }
        for i in range(n)
    ]


def read_metallurgy(path: Path) -> dict[str, Any]:
    path = Path(path)
    with Dataset(path, "r") as ds:
        gm = ds.groups["metallurgy"]
        source_rows = _read_sources(ds.groups["sources"].groups["geochemistry"])
        tables = {
            "chemistry_batches": _read_batches(gm.groups["batches"]),
            "elements": _read_elements(gm.groups["elements"]),
            "pb_isotopes": _read_pb_isotopes(gm.groups["pb_isotopes"]),
            "source_pb": _read_source_pb(gm.groups["source_pb"]),
        }
        stored = str(ds.phase03_metallurgy_sha256)
        computed = metallurgy_hash(source_rows, tables)
        if stored != computed:
            raise RuntimeError(
                f"v3 phase-03 metallurgy hash mismatch: stored={stored} computed={computed}"
            )
        return {
            "phase": str(ds.latest_phase),
            "schema": str(ds.phase03_schema),
            "model_version": str(ds.phase03_model_version),
            "source_calibration_status": str(ds.phase03_source_calibration_status),
            "process_recipe_status": str(ds.phase03_process_recipe_status),
            "world_seed": int(ds.phase03_world_seed),
            "phase01_spine_sha256": str(ds.phase03_spine_sha256),
            "phase02_biography_sha256": str(ds.phase03_biography_sha256),
            "metallurgy_sha256": stored,
            "sources": source_rows,
            **tables,
        }
