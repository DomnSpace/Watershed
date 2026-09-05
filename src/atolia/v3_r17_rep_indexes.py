from __future__ import annotations

"""Add per-representative CSR pointers for sparse joint anchor tables."""

from pathlib import Path
from typing import Any

import numpy as np
from netCDF4 import Dataset


_TABLES = (
    ("element", "element_representative", "element_row"),
    ("source", "source_representative", "source_row"),
    ("pb_source", "pb_source_representative", "pb_source_row"),
    ("operation", "operation_representative", "operation_row"),
)


def append_sparse_indexes(runtime_path: Path, *, semantic_fingerprint: Any) -> dict[str, str]:
    runtime_path = Path(runtime_path)
    with Dataset(runtime_path, "r+") as ds:
        g = ds.groups["representatives"]
        total_rep = int(g.representative_count)
        if "representative_ptr_dim" not in g.dimensions:
            g.createDimension("representative_ptr_dim", total_rep + 1)
        for prefix, rep_var_name, _row_dim in _TABLES:
            name = f"{prefix}_ptr"
            if name in g.variables:
                raise RuntimeError(f"R17 representative sparse index already exists: {name}")
            rep_ids = np.asarray(g.variables[rep_var_name][:], dtype=np.int64)
            if rep_ids.size:
                if int(rep_ids.min()) < 0 or int(rep_ids.max()) >= total_rep:
                    raise RuntimeError(f"R17 {rep_var_name} contains out-of-range representative pointers")
                # Phase-08 writes each sparse table in representative order; retain
                # that property so a pointer slice is a direct NetCDF read.
                if np.any(rep_ids[1:] < rep_ids[:-1]):
                    raise RuntimeError(f"R17 {rep_var_name} is not representative-ordered")
                counts = np.bincount(rep_ids, minlength=total_rep)
            else:
                counts = np.zeros(total_rep, dtype=np.int64)
            ptr = np.zeros(total_rep + 1, dtype=np.int64)
            ptr[1:] = np.cumsum(counts, dtype=np.int64)
            var = g.createVariable(name, "i8", ("representative_ptr_dim",), zlib=True, complevel=6, shuffle=True)
            var[:] = ptr
            if int(ptr[-1]) != len(rep_ids):
                raise RuntimeError(f"R17 {name} does not close over its sparse table")
        g.sparse_index_policy = "per-representative CSR; direct slice reads; no global sparse scan at player startup"
        ds.runtime_fingerprint = semantic_fingerprint(ds)
        return {"runtime_fingerprint": str(ds.runtime_fingerprint)}
