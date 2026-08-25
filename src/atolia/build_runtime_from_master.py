#!/usr/bin/env python3
from __future__ import annotations

"""Build the compact Atolia installer/runtime NetCDF from a completed master.

This recovery/post-processing command deliberately does *not* read the giant
JSON substrate and does *not* rerun the 3,200-workshop / 28-step circulation
model.  It is safe to use after a failure in the master->runtime copy stage.

The initial ECMWF converter attempted to apply HDF5 filters to NetCDF4 VLEN
string coordinate variables such as ``bundle_name``.  NetCDF4 rejects that.
This copier recognizes string variables explicitly and creates them without
compression filters while still chunking/compressing numeric arrays.
"""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from netCDF4 import Dataset


MASTER_SCHEMA = "atolia.ecmwf-master.v1"
RUNTIME_SCHEMA = "atolia.ecmwf-runtime.v1"
DEFAULT_MASTER = Path("cache/atolia_master_v1.nc")
DEFAULT_RUNTIME = Path("cache/atolia_runtime_v1.nc")
DEFAULT_CHUNK = 131_072


def sha256_file(path: Path, block_size: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(block_size)
            if not block:
                return h.hexdigest()
            h.update(block)


def _is_string_variable(var: Any, name: str) -> bool:
    """Return True for NetCDF4 VLEN/fixed string coordinates across versions."""
    # All semantic vocabulary variables created by the master writer use this
    # naming convention.  Keep this explicit fallback because netCDF4 releases
    # have exposed VLEN strings through slightly different dtype/datatype forms.
    if name.endswith("_name"):
        return True

    datatype = getattr(var, "datatype", None)
    dtype = getattr(var, "dtype", None)
    if datatype == str or dtype == str:
        return True
    if isinstance(datatype, type):
        try:
            if issubclass(datatype, str):
                return True
        except TypeError:
            pass
    kind = getattr(dtype, "kind", None)
    return kind in {"U", "S", "O"}


def validate_master(src: Dataset) -> dict[str, int]:
    schema = str(getattr(src, "schema", ""))
    if schema != MASTER_SCHEMA:
        raise ValueError(f"not an Atolia ECMWF master: schema={schema!r}")

    expected = {
        "state": int(getattr(src, "state_count", -1)),
        "profile": int(getattr(src, "profile_count", -1)),
        "production_cell": int(getattr(src, "production_cell_count", -1)),
    }
    for dim_name, attr_count in expected.items():
        if dim_name not in src.dimensions:
            raise ValueError(f"master missing required dimension: {dim_name}")
        dim_count = len(src.dimensions[dim_name])
        if attr_count < 0:
            raise ValueError(f"master missing completion attribute for {dim_name}")
        if dim_count != attr_count:
            raise ValueError(
                f"master incomplete for {dim_name}: dimension={dim_count:,} "
                f"completion_attribute={attr_count:,}"
            )

    required_vars = {
        "profile_cell",
        "profile_node",
        "profile_loss_intensity",
        "profile_archaeological_intensity",
        "site_ptr",
        "site_profile_index",
        "class_ptr",
        "class_profile_index",
        "bundle_ptr",
        "bundle_profile_index",
        "cell_source_ptr",
        "cell_source_id",
        "cell_source_weight",
    }
    missing = sorted(required_vars - set(src.variables))
    if missing:
        raise ValueError(f"master missing runtime pointer/field variables: {missing}")
    return expected


def _copy_variable(
    src: Dataset,
    dst: Dataset,
    name: str,
    *,
    chunk_rows: int,
) -> None:
    sv = src.variables[name]
    is_string = _is_string_variable(sv, name)

    create_kwargs: dict[str, Any] = {}
    fill_value: Any = None
    has_fill = "_FillValue" in sv.ncattrs()
    if has_fill:
        fill_value = sv.getncattr("_FillValue")

    if is_string:
        # VLEN UTF-8 strings cannot use the numeric HDF5 filter configuration.
        dtype: Any = str
    else:
        dtype = sv.datatype
        if sv.dimensions:
            shape = tuple(len(src.dimensions[d]) for d in sv.dimensions)
            if all(n > 0 for n in shape):
                chunks = tuple(
                    max(1, min(int(n), chunk_rows if i == 0 else int(n)))
                    for i, n in enumerate(shape)
                )
                create_kwargs.update(
                    zlib=True,
                    complevel=4,
                    shuffle=True,
                    chunksizes=chunks,
                )

    if has_fill:
        create_kwargs["fill_value"] = fill_value
    dv = dst.createVariable(name, dtype, sv.dimensions, **create_kwargs)

    # _FillValue is immutable after variable creation and was handled above.
    for attr in sv.ncattrs():
        if attr == "_FillValue":
            continue
        dv.setncattr(attr, sv.getncattr(attr))

    if sv.ndim == 0:
        dv.assignValue(sv.getValue())
        return

    n0 = sv.shape[0]
    if n0 == 0:
        return

    if sv.ndim == 1:
        slab = chunk_rows
    else:
        # Keep two-dimensional profile/deposition arrays comfortably bounded.
        slab = max(4096, chunk_rows // 8)

    for a in range(0, n0, slab):
        z = min(n0, a + slab)
        if sv.ndim == 1:
            dv[a:z] = sv[a:z]
        else:
            dv[a:z, ...] = sv[a:z, ...]


def build_runtime(
    master_path: Path = DEFAULT_MASTER,
    runtime_path: Path = DEFAULT_RUNTIME,
    *,
    chunk_rows: int = DEFAULT_CHUNK,
) -> dict[str, Any]:
    master_path = Path(master_path)
    runtime_path = Path(runtime_path)
    if not master_path.exists():
        raise FileNotFoundError(master_path)

    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    master_hash = sha256_file(master_path)

    with Dataset(master_path, "r") as src:
        counts = validate_master(src)
        keep_vars = [
            name
            for name, var in src.variables.items()
            if not name.startswith("state_") and "state" not in var.dimensions
        ]
        needed_dims: set[str] = set()
        for name in keep_vars:
            needed_dims.update(src.variables[name].dimensions)

        print(
            "validated master: "
            f"{counts['state']:,} exact states, "
            f"{counts['profile']:,} runtime profiles, "
            f"{counts['production_cell']:,} production cells",
            flush=True,
        )
        print(f"copying {len(keep_vars)} runtime variables ...", flush=True)

        # "w" intentionally replaces a partial runtime left by a failed copy.
        with Dataset(runtime_path, "w", format="NETCDF4") as dst:
            for attr in src.ncattrs():
                # These two describe the developer master, not the product being
                # written.  The source counts remain available below explicitly.
                if attr in {"schema", "product_kind", "master_sha256"}:
                    continue
                dst.setncattr(attr, src.getncattr(attr))
            dst.schema = RUNTIME_SCHEMA
            dst.product_kind = "installer_runtime"
            dst.master_sha256 = master_hash
            dst.master_state_count = counts["state"]
            dst.runtime_profile_count = counts["profile"]
            dst.production_cell_count = counts["production_cell"]

            for dim_name in sorted(needed_dims):
                dst.createDimension(dim_name, len(src.dimensions[dim_name]))

            for i, name in enumerate(keep_vars, start=1):
                _copy_variable(src, dst, name, chunk_rows=chunk_rows)
                if i % 10 == 0 or i == len(keep_vars):
                    print(f"  copied {i}/{len(keep_vars)} variables", flush=True)

    report = {
        "schema": RUNTIME_SCHEMA,
        "master": str(master_path),
        "master_bytes": master_path.stat().st_size,
        "master_sha256": master_hash,
        "runtime": str(runtime_path),
        "runtime_bytes": runtime_path.stat().st_size,
        "runtime_sha256": sha256_file(runtime_path),
        "exact_master_states": counts["state"],
        "runtime_profiles": counts["profile"],
        "production_cells": counts["production_cell"],
    }
    return report


def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Build only the compact Atolia runtime NetCDF from an already "
            "completed ECMWF master; never rereads the giant JSON."
        )
    )
    ap.add_argument("--master", type=Path, default=DEFAULT_MASTER)
    ap.add_argument("--runtime", type=Path, default=DEFAULT_RUNTIME)
    ap.add_argument("--chunk-rows", type=int, default=DEFAULT_CHUNK)
    args = ap.parse_args()
    report = build_runtime(args.master, args.runtime, chunk_rows=max(4096, args.chunk_rows))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
