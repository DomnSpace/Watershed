from __future__ import annotations

"""NetCDF append/read support for Atolia v3 phase-02 metal biographies."""

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from netCDF4 import Dataset

import v3_metal_biography as biography


V3_BIOGRAPHY_SCHEMA = "atolia-v3-metal-biography-v1"
V3_BIOGRAPHY_PHASE = "atolia-v3-02-metal-biography"


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


def biography_hash(tables: Mapping[str, Sequence[Mapping[str, Any]]]) -> str:
    payload = {
        name: [_plain(dict(row)) for row in tables[name]]
        for name in ("particles", "batches", "ancestry", "parents", "episodes", "events")
    }
    return hashlib.sha256(stable_json(payload).encode("utf-8")).hexdigest()


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
        name,
        dtype,
        (dim,),
        zlib=True,
        complevel=4,
        shuffle=True,
    )
    if values:
        var[:] = np.asarray(list(values))


def _make_group(parent: Any, name: str, dim_name: str, count: int) -> Any:
    group = parent.createGroup(name)
    group.createDimension(dim_name, int(count))
    return group


def append_biography(
    path: Path,
    *,
    lineages: Sequence[biography.MetalLineage],
    world_seed: int,
    phase01_spine_sha256: str,
) -> dict[str, Any]:
    path = Path(path)
    tables = biography.flatten_lineages(lineages)
    digest = biography_hash(tables)

    with Dataset(path, "a") as ds:
        collisions = {"particles", "metal", "objects", "events"}.intersection(ds.groups)
        if collisions:
            raise RuntimeError(
                "phase-02 groups already exist: " + ", ".join(sorted(collisions))
            )

        ds.latest_phase = V3_BIOGRAPHY_PHASE
        ds.phase02_schema = V3_BIOGRAPHY_SCHEMA
        ds.phase02_model_version = biography.BIOGRAPHY_MODEL_VERSION
        ds.phase02_mixing_assumption = biography.MIXING_ASSUMPTION
        ds.phase02_world_seed = int(world_seed)
        ds.phase02_spine_sha256 = str(phase01_spine_sha256)
        ds.phase02_biography_sha256 = digest
        ds.phase02_representation = (
            "one deterministic weighted conditional lineage per positive v1 loss stratum"
        )

        p = tables["particles"]
        gp = _make_group(ds, "particles", "particle", len(p))
        for name in (
            "particle_index",
            "production_cell_index",
            "cell_loss_index",
            "date_bc",
            "loss_step",
            "final_batch_index",
            "final_episode_index",
            "remelt_count",
            "repair_count",
        ):
            _numeric_var(gp, name, "i8", "particle", [r[name] for r in p])
        for name in (
            "represented_weight",
            "metal_mass_kg",
            "ore_distance_km",
            "cumulative_metal_distance_km",
            "current_object_distance_km",
            "source_entropy",
        ):
            _numeric_var(gp, name, "f8", "particle", [r[name] for r in p])
        for name in (
            "particle_id",
            "production_cell_id",
            "loss_site_id",
            "bundle_id",
            "object_class",
            "loss_node_id",
            "metal_batch_id",
            "object_episode_id",
        ):
            _string_var(gp, name, "particle", [r[name] for r in p])

        gm = ds.createGroup("metal")

        b = tables["batches"]
        gb = _make_group(gm, "batches", "batch", len(b))
        for name in (
            "batch_index",
            "particle_index",
            "date_bc",
            "recycle_generation",
        ):
            _numeric_var(gb, name, "i8", "batch", [r[name] for r in b])
        for name in (
            "metal_mass_kg",
            "route_position_km",
            "retained_mass_fraction",
        ):
            _numeric_var(gb, name, "f8", "batch", [r[name] for r in b])
        for name in ("batch_id", "role", "node_id"):
            _string_var(gb, name, "batch", [r[name] for r in b])

        a = tables["ancestry"]
        ga = _make_group(gm, "ancestry", "ancestry", len(a))
        for name in ("ancestry_index", "batch_index"):
            _numeric_var(ga, name, "i8", "ancestry", [r[name] for r in a])
        for name in ("mass_kg", "fraction"):
            _numeric_var(ga, name, "f8", "ancestry", [r[name] for r in a])
        _string_var(ga, "source_id", "ancestry", [r["source_id"] for r in a])

        pr = tables["parents"]
        gpr = _make_group(gm, "parents", "parent_link", len(pr))
        for name in (
            "parent_link_index",
            "child_batch_index",
            "parent_batch_index",
        ):
            _numeric_var(gpr, name, "i8", "parent_link", [r[name] for r in pr])
        for name in ("contribution_kg", "fraction_of_child"):
            _numeric_var(gpr, name, "f8", "parent_link", [r[name] for r in pr])

        o = tables["episodes"]
        go = _make_group(ds, "objects", "episode", len(o))
        for name in (
            "episode_index",
            "particle_index",
            "batch_index",
            "life_index",
        ):
            _numeric_var(go, name, "i8", "episode", [r[name] for r in o])
        for name in ("start_position_km", "end_position_km"):
            _numeric_var(go, name, "f8", "episode", [r[name] for r in o])
        for name in (
            "episode_id",
            "object_class",
            "start_node_id",
            "end_node_id",
            "end_event_kind",
        ):
            _string_var(go, name, "episode", [r[name] for r in o])

        e = tables["events"]
        ge = _make_group(ds, "events", "event", len(e))
        for name in (
            "event_index",
            "particle_index",
            "ordinal",
            "episode_index",
            "output_batch_index",
        ):
            _numeric_var(ge, name, "i8", "event", [r[name] for r in e])
        _numeric_var(
            ge,
            "route_position_km",
            "f8",
            "event",
            [r["route_position_km"] for r in e],
        )
        _numeric_var(
            ge,
            "retained_mass_fraction",
            "f8",
            "event",
            [
                np.nan if r["retained_mass_fraction"] is None
                else r["retained_mass_fraction"]
                for r in e
            ],
        )
        for name in ("event_id", "kind", "node_id"):
            _string_var(ge, name, "event", [r[name] for r in e])
        _string_var(
            ge,
            "input_batch_indices_json",
            "event",
            [stable_json(r["input_batch_indices"]) for r in e],
        )

    return {
        "path": str(path),
        "phase": V3_BIOGRAPHY_PHASE,
        "schema": V3_BIOGRAPHY_SCHEMA,
        "model_version": biography.BIOGRAPHY_MODEL_VERSION,
        "biography_sha256": digest,
        "phase01_spine_sha256": str(phase01_spine_sha256),
        **{name: len(rows) for name, rows in tables.items()},
    }


def _strings(var: Any, *, none_if_empty: bool = False) -> list[Any]:
    out: list[Any] = []
    for value in var[:]:
        if isinstance(value, bytes):
            text = value.decode("utf-8")
        else:
            text = str(value)
        out.append(None if none_if_empty and text == "" else text)
    return out


def _numeric(group: Any, name: str) -> Any:
    return group.variables[name][:]


def _read_particles(group: Any) -> list[dict[str, Any]]:
    n = len(group.dimensions["particle"])
    arrays = {name: _numeric(group, name) for name in (
        "particle_index", "production_cell_index", "cell_loss_index", "date_bc",
        "loss_step", "final_batch_index", "final_episode_index", "remelt_count",
        "repair_count", "represented_weight", "metal_mass_kg", "ore_distance_km",
        "cumulative_metal_distance_km", "current_object_distance_km", "source_entropy",
    )}
    strings = {name: _strings(group.variables[name]) for name in (
        "particle_id", "production_cell_id", "loss_site_id", "bundle_id",
        "object_class", "loss_node_id", "metal_batch_id", "object_episode_id"
    )}
    int_names = {
        "particle_index", "production_cell_index", "cell_loss_index", "date_bc",
        "loss_step", "final_batch_index", "final_episode_index", "remelt_count",
        "repair_count",
    }
    rows = []
    for i in range(n):
        row = {name: int(arrays[name][i]) for name in int_names}
        for name in arrays:
            if name not in int_names:
                row[name] = float(arrays[name][i])
        for name in strings:
            row[name] = strings[name][i]
        rows.append(row)
    return rows


def _read_batches(group: Any) -> list[dict[str, Any]]:
    n = len(group.dimensions["batch"])
    ints = {name: _numeric(group, name) for name in (
        "batch_index", "particle_index", "date_bc", "recycle_generation"
    )}
    floats = {name: _numeric(group, name) for name in (
        "metal_mass_kg", "route_position_km", "retained_mass_fraction"
    )}
    strings = {
        "batch_id": _strings(group.variables["batch_id"]),
        "role": _strings(group.variables["role"]),
        "node_id": _strings(group.variables["node_id"], none_if_empty=True),
    }
    rows = []
    for i in range(n):
        row = {name: int(values[i]) for name, values in ints.items()}
        row.update({name: float(values[i]) for name, values in floats.items()})
        row.update({name: values[i] for name, values in strings.items()})
        rows.append(row)
    return rows


def _read_ancestry(group: Any) -> list[dict[str, Any]]:
    n = len(group.dimensions["ancestry"])
    ai = _numeric(group, "ancestry_index")
    bi = _numeric(group, "batch_index")
    mass = _numeric(group, "mass_kg")
    frac = _numeric(group, "fraction")
    source = _strings(group.variables["source_id"])
    return [{
        "ancestry_index": int(ai[i]),
        "batch_index": int(bi[i]),
        "source_id": source[i],
        "mass_kg": float(mass[i]),
        "fraction": float(frac[i]),
    } for i in range(n)]


def _read_parents(group: Any) -> list[dict[str, Any]]:
    n = len(group.dimensions["parent_link"])
    li = _numeric(group, "parent_link_index")
    child = _numeric(group, "child_batch_index")
    parent = _numeric(group, "parent_batch_index")
    mass = _numeric(group, "contribution_kg")
    frac = _numeric(group, "fraction_of_child")
    return [{
        "parent_link_index": int(li[i]),
        "child_batch_index": int(child[i]),
        "parent_batch_index": int(parent[i]),
        "contribution_kg": float(mass[i]),
        "fraction_of_child": float(frac[i]),
    } for i in range(n)]


def _read_episodes(group: Any) -> list[dict[str, Any]]:
    n = len(group.dimensions["episode"])
    ints = {name: _numeric(group, name) for name in (
        "episode_index", "particle_index", "batch_index", "life_index"
    )}
    floats = {name: _numeric(group, name) for name in (
        "start_position_km", "end_position_km"
    )}
    strings = {
        "episode_id": _strings(group.variables["episode_id"]),
        "object_class": _strings(group.variables["object_class"]),
        "start_node_id": _strings(group.variables["start_node_id"], none_if_empty=True),
        "end_node_id": _strings(group.variables["end_node_id"], none_if_empty=True),
        "end_event_kind": _strings(group.variables["end_event_kind"]),
    }
    rows = []
    for i in range(n):
        row = {name: int(values[i]) for name, values in ints.items()}
        row.update({name: float(values[i]) for name, values in floats.items()})
        row.update({name: values[i] for name, values in strings.items()})
        rows.append(row)
    return rows


def _read_events(group: Any) -> list[dict[str, Any]]:
    n = len(group.dimensions["event"])
    ints = {name: _numeric(group, name) for name in (
        "event_index", "particle_index", "ordinal", "episode_index",
        "output_batch_index"
    )}
    pos = _numeric(group, "route_position_km")
    retained = _numeric(group, "retained_mass_fraction")
    event_id = _strings(group.variables["event_id"])
    kind = _strings(group.variables["kind"])
    node = _strings(group.variables["node_id"], none_if_empty=True)
    inputs = _strings(group.variables["input_batch_indices_json"])
    rows = []
    for i in range(n):
        x = float(retained[i])
        rows.append({
            **{name: int(values[i]) for name, values in ints.items()},
            "event_id": event_id[i],
            "kind": kind[i],
            "route_position_km": float(pos[i]),
            "node_id": node[i],
            "input_batch_indices": [int(v) for v in json.loads(inputs[i])],
            "retained_mass_fraction": None if math.isnan(x) else x,
        })
    return rows


def read_biography(path: Path) -> dict[str, Any]:
    path = Path(path)
    with Dataset(path, "r") as ds:
        gm = ds.groups["metal"]
        tables = {
            "particles": _read_particles(ds.groups["particles"]),
            "batches": _read_batches(gm.groups["batches"]),
            "ancestry": _read_ancestry(gm.groups["ancestry"]),
            "parents": _read_parents(gm.groups["parents"]),
            "episodes": _read_episodes(ds.groups["objects"]),
            "events": _read_events(ds.groups["events"]),
        }
        stored_hash = str(ds.phase02_biography_sha256)
        computed_hash = biography_hash(tables)
        if stored_hash != computed_hash:
            raise RuntimeError(
                f"v3 phase-02 biography hash mismatch: "
                f"stored={stored_hash} computed={computed_hash}"
            )
        return {
            "phase": str(ds.latest_phase),
            "schema": str(ds.phase02_schema),
            "model_version": str(ds.phase02_model_version),
            "mixing_assumption": str(ds.phase02_mixing_assumption),
            "world_seed": int(ds.phase02_world_seed),
            "phase01_spine_sha256": str(ds.phase02_spine_sha256),
            "biography_sha256": stored_hash,
            **tables,
        }
