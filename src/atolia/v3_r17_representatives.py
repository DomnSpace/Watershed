from __future__ import annotations

"""Pack/read Phase-08 joint empirical representatives inside final R17.

The 580 compact fragments are build-only inputs.  This module copies their
small retained joint representatives into one NetCDF group so player creation can
select a concrete conditioned latent state directly from R17 without replaying
Phase-01 or shipping JSON fragments.
"""

from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from netCDF4 import Dataset

import v3_phase08_runtime_fragment as phase08


NUMERIC_FIELDS = (
    "metal_mass_kg",
    "ore_distance_km",
    "cumulative_metal_distance_km",
    "current_object_distance_km",
    "source_entropy",
    "remelt_count",
    "repair_count",
    "Pb206_204",
    "Pb207_204",
    "Pb208_204",
    "hydro_context_score",
    "p_survival",
    "p_discovery",
    "p_record",
)


def _strings(var: Any) -> list[str]:
    values = var[:]
    return [x.decode("utf-8") if isinstance(x, bytes) else str(x) for x in values]


def _strvar(group: Any, name: str, dim: str, values: list[str]) -> None:
    var = group.createVariable(name, str, (dim,))
    if values:
        var[:] = np.asarray(values, dtype=object)


def _numvar(group: Any, name: str, dtype: str, dims: tuple[str, ...], values: Any) -> None:
    var = group.createVariable(name, dtype, dims, zlib=True, complevel=6, shuffle=True)
    arr = np.asarray(values)
    if arr.size:
        var[:] = arr


def _profile_lookup(ds: Dataset) -> dict[tuple[int, str], int]:
    gp = ds.groups["profiles"]
    node_ids = _strings(ds.groups["world_nodes"].variables["node_id"])
    world_build_id = str(ds.world_build_id)
    cells = np.asarray(gp.variables["cell_index"][:], dtype=np.int64)
    nodes = np.asarray(gp.variables["node_index"][:], dtype=np.int64)
    out: dict[tuple[int, str], int] = {}
    for p, (cell, node_idx) in enumerate(zip(cells, nodes)):
        token = phase08.anonymous_token(world_build_id, "node", node_ids[int(node_idx)])
        key = (int(cell), token)
        if key in out:
            raise RuntimeError(f"R17 profile key is not unique: {key}")
        out[key] = int(p)
    return out


def append_representatives(
    runtime_path: Path,
    fragments_dir: Path,
    *,
    read_fragment: Any,
    semantic_fingerprint: Any,
) -> dict[str, int | str]:
    """Append all retained joint representatives to an already-built R17.

    The operation is deterministic and self-contained: all fragment-local
    dictionaries and indexes are translated to one global R17 coordinate system.
    """
    runtime_path = Path(runtime_path)
    fragments_dir = Path(fragments_dir)
    paths = sorted(fragments_dir.rglob("compact-*.json.gz"), key=lambda p: int(p.name.removeprefix("compact-").removesuffix(".json.gz")))
    if not paths:
        raise RuntimeError("cannot pack R17 representatives without Phase-08 compact fragments")

    # Pass 1: counts and small global dictionaries only.
    total_rep = total_el = total_src = total_pb = total_op = 0
    mode_names: set[str] = set()
    element_names: set[str] = set()
    operation_names: set[str] = set()
    for path in paths:
        fragment = read_fragment(path)
        total_rep += len(fragment["representatives"])
        total_el += len(fragment["representative_elements"])
        total_src += len(fragment["representative_sources"])
        total_pb += len(fragment["representative_pb_sources"])
        total_op += len(fragment["representative_operations"])
        d = fragment["dictionary"]
        mode_names.update(str(x) for x in d.get("mode", ()))
        element_names.update(str(x) for x in d.get("element", ()))
        operation_names.update(str(x) for x in d.get("operation_type", ()))

    modes = sorted(mode_names)
    elements = sorted(element_names)
    operations = sorted(operation_names)
    mode_index = {name: i for i, name in enumerate(modes)}
    element_index = {name: i for i, name in enumerate(elements)}
    operation_index = {name: i for i, name in enumerate(operations)}

    with Dataset(runtime_path, "r+") as ds:
        if "representatives" in ds.groups:
            raise RuntimeError("R17 already contains representative group; rebuild from a clean output")
        lookup = _profile_lookup(ds)
        profile_count = int(ds.groups["profiles"].profile_count)
        world_build_id = str(ds.world_build_id)
        source_ids = _strings(ds.groups["world_sources"].variables["source_id"])
        source_token_to_index = {
            phase08.anonymous_token(world_build_id, "source", source_id): i
            for i, source_id in enumerate(source_ids)
        }

        g = ds.createGroup("representatives")
        g.createDimension("representative", total_rep)
        g.createDimension("profile_ptr_dim", profile_count + 1)
        g.createDimension("mode", len(modes))
        g.createDimension("element", len(elements))
        g.createDimension("operation_type", len(operations))
        g.createDimension("element_row", total_el)
        g.createDimension("source_row", total_src)
        g.createDimension("pb_source_row", total_pb)
        g.createDimension("operation_row", total_op)
        _strvar(g, "mode_name", "mode", modes)
        _strvar(g, "element_name", "element", elements)
        _strvar(g, "operation_type_name", "operation_type", operations)

        rep_profile = g.createVariable("profile_index", "i4", ("representative",), zlib=True, complevel=6, shuffle=True)
        rep_rank = g.createVariable("profile_rank", "i1", ("representative",), zlib=True, complevel=6, shuffle=True)
        rep_mass = g.createVariable("representative_recorded_mass", "f8", ("representative",), zlib=True, complevel=6, shuffle=True)
        rep_source_repr = g.createVariable("source_represented_weight", "f8", ("representative",), zlib=True, complevel=6, shuffle=True)
        rep_source_record = g.createVariable("source_recorded_weight", "f8", ("representative",), zlib=True, complevel=6, shuffle=True)
        rep_mode = g.createVariable("mode_index", "i2", ("representative",), zlib=True, complevel=6, shuffle=True)
        rep_numeric = {
            name: g.createVariable(name, "f8", ("representative",), zlib=True, complevel=6, shuffle=True)
            for name in NUMERIC_FIELDS
        }

        el_rep = g.createVariable("element_representative", "i4", ("element_row",), zlib=True, complevel=6, shuffle=True)
        el_name = g.createVariable("element_index", "i2", ("element_row",), zlib=True, complevel=6, shuffle=True)
        el_value = g.createVariable("element_mass_fraction", "f8", ("element_row",), zlib=True, complevel=6, shuffle=True)
        src_rep = g.createVariable("source_representative", "i4", ("source_row",), zlib=True, complevel=6, shuffle=True)
        src_name = g.createVariable("source_index", "i4", ("source_row",), zlib=True, complevel=6, shuffle=True)
        src_value = g.createVariable("source_fraction", "f8", ("source_row",), zlib=True, complevel=6, shuffle=True)
        pb_rep = g.createVariable("pb_source_representative", "i4", ("pb_source_row",), zlib=True, complevel=6, shuffle=True)
        pb_name = g.createVariable("pb_source_index", "i4", ("pb_source_row",), zlib=True, complevel=6, shuffle=True)
        pb_value = g.createVariable("pb_source_fraction", "f8", ("pb_source_row",), zlib=True, complevel=6, shuffle=True)
        op_rep = g.createVariable("operation_representative", "i4", ("operation_row",), zlib=True, complevel=6, shuffle=True)
        op_name = g.createVariable("operation_type_index", "i2", ("operation_row",), zlib=True, complevel=6, shuffle=True)
        op_count = g.createVariable("operation_count", "i2", ("operation_row",), zlib=True, complevel=6, shuffle=True)

        profile_counts = np.zeros(profile_count, dtype=np.int64)
        rep_cursor = el_cursor = src_cursor = pb_cursor = op_cursor = 0

        for path in paths:
            fragment = read_fragment(path)
            start = int(fragment["global_cell_start"])
            d = fragment["dictionary"]
            pcols = {name: i for i, name in enumerate(fragment["columns"]["profile"])}
            rcols = {name: i for i, name in enumerate(fragment["columns"]["representative"])}
            local_profile_to_global: list[int] = []
            for prow in fragment["profiles"]:
                local_cell = int(prow[pcols["cell"]])
                node_token = str(d["node"][int(prow[pcols["loss_node"]])])
                key = (start + local_cell, node_token)
                global_profile = lookup.get(key)
                if global_profile is None:
                    raise RuntimeError(f"Phase-08 representative profile does not resolve in R17: {key}")
                local_profile_to_global.append(global_profile)

            local_rep_to_global: list[int] = []
            ranks: dict[int, int] = defaultdict(int)
            reps = fragment["representatives"]
            n = len(reps)
            if n:
                sl = slice(rep_cursor, rep_cursor + n)
                out_profile = np.empty(n, dtype=np.int32)
                out_rank = np.empty(n, dtype=np.int8)
                out_mass = np.empty(n, dtype=np.float64)
                out_source_repr = np.empty(n, dtype=np.float64)
                out_source_record = np.empty(n, dtype=np.float64)
                out_mode = np.empty(n, dtype=np.int16)
                out_numeric = {name: np.empty(n, dtype=np.float64) for name in NUMERIC_FIELDS}
                for j, row in enumerate(reps):
                    lp = int(row[rcols["profile"]])
                    if lp < 0 or lp >= len(local_profile_to_global):
                        raise RuntimeError(f"representative profile index outside fragment: {lp}")
                    gpidx = local_profile_to_global[lp]
                    rank = ranks[gpidx]
                    ranks[gpidx] += 1
                    global_rep = rep_cursor + j
                    local_rep_to_global.append(global_rep)
                    out_profile[j] = gpidx
                    out_rank[j] = rank
                    out_mass[j] = float(row[rcols["representative_recorded_mass"]])
                    out_source_repr[j] = float(row[rcols["source_represented_weight"]])
                    out_source_record[j] = float(row[rcols["source_recorded_weight"]])
                    mode = str(d["mode"][int(row[rcols["mode"]])])
                    out_mode[j] = mode_index[mode]
                    for name in NUMERIC_FIELDS:
                        out_numeric[name][j] = float(row[rcols[name]])
                    profile_counts[gpidx] += 1
                rep_profile[sl] = out_profile
                rep_rank[sl] = out_rank
                rep_mass[sl] = out_mass
                rep_source_repr[sl] = out_source_repr
                rep_source_record[sl] = out_source_record
                rep_mode[sl] = out_mode
                for name in NUMERIC_FIELDS:
                    rep_numeric[name][sl] = out_numeric[name]
                rep_cursor += n

            def _write_sparse(rows: list[list[Any]], columns_name: str, cursor: int, rep_var: Any, name_var: Any, value_var: Any, dictionary_name: str, global_index: dict[str, int] | None, value_field: str, count_value: bool = False) -> int:
                if not rows:
                    return cursor
                cols = {name: i for i, name in enumerate(fragment["columns"][columns_name])}
                m = len(rows)
                rarr = np.empty(m, dtype=np.int32)
                narr = np.empty(m, dtype=np.int32 if dictionary_name == "source" else np.int16)
                varr = np.empty(m, dtype=np.int16 if count_value else np.float64)
                for j, row in enumerate(rows):
                    lr = int(row[cols["representative"]])
                    if lr < 0 or lr >= len(local_rep_to_global):
                        raise RuntimeError(f"sparse representative index outside fragment: {lr}")
                    rarr[j] = local_rep_to_global[lr]
                    raw_name = str(d[dictionary_name][int(row[cols[dictionary_name if dictionary_name != 'operation_type' else 'operation_type']])])
                    if dictionary_name == "source":
                        idx = source_token_to_index.get(raw_name)
                        if idx is None:
                            raise RuntimeError(f"representative source token does not resolve in R17: {raw_name}")
                        narr[j] = idx
                    else:
                        assert global_index is not None
                        narr[j] = global_index[raw_name]
                    varr[j] = int(row[cols[value_field]]) if count_value else float(row[cols[value_field]])
                sl = slice(cursor, cursor + m)
                rep_var[sl] = rarr
                name_var[sl] = narr
                value_var[sl] = varr
                return cursor + m

            el_cursor = _write_sparse(fragment["representative_elements"], "representative_element", el_cursor, el_rep, el_name, el_value, "element", element_index, "mass_fraction")
            src_cursor = _write_sparse(fragment["representative_sources"], "representative_source", src_cursor, src_rep, src_name, src_value, "source", None, "fraction")
            pb_cursor = _write_sparse(fragment["representative_pb_sources"], "representative_pb_source", pb_cursor, pb_rep, pb_name, pb_value, "source", None, "fraction_of_pb")
            op_cursor = _write_sparse(fragment["representative_operations"], "representative_operation", op_cursor, op_rep, op_name, op_count, "operation_type", operation_index, "count", count_value=True)

        if rep_cursor != total_rep or el_cursor != total_el or src_cursor != total_src or pb_cursor != total_pb or op_cursor != total_op:
            raise RuntimeError("R17 representative packing row counts changed during write")
        if np.any(profile_counts <= 0) or np.any(profile_counts > 2):
            bad = np.where((profile_counts <= 0) | (profile_counts > 2))[0]
            raise RuntimeError(f"R17 representative multiplicity invalid for {len(bad)} profiles; first={bad[:8].tolist()}")
        profile_ptr = np.zeros(profile_count + 1, dtype=np.int64)
        profile_ptr[1:] = np.cumsum(profile_counts, dtype=np.int64)
        _numvar(g, "profile_ptr", "i8", ("profile_ptr_dim",), profile_ptr)
        g.source = "phase08-joint-empirical-representatives-packed-directly-into-r17"
        g.conditioning_policy = "player-key-selects-profile-then-retained-joint-representative;phase01-not-replayed"
        g.representative_count = int(total_rep)
        g.profile_count = int(profile_count)

        # The new group is authoritative and must participate in the R17 semantic digest.
        ds.runtime_fingerprint = semantic_fingerprint(ds)
        fingerprint = str(ds.runtime_fingerprint)

    return {
        "representatives": int(total_rep),
        "representative_elements": int(total_el),
        "representative_sources": int(total_src),
        "representative_pb_sources": int(total_pb),
        "representative_operations": int(total_op),
        "runtime_fingerprint": fingerprint,
    }
