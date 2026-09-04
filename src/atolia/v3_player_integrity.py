from __future__ import annotations

"""Deep structural and semantic integrity for private ``player_17.nc`` files."""

import hashlib
from pathlib import Path
from typing import Any

import numpy as np
from netCDF4 import Dataset

import v3_runtime_v3 as runtime_v3


REQUIRED_GROUPS = {
    "objects", "deposition", "biography_batches", "batch_ancestry", "batch_parents",
    "episodes", "events", "event_inputs", "chemistry", "elements", "pb_isotopes",
    "pb_sources", "operations", "operation_tools", "external_exchange",
}
ELEMENTS = {"Cu", "Sn", "As", "Pb", "Ag", "Fe", "Zn", "Sb", "Ni", "Co", "Bi"}
PB_ISOTOPES = {"Pb204", "Pb206", "Pb207", "Pb208"}


def _strings(var: Any) -> list[str]:
    values = var[:]
    return [x.decode("utf-8") if isinstance(x, bytes) else str(x) for x in values]


def _hash_variable(h: Any, var: Any) -> None:
    values = var[:]
    dtype = getattr(values, "dtype", None)
    kind = getattr(dtype, "kind", None)
    if kind in {"O", "U", "S"} or var.datatype == str:
        for text in _strings(var):
            raw = text.encode("utf-8")
            h.update(len(raw).to_bytes(4, "big")); h.update(raw)
        return
    arr = np.ma.getdata(np.asarray(values))
    if arr.dtype.kind == "f": arr = arr.astype(f">f{arr.dtype.itemsize}", copy=False)
    elif arr.dtype.kind == "i": arr = arr.astype(f">i{arr.dtype.itemsize}", copy=False)
    elif arr.dtype.kind == "u": arr = arr.astype(f">u{arr.dtype.itemsize}", copy=False)
    h.update(np.ascontiguousarray(arr).tobytes(order="C"))


def semantic_fingerprint(ds: Dataset) -> str:
    """Hash every hidden variable plus identity metadata, independent of HDF5 bytes."""
    h = hashlib.sha256()
    for attr in (
        "schema", "generator_version", "product_kind", "runtime_fingerprint", "world_build_id",
        "player_key_hash", "object_count", "levels", "objects_per_level", "canonical_hydro_realization_id",
    ):
        h.update(attr.encode()); h.update(b"\0"); h.update(str(getattr(ds, attr, "")).encode()); h.update(b"\0")
    for name in sorted(ds.dimensions):
        h.update(b"dim\0" + name.encode() + b"\0" + str(len(ds.dimensions[name])).encode() + b"\0")
    for group_name in sorted(ds.groups):
        group = ds.groups[group_name]
        h.update(b"group\0" + group_name.encode() + b"\0")
        for name in sorted(group.variables):
            var = group.variables[name]
            h.update(name.encode()); h.update(b"\0")
            h.update(str(var.dimensions).encode()); h.update(b"\0")
            _hash_variable(h, var)
    return h.hexdigest()


def _index_array(ds: Dataset, group: str, variable: str, upper: int) -> np.ndarray:
    arr = np.asarray(ds.groups[group].variables[variable][:], dtype=np.int64)
    if arr.size and (int(arr.min()) < 0 or int(arr.max()) >= int(upper)):
        raise ValueError(f"{group}/{variable} contains an out-of-range foreign key")
    return arr


def validate_structure(ds: Dataset) -> list[str]:
    if str(getattr(ds, "schema", "")) != runtime_v3.PLAYER_SCHEMA:
        raise ValueError("not a Dr. Corrosion player_17 NetCDF")
    if "object" not in ds.dimensions or len(ds.dimensions["object"]) != runtime_v3.TARGET_OBJECTS:
        raise ValueError("player_17.nc does not contain exactly 300 objects")
    missing = sorted(REQUIRED_GROUPS - set(ds.groups))
    if missing:
        raise ValueError("player_17.nc is missing hidden groups: " + ", ".join(missing))

    objects = ds.groups["objects"]
    ids = _strings(objects.variables["object_id"])
    if len(ids) != runtime_v3.TARGET_OBJECTS or len(set(ids)) != runtime_v3.TARGET_OBJECTS:
        raise ValueError("player_17.nc object identities are incomplete or duplicated")
    selection = np.asarray(objects.variables["selection_index"][:], dtype=np.int64)
    if not np.array_equal(selection, np.arange(runtime_v3.TARGET_OBJECTS, dtype=np.int64)):
        raise ValueError("player_17.nc selection order is not the canonical 0..299 sequence")

    batch_n = len(ds.dimensions["batch"]); chemistry_n = len(ds.dimensions["chemistry"])
    event_n = len(ds.dimensions["event"]); operation_n = len(ds.dimensions["operation"])
    for group, variable in (
        ("biography_batches", "object_index"), ("episodes", "object_index"), ("events", "object_index"),
        ("chemistry", "object_index"), ("operations", "object_index"), ("external_exchange", "object_index"),
    ):
        _index_array(ds, group, variable, runtime_v3.TARGET_OBJECTS)
    _index_array(ds, "batch_ancestry", "batch_row", batch_n)
    _index_array(ds, "batch_parents", "batch_row", batch_n)
    _index_array(ds, "event_inputs", "event_row", event_n)
    _index_array(ds, "elements", "chemistry_row", chemistry_n)
    _index_array(ds, "pb_isotopes", "chemistry_row", chemistry_n)
    _index_array(ds, "pb_sources", "chemistry_row", chemistry_n)
    _index_array(ds, "operation_tools", "operation_row", operation_n)

    batch_object = np.asarray(ds.groups["biography_batches"].variables["object_index"][:], dtype=np.int64)
    batch_tokens = _strings(ds.groups["biography_batches"].variables["batch_token"])
    final_rows = np.asarray(objects.variables["final_batch_row"][:], dtype=np.int64)
    if final_rows.size != runtime_v3.TARGET_OBJECTS or np.any(final_rows < 0) or np.any(final_rows >= batch_n):
        raise ValueError("one or more objects lack a valid final biography batch")
    for obj, row in enumerate(final_rows):
        if int(batch_object[int(row)]) != obj:
            raise ValueError(f"object {obj} final batch points to another object")

    chemistry_object = np.asarray(ds.groups["chemistry"].variables["object_index"][:], dtype=np.int64)
    chemistry_tokens = _strings(ds.groups["chemistry"].variables["batch_token"])
    chemistry_pairs = {(int(obj), token) for obj, token in zip(chemistry_object, chemistry_tokens)}
    if set(int(x) for x in chemistry_object) != set(range(runtime_v3.TARGET_OBJECTS)):
        raise ValueError("not every selected object has chemistry truth")
    for obj, row in enumerate(final_rows):
        if (obj, batch_tokens[int(row)]) not in chemistry_pairs:
            raise ValueError(f"object {obj} final batch lacks matching chemistry")

    ancestry_batch = np.asarray(ds.groups["batch_ancestry"].variables["batch_row"][:], dtype=np.int64)
    ancestry_fraction = np.asarray(ds.groups["batch_ancestry"].variables["fraction"][:], dtype=np.float64)
    if np.any(~np.isfinite(ancestry_fraction)) or np.any(ancestry_fraction < 0.0):
        raise ValueError("batch ancestry contains invalid source fractions")
    for row in range(batch_n):
        mask = ancestry_batch == row
        if np.any(mask):
            total = float(np.sum(ancestry_fraction[mask], dtype=np.float64))
            if abs(total - 1.0) > 2e-12:
                raise ValueError(f"batch {row} source ancestry does not close to one")

    element_rows = np.asarray(ds.groups["elements"].variables["chemistry_row"][:], dtype=np.int64)
    element_names = _strings(ds.groups["elements"].variables["element"])
    isotope_rows = np.asarray(ds.groups["pb_isotopes"].variables["chemistry_row"][:], dtype=np.int64)
    isotope_names = _strings(ds.groups["pb_isotopes"].variables["isotope"])
    for row in range(chemistry_n):
        found_elements = {name for idx, name in zip(element_rows, element_names) if int(idx) == row}
        if found_elements != ELEMENTS:
            raise ValueError(f"chemistry row {row} has incomplete element basis")
        found_isotopes = {name for idx, name in zip(isotope_rows, isotope_names) if int(idx) == row}
        if found_isotopes != PB_ISOTOPES:
            raise ValueError(f"chemistry row {row} has incomplete Pb isotope basis")

    known_batches = set(batch_tokens)
    for token in _strings(ds.groups["batch_parents"].variables["parent_batch_token"]):
        if token not in known_batches:
            raise ValueError("batch parent reference points outside player_17.nc")
    for token in _strings(ds.groups["event_inputs"].variables["batch_token"]):
        if token not in known_batches:
            raise ValueError("event input references an unknown batch")

    dep = np.asarray(ds.groups["deposition"].variables["mode_weight"][:], dtype=np.float64)
    if dep.shape[0] != runtime_v3.TARGET_OBJECTS or np.any(~np.isfinite(dep)) or np.any(dep < 0.0):
        raise ValueError("deposition probability field is malformed")
    sums = np.sum(dep, axis=1, dtype=np.float64)
    if np.any(np.abs(sums - 1.0) > 2e-12):
        raise ValueError("deposition probability rows do not close to one")
    return ids


def finalize_player_netcdf(path: Path) -> dict[str, Any]:
    path = Path(path)
    with Dataset(path, "r+") as ds:
        ids = validate_structure(ds)
        fingerprint = semantic_fingerprint(ds)
        ds.player_state_fingerprint = fingerprint
    return validate_player_netcdf(path)


def validate_player_netcdf(path: Path) -> dict[str, Any]:
    path = Path(path)
    with Dataset(path, "r") as ds:
        ids = validate_structure(ds)
        expected = str(getattr(ds, "player_state_fingerprint", ""))
        actual = semantic_fingerprint(ds)
        if not expected or expected != actual:
            raise ValueError("player_17.nc full semantic fingerprint mismatch")
        return {
            "schema": str(ds.schema),
            "generator_version": str(ds.generator_version),
            "runtime_fingerprint": str(ds.runtime_fingerprint),
            "world_build_id": str(ds.world_build_id),
            "player_key_hash": str(ds.player_key_hash),
            "player_state_fingerprint": actual,
            "object_count": len(ids),
            "object_ids": ids,
        }
