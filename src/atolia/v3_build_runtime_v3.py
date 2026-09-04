from __future__ import annotations

"""Build the one shipped Atolia v3 R17 frozen-field NetCDF.

The repaired Phase-08 compact fragments are build inputs only.  The product is
one authoritative field: static river/world tables, 37,100 production cells,
the full compact loss/profile field, exact source/deposition/transport state,
canonical Phase-07 hydro context, and integrity checkpoints.  No hypothesis
JSON and no expanded Phase-02..05 object population are shipped.
"""

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from netCDF4 import Dataset

import archaeology_temporal_world as archaeology
import build_v3_master
import intensity_circulation as intensity
import provenance_field as base
import release_candidate_invariants as release_invariants
import transport_fields
import v3_frozen_world
import v3_hydro_exchange_deposition as phase05
import v3_phase07_canonical as canonical
import v3_phase07_manifest as phase07_manifest
import v3_phase08_compact_fragment as compact
import v3_phase08_runtime_fragment as phase08
import v3_runtime_v3 as runtime_v3


PROFILE_CHUNK = 32768


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_fragment(path: Path) -> dict[str, Any]:
    value = json.loads(gzip.decompress(Path(path).read_bytes()).decode("utf-8"))
    if value.get("schema") != compact.SCHEMA:
        raise RuntimeError(f"unsupported compact fragment schema in {path}")
    if str(value.get("fragment_sha256", "")) != compact.logical_hash(value):
        raise RuntimeError(f"compact fragment hash mismatch: {path}")
    return value


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _float_same(a: Any, b: Any) -> bool:
    return float(a).hex() == float(b).hex()


def _strvar(group: Any, name: str, dim: str, values: Sequence[str]) -> None:
    var = group.createVariable(name, str, (dim,))
    if values:
        var[:] = np.asarray([str(x) for x in values], dtype=object)


def _numvar(group: Any, name: str, dtype: str, dims: tuple[str, ...], values: Any, *, level: int = 6) -> Any:
    var = group.createVariable(name, dtype, dims, zlib=True, complevel=level, shuffle=True)
    if np.asarray(values).size:
        var[:] = np.asarray(values)
    return var


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
            "represented_weight": float(row[columns["represented_weight"]]),
            "recorded_weight": float(row[columns["recorded_weight"]]),
            "step_min": int(row[columns["step_min"]]),
            "step_max": int(row[columns["step_max"]]),
        }
        for field in runtime_v3.PROFILE_PHASE01_FIELDS:
            item[f"{field}_mean"] = float(row[columns[f"{field}_mean"]])
            item[f"{field}_variance"] = float(row[columns[f"{field}_variance"]])
        rows.append(item)
    return sorted(rows, key=lambda item: item["node_token"])


def _cell_source_mix(fragment: Mapping[str, Any], local_cell: int) -> dict[str, float]:
    columns = {name: i for i, name in enumerate(fragment["columns"]["cell_source"])}
    sources = list(fragment["dictionary"]["source"])
    out: dict[str, float] = {}
    for row in fragment["cell_sources"]:
        if int(row[columns["cell"]]) == int(local_cell):
            out[str(sources[int(row[columns["source"]])])] = float(row[columns["weight"]])
    return out


def _fragment_cell_digest(fragment: Mapping[str, Any], local_cell: int) -> bytes:
    columns = {name: i for i, name in enumerate(fragment["columns"]["cell"])}
    row = fragment["cells"][local_cell]
    d = fragment["dictionary"]
    return runtime_v3.cell_identity_hash(
        world_build_id=str(fragment["world_build_id"]),
        global_cell_index=int(row[columns["global_cell_index"]]),
        bundle_id=str(d["bundle"][int(row[columns["bundle"]])]),
        bundle_family=str(d["family"][int(row[columns["family"]])]),
        object_class=str(d["object_class"][int(row[columns["object_class"]])]),
        date_bc=int(row[columns["date_bc"]]),
        origin=str(d["node"][int(row[columns["origin_node"]])]),
        destination=str(d["node"][int(row[columns["destination_node"]])]),
        production_intensity=float(row[columns["production_intensity"]]),
        circulation_seed_intensity=float(row[columns["circulation_seed_intensity"]]),
        recycle_mean=float(row[columns["recycle_mean"]]),
        source_mix=_cell_source_mix(fragment, local_cell),
        already_tokenized=True,
    )


def _world_payload(world: Any) -> dict[str, Any]:
    hx = runtime_v3.float_hex
    return {
        "nodes": [
            [n.id, n.label, hx(n.lon), hx(n.lat), n.kind, hx(n.settlement_weight)]
            for n in world.nodes.values()
        ],
        "edges": [
            [e.a, e.b, e.mode, hx(e.cost), bool(e.directed)] for e in world.edges
        ],
        "sources": [
            [
                s.id, s.label, hx(s.lon), hx(s.lat), int(s.start_bc), int(s.end_bc), hx(s.capacity_scale),
                [[k, hx(s.trace_mean[k])] for k in base.TRACE_KEYS],
                [[k, hx(s.isotope_mean[k])] for k in base.ISO_KEYS],
            ]
            for s in world.sources.values()
        ],
        "bundles": [
            [b.id, b.family, b.origin, b.destination, hx(b.recycle_mean), hx(world.bundle_incidence.get(b.id, 1.0))]
            for b in world.bundles
        ],
        "workshops": [
            [
                w.id, w.node_id, hx(w.lon), hx(w.lat), int(w.start_bc), int(w.end_bc), int(w.workers),
                w.lineage_id, [hx(x) for x in w.technical_vector], hx(w.capacity_weight),
                str(world.workshop_guild.get(w.id) or ""), hx(world.guild_strength.get(w.id, 0.0)),
            ]
            for w in world.workshops
        ],
        "guilds": [
            [gid, str(row.get("anchor_node", "")), hx(row.get("mobility_scale", 0.0)), [hx(x) for x in row.get("prototype", ())]]
            for gid, row in sorted(world.guilds.items())
        ],
    }


def _write_world_tables(ds: Dataset, world: Any) -> str:
    payload = _world_payload(world)
    digest = hashlib.sha256(runtime_v3.stable_json(payload).encode("utf-8")).hexdigest()

    g = ds.createGroup("world_nodes")
    g.createDimension("node", len(world.nodes))
    nodes = list(world.nodes.values())
    _strvar(g, "node_id", "node", [n.id for n in nodes])
    _strvar(g, "label", "node", [n.label for n in nodes])
    _strvar(g, "kind", "node", [n.kind for n in nodes])
    _numvar(g, "lon", "f8", ("node",), [n.lon for n in nodes])
    _numvar(g, "lat", "f8", ("node",), [n.lat for n in nodes])
    _numvar(g, "settlement_weight", "f8", ("node",), [n.settlement_weight for n in nodes])
    node_index = {n.id: i for i, n in enumerate(nodes)}

    g = ds.createGroup("world_edges")
    g.createDimension("edge", len(world.edges))
    _numvar(g, "a_node", "i4", ("edge",), [node_index[e.a] for e in world.edges])
    _numvar(g, "b_node", "i4", ("edge",), [node_index[e.b] for e in world.edges])
    _strvar(g, "mode", "edge", [e.mode for e in world.edges])
    _numvar(g, "cost", "f8", ("edge",), [e.cost for e in world.edges])
    _numvar(g, "directed", "i1", ("edge",), [int(e.directed) for e in world.edges])

    sources = list(world.sources.values())
    g = ds.createGroup("world_sources")
    g.createDimension("source", len(sources))
    _strvar(g, "source_id", "source", [s.id for s in sources])
    _strvar(g, "label", "source", [s.label for s in sources])
    for name, values, dtype in (
        ("lon", [s.lon for s in sources], "f8"), ("lat", [s.lat for s in sources], "f8"),
        ("start_bc", [s.start_bc for s in sources], "i4"), ("end_bc", [s.end_bc for s in sources], "i4"),
        ("capacity_scale", [s.capacity_scale for s in sources], "f8"),
    ):
        _numvar(g, name, dtype, ("source",), values)
    for name in base.TRACE_KEYS:
        _numvar(g, f"trace_{name}", "f8", ("source",), [s.trace_mean[name] for s in sources])
    for name in base.ISO_KEYS:
        _numvar(g, f"isotope_{name}", "f8", ("source",), [s.isotope_mean[name] for s in sources])

    g = ds.createGroup("world_bundles")
    g.createDimension("bundle", len(world.bundles))
    _strvar(g, "bundle_id", "bundle", [b.id for b in world.bundles])
    _strvar(g, "family", "bundle", [b.family for b in world.bundles])
    _strvar(g, "origin", "bundle", [b.origin for b in world.bundles])
    _strvar(g, "destination", "bundle", [b.destination for b in world.bundles])
    _numvar(g, "recycle_mean", "f8", ("bundle",), [b.recycle_mean for b in world.bundles])
    _numvar(g, "incidence", "f8", ("bundle",), [world.bundle_incidence.get(b.id, 1.0) for b in world.bundles])

    g = ds.createGroup("world_workshops")
    g.createDimension("workshop", len(world.workshops))
    g.createDimension("technical_axis", 6)
    _strvar(g, "workshop_id", "workshop", [w.id for w in world.workshops])
    _strvar(g, "node_id", "workshop", [w.node_id for w in world.workshops])
    _strvar(g, "lineage_id", "workshop", [w.lineage_id for w in world.workshops])
    _strvar(g, "primary_guild_id", "workshop", [str(world.workshop_guild.get(w.id) or "") for w in world.workshops])
    for name, values, dtype in (
        ("lon", [w.lon for w in world.workshops], "f8"), ("lat", [w.lat for w in world.workshops], "f8"),
        ("start_bc", [w.start_bc for w in world.workshops], "i4"), ("end_bc", [w.end_bc for w in world.workshops], "i4"),
        ("workers", [w.workers for w in world.workshops], "i4"),
        ("capacity_weight", [w.capacity_weight for w in world.workshops], "f8"),
        ("guild_strength", [world.guild_strength.get(w.id, 0.0) for w in world.workshops], "f8"),
    ):
        _numvar(g, name, dtype, ("workshop",), values)
    _numvar(g, "technical_vector", "f8", ("workshop", "technical_axis"), [w.technical_vector for w in world.workshops])

    guild_ids = sorted(world.guilds)
    g = ds.createGroup("world_guilds")
    g.createDimension("guild", len(guild_ids))
    g.createDimension("technical_axis", 6)
    _strvar(g, "guild_id", "guild", guild_ids)
    _strvar(g, "anchor_node", "guild", [str(world.guilds[x].get("anchor_node", "")) for x in guild_ids])
    _numvar(g, "mobility_scale", "f8", ("guild",), [world.guilds[x].get("mobility_scale", 0.0) for x in guild_ids])
    _numvar(g, "prototype", "f8", ("guild", "technical_axis"), [world.guilds[x].get("prototype", np.zeros(6)) for x in guild_ids])
    return digest


def _write_production_cells(ds: Dataset, cells: Sequence[intensity.ProductionCell], world: Any) -> None:
    g = ds.createGroup("production_cells")
    g.createDimension("cell", len(cells))
    source_entries = sum(len(c.source_mix) for c in cells)
    g.createDimension("source_ptr_dim", len(cells) + 1)
    g.createDimension("source_entry", source_entries)
    g.createDimension("deposition_mode", len(base.DEPOSITION_MODES))
    g.createDimension("transport_field", len(transport_fields.FIELD_NAMES))
    _strvar(g, "bundle_id", "cell", [c.bundle_id for c in cells])
    _strvar(g, "bundle_family", "cell", [c.bundle_family for c in cells])
    _strvar(g, "object_class", "cell", [c.object_class for c in cells])
    _strvar(g, "origin", "cell", [c.origin for c in cells])
    _strvar(g, "destination", "cell", [c.destination for c in cells])
    _numvar(g, "date_bc", "i4", ("cell",), [c.date_bc for c in cells])
    _numvar(g, "production_intensity", "f8", ("cell",), [c.production_intensity for c in cells])
    _numvar(g, "circulation_seed_intensity", "f8", ("cell",), [c.circulation_seed_intensity for c in cells])
    _numvar(g, "recycle_mean", "f8", ("cell",), [c.recycle_mean for c in cells])

    ptr = [0]
    source_ids: list[str] = []
    source_weights: list[float] = []
    for cell in cells:
        for source_id, value in sorted(cell.source_mix.items()):
            source_ids.append(str(source_id)); source_weights.append(float(value))
        ptr.append(len(source_ids))
    _numvar(g, "source_ptr", "i8", ("source_ptr_dim",), ptr)
    _strvar(g, "source_id", "source_entry", source_ids)
    _numvar(g, "source_weight", "f8", ("source_entry",), source_weights)

    bundle_by_id = {b.id: b for b in world.bundles}
    deposition = np.zeros((len(cells), len(base.DEPOSITION_MODES)), dtype=np.float64)
    field_mix = np.zeros((len(cells), len(transport_fields.FIELD_NAMES)), dtype=np.float64)
    for i, cell in enumerate(cells):
        bundle = bundle_by_id[cell.bundle_id]
        dep = world._deposition_probabilities(cell.object_class, bundle)
        deposition[i, :] = [float(dep.get(name, 0.0)) for name in base.DEPOSITION_MODES]
        phase = float(np.clip((1800.0 - float(cell.date_bc)) / 800.0, 0.0, 1.0))
        fm = transport_fields.object_field_mix(cell.object_class, cell.bundle_family, phase)
        field_mix[i, :] = [float(fm.get(name, 0.0)) for name in transport_fields.FIELD_NAMES]
    _strvar(g, "deposition_mode_name", "deposition_mode", list(base.DEPOSITION_MODES))
    _numvar(g, "deposition_weight", "f8", ("cell", "deposition_mode"), deposition)
    _strvar(g, "transport_field_name", "transport_field", list(transport_fields.FIELD_NAMES))
    _numvar(g, "transport_field_mix", "f8", ("cell", "transport_field"), field_mix)


def _write_hydro(ds: Dataset, world: Any, plan: Mapping[str, Any], certificate: Mapping[str, Any]) -> dict[str, float]:
    _status, _evidence, ensemble = phase05.build_hydro_ensemble(world)
    realization = phase05.realize_hydro(ensemble, world_seed=int(ds.world_seed))
    ids = {row.realization_id for row in realization}
    if len(ids) != 1:
        raise RuntimeError("canonical hydro rebuild did not produce exactly one realization")
    fresh_id = next(iter(ids))
    canonical_id = str(plan["observed_variants"]["canonical_hydro_realization_id"])
    minority_id = str(plan["observed_variants"]["minority_hydro_realization_id"])
    if fresh_id not in {canonical_id, minority_id}:
        raise RuntimeError(f"fresh hydro topology {fresh_id} is outside the Phase-07 observed pair")
    if canonical_id != str(certificate["canonical_hydro_realization_id"]):
        raise RuntimeError("cutoff plan/certificate disagree on canonical hydro realization")
    context = phase05._hydro_context(realization)
    for row in plan["observed_boundary"]["affected_nodes"]:
        context[str(row["node_id"])] = float(row["canonical"])
    node_ids = list(world.nodes)
    g = ds.createGroup("canonical_hydro")
    g.createDimension("node", len(node_ids))
    _strvar(g, "node_id", "node", node_ids)
    _numvar(g, "context", "f8", ("node",), [float(context.get(node, 0.0)) for node in node_ids])
    ds.canonical_hydro_realization_id = canonical_id
    ds.minority_hydro_realization_id = minority_id
    ds.fresh_build_hydro_realization_id = fresh_id
    return {node: float(context.get(node, 0.0)) for node in node_ids}


def _semantic_runtime_fingerprint(ds: Dataset) -> str:
    """Hash the authoritative numeric/string field, excluding its own digest attr."""
    h = hashlib.sha256()
    for attr in (
        "schema", "generator_version", "world_build_id", "world_seed", "workshop_count",
        "intensity_steps", "target_geography_nodes", "population_cells", "hypothesis_sha256",
        "repair_certificate_sha256", "cutoff_plan_sha256", "world_table_sha256",
        "canonical_hydro_realization_id",
    ):
        h.update(attr.encode()); h.update(b"\0"); h.update(str(getattr(ds, attr)).encode()); h.update(b"\0")
    for group_name in sorted(ds.groups):
        group = ds.groups[group_name]
        h.update(group_name.encode()); h.update(b"\0")
        for name in sorted(group.variables):
            var = group.variables[name]
            h.update(name.encode()); h.update(b"\0")
            values = var[:]
            dtype = getattr(values, "dtype", None)
            kind = getattr(dtype, "kind", None)
            if kind in {"O", "U", "S"} or var.datatype == str:
                for text in _strings(var):
                    raw = text.encode("utf-8")
                    h.update(len(raw).to_bytes(4, "big")); h.update(raw)
            else:
                arr = np.ma.getdata(np.asarray(values))
                if arr.dtype.kind == "f": arr = arr.astype(f">f{arr.dtype.itemsize}", copy=False)
                elif arr.dtype.kind == "i": arr = arr.astype(f">i{arr.dtype.itemsize}", copy=False)
                elif arr.dtype.kind == "u": arr = arr.astype(f">u{arr.dtype.itemsize}", copy=False)
                else: arr = np.ascontiguousarray(arr)
                h.update(np.ascontiguousarray(arr).tobytes(order="C"))
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
    by_ordinal: dict[int, Path] = {}
    for path in paths:
        ordinal = int(path.name.removeprefix("compact-").removesuffix(".json.gz"))
        if ordinal in by_ordinal: raise RuntimeError(f"duplicate compact ordinal {ordinal}")
        by_ordinal[ordinal] = path
    if sorted(by_ordinal) != list(range(expected_shards)):
        raise RuntimeError("compact fragment ordinals are not contiguous")

    plan = _read_json(cutoff_plan_path)
    certificate = _read_json(repair_certificate_path)
    phase08.validate_certificate(certificate)
    hypothesis = _read_json(hypothesis_path)
    first = _read_fragment(by_ordinal[0])
    world_build_id = str(first["world_build_id"])
    if str(plan["world_build_id"]) != world_build_id or str(certificate["world_build_id"]) != world_build_id:
        raise RuntimeError("R17 inputs disagree on world_build_id")

    release_invariants.install()
    world = archaeology.TemporalFieldArchaeologicalWorld(
        hypothesis, seed=canonical.CANONICAL_WORLD_SEED, target_geography_nodes=canonical.CANONICAL_NODES
    )
    world.build(workshop_count=canonical.CANONICAL_WORKSHOPS)
    cells = intensity.production_cells(world)
    if len(cells) != population_cells:
        raise RuntimeError(f"canonical world produced {len(cells)} cells, expected {population_cells}")
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
    if phase07_manifest.world_build_id(config) != world_build_id:
        raise RuntimeError("canonical static world does not reproduce Phase-07 world_build_id")

    out_path = Path(out_path); out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.unlink(missing_ok=True)
    with Dataset(out_path, "w", format="NETCDF4") as ds:
        ds.schema = runtime_v3.RUNTIME_SCHEMA
        ds.generator_version = runtime_v3.GENERATOR_VERSION
        ds.world_table_schema = v3_frozen_world.WORLD_TABLE_SCHEMA
        ds.product_kind = "sealed-shared-frozen-latent-river-field"
        ds.world_build_id = world_build_id
        ds.world_seed = int(canonical.CANONICAL_WORLD_SEED)
        ds.workshop_count = int(canonical.CANONICAL_WORKSHOPS)
        ds.intensity_steps = int(canonical.CANONICAL_STEPS)
        ds.target_geography_nodes = int(canonical.CANONICAL_NODES)
        ds.population_cells = int(population_cells)
        ds.target_player_objects = int(runtime_v3.TARGET_OBJECTS)
        ds.hypothesis_sha256 = build_v3_master.canonical_hypothesis_sha256(hypothesis)
        ds.hypothesis_storage = "not-shipped-compiled-into-frozen-field"
        ds.repair_certificate_sha256 = str(certificate["certificate_sha256"])
        ds.cutoff_plan_sha256 = _sha256_file(cutoff_plan_path)
        ds.cell_hash_policy = runtime_v3.CELL_HASH_POLICY
        ds.profile_hash_policy = runtime_v3.PROFILE_HASH_POLICY
        ds.acquisition_policy = "slot-domain-separated-profile-readout-then-exact-selected-cell-propagation"

        ds.world_table_sha256 = _write_world_tables(ds, world)
        _write_production_cells(ds, cells, world)
        _write_hydro(ds, world, plan, certificate)

        gp = ds.createGroup("profiles")
        gp.createDimension("profile", None)
        gp.createDimension("hash_byte", 32)
        gp.createDimension("cell_ptr", population_cells + 1)
        gp.createDimension("node_ptr", len(world.nodes) + 1)
        # site_profile is finalized after the streaming append.
        gp.createDimension("site_profile", None)
        def pv(name: str, dtype: str, dims: tuple[str, ...]):
            chunks = None
            if dims == ("profile",): chunks = (PROFILE_CHUNK,)
            elif dims == ("profile", "hash_byte"): chunks = (min(PROFILE_CHUNK, 8192), 32)
            return gp.createVariable(name, dtype, dims, zlib=True, complevel=6, shuffle=True, chunksizes=chunks)
        p_cell = pv("cell_index", "i4", ("profile",))
        p_node = pv("node_index", "i4", ("profile",))
        p_count = pv("lineage_count", "i4", ("profile",))
        p_loss = pv("loss_intensity", "f8", ("profile",))
        p_repr = pv("represented_weight", "f8", ("profile",))
        p_record = pv("recorded_weight", "f8", ("profile",))
        p_step_min = pv("step_min", "i2", ("profile",))
        p_step_max = pv("step_max", "i2", ("profile",))
        p_hash = pv("checkpoint_sha256", "u1", ("profile", "hash_byte"))
        p_mean = {f: pv(f"mean_{f}", "f8", ("profile",)) for f in runtime_v3.PROFILE_PHASE01_FIELDS}
        p_var = {f: pv(f"variance_{f}", "f8", ("profile",)) for f in runtime_v3.PROFILE_PHASE01_FIELDS}
        cell_identity = np.zeros((population_cells, 32), dtype=np.uint8)
        cell_profile_hash = np.zeros((population_cells, 32), dtype=np.uint8)
        cell_profile_count = np.zeros(population_cells, dtype=np.int64)
        cell_recorded = np.zeros(population_cells, dtype=np.float64)
        shard_phase01 = np.zeros((expected_shards, 32), dtype=np.uint8)
        node_index = {node_id: i for i, node_id in enumerate(world.nodes)}
        token_to_node = {phase08.anonymous_token(world_build_id, "node", node_id): node_id for node_id in world.nodes}
        cursor = 0
        capsules = 0
        total_lineages = 0

        for ordinal in range(expected_shards):
            fragment = _read_fragment(by_ordinal[ordinal])
            if int(fragment["chunk_ordinal"]) != ordinal or str(fragment["world_build_id"]) != world_build_id:
                raise RuntimeError(f"compact identity mismatch at ordinal {ordinal}")
            if str(fragment["recovery"]["certificate_sha256"]) != str(certificate["certificate_sha256"]):
                raise RuntimeError(f"repair certificate mismatch at ordinal {ordinal}")
            capsules += int(bool(fragment["recovery"].get("replay_capsule_sha256")))
            shard_phase01[ordinal, :] = np.frombuffer(bytes.fromhex(str(fragment["source"]["phase01_spine_sha256"])), dtype=np.uint8)
            start, stop = int(fragment["global_cell_start"]), int(fragment["global_cell_stop"])
            if start != ordinal * 64 or stop != min(population_cells, start + 64):
                raise RuntimeError(f"unexpected cell interval {start}:{stop} at ordinal {ordinal}")
            if len(fragment["cells"]) != stop - start:
                raise RuntimeError(f"compact cell count mismatch at ordinal {ordinal}")

            for local in range(stop - start):
                global_cell = start + local
                generated = runtime_v3.cell_identity_hash(
                    world_build_id=world_build_id,
                    global_cell_index=global_cell,
                    bundle_id=cells[global_cell].bundle_id,
                    bundle_family=cells[global_cell].bundle_family,
                    object_class=cells[global_cell].object_class,
                    date_bc=cells[global_cell].date_bc,
                    origin=cells[global_cell].origin,
                    destination=cells[global_cell].destination,
                    production_intensity=cells[global_cell].production_intensity,
                    circulation_seed_intensity=cells[global_cell].circulation_seed_intensity,
                    recycle_mean=cells[global_cell].recycle_mean,
                    source_mix=cells[global_cell].source_mix,
                )
                observed = _fragment_cell_digest(fragment, local)
                if generated != observed:
                    raise RuntimeError(f"frozen production cell {global_cell} differs from repaired corpus")
                cell_identity[global_cell, :] = np.frombuffer(generated, dtype=np.uint8)

                rows = _profile_rows_for_cell(fragment, local)
                if not rows: raise RuntimeError(f"cell {global_cell} has no profiles")
                cell_profile_hash[global_cell, :] = np.frombuffer(runtime_v3.profile_checkpoint_hash(rows), dtype=np.uint8)
                cell_profile_count[global_cell] = len(rows)
                cell_recorded[global_cell] = math.fsum(float(r["recorded_weight"]) for r in rows)
                n = len(rows); sl = slice(cursor, cursor + n)
                raw_nodes: list[int] = []
                single_hash = np.zeros((n, 32), dtype=np.uint8)
                for j, row in enumerate(rows):
                    raw = token_to_node.get(str(row["node_token"]))
                    if raw is None: raise RuntimeError(f"profile node token does not resolve in frozen world: {row['node_token']}")
                    raw_nodes.append(node_index[raw])
                    single_hash[j, :] = np.frombuffer(runtime_v3.profile_checkpoint_hash([row]), dtype=np.uint8)
                p_cell[sl] = np.full(n, global_cell, dtype=np.int32)
                p_node[sl] = np.asarray(raw_nodes, dtype=np.int32)
                p_count[sl] = np.asarray([r["lineage_count"] for r in rows], dtype=np.int32)
                p_loss[sl] = np.asarray([r["loss_intensity"] for r in rows], dtype=np.float64)
                p_repr[sl] = np.asarray([r["represented_weight"] for r in rows], dtype=np.float64)
                p_record[sl] = np.asarray([r["recorded_weight"] for r in rows], dtype=np.float64)
                p_step_min[sl] = np.asarray([r["step_min"] for r in rows], dtype=np.int16)
                p_step_max[sl] = np.asarray([r["step_max"] for r in rows], dtype=np.int16)
                p_hash[sl, :] = single_hash
                for field in runtime_v3.PROFILE_PHASE01_FIELDS:
                    p_mean[field][sl] = np.asarray([r[f"{field}_mean"] for r in rows], dtype=np.float64)
                    p_var[field][sl] = np.asarray([r[f"{field}_variance"] for r in rows], dtype=np.float64)
                total_lineages += sum(int(r["lineage_count"]) for r in rows)
                cursor += n
            del fragment

        if capsules != 9: raise RuntimeError(f"expected 9 capsule-backed fragments, found {capsules}")
        gp.profile_count = int(cursor)
        gp.lineages_represented = int(total_lineages)
        gp.recorded_weight_total = float(np.sum(np.asarray(p_record[:], dtype=np.float64), dtype=np.float64))
        # Profiles were appended in cell order, so a simple cumulative count is the exact cell CSR.
        cell_ptr = np.zeros(population_cells + 1, dtype=np.int64)
        cell_ptr[1:] = np.cumsum(cell_profile_count, dtype=np.int64)
        if int(cell_ptr[-1]) != cursor: raise RuntimeError("profile/cell CSR count mismatch")
        _numvar(gp, "cell_ptr", "i8", ("cell_ptr",), cell_ptr)
        _numvar(gp, "cell_recorded_weight", "f8", ("cell_ptr",), np.concatenate([cell_recorded, [0.0]]))

        profile_nodes = np.asarray(p_node[:], dtype=np.int64)
        order = np.argsort(profile_nodes, kind="stable")
        counts = np.bincount(profile_nodes, minlength=len(world.nodes))
        site_ptr = np.zeros(len(world.nodes) + 1, dtype=np.int64); site_ptr[1:] = np.cumsum(counts, dtype=np.int64)
        _numvar(gp, "site_ptr", "i8", ("node_ptr",), site_ptr)
        site_index = gp.createVariable("site_profile_index", "i4", ("site_profile",), zlib=True, complevel=6, shuffle=True, chunksizes=(PROFILE_CHUNK,))
        site_index[:] = order.astype(np.int32)

        gi = ds.createGroup("integrity")
        gi.createDimension("cell", population_cells); gi.createDimension("hash_byte", 32); gi.createDimension("shard", expected_shards)
        _numvar(gi, "cell_identity_sha256", "u1", ("cell", "hash_byte"), cell_identity)
        _numvar(gi, "cell_profile_sha256", "u1", ("cell", "hash_byte"), cell_profile_hash)
        _numvar(gi, "shard_phase01_sha256", "u1", ("shard", "hash_byte"), shard_phase01)

    with Dataset(out_path, "r+") as ds:
        ds.runtime_fingerprint = _semantic_runtime_fingerprint(ds)
        ds.runtime_profile_count = int(ds.groups["profiles"].profile_count)
    with Dataset(out_path, "r") as ds:
        fingerprint = str(ds.runtime_fingerprint)
        if _semantic_runtime_fingerprint(ds) != fingerprint:
            raise RuntimeError("R17 semantic fingerprint changed in NetCDF roundtrip")
        if "hypothesis_bytes" in ds.variables or any("hypothesis" in name.lower() for name in ds.variables):
            raise RuntimeError("R17 unexpectedly contains a plaintext hypothesis variable")
        profile_count = int(ds.runtime_profile_count)

    return {
        "schema": runtime_v3.RUNTIME_SCHEMA,
        "world_build_id": world_build_id,
        "runtime_fingerprint": fingerprint,
        "cells": population_cells,
        "profiles": profile_count,
        "lineages_represented": int(total_lineages),
        "capsule_backed_shards": capsules,
        "bytes": out_path.stat().st_size,
        "output": str(out_path),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fragments", type=Path, required=True)
    ap.add_argument("--cutoff-plan", type=Path, required=True)
    ap.add_argument("--repair-certificate", type=Path, required=True)
    ap.add_argument("--hypothesis", type=Path, required=True, help="build-time only; never embedded in R17")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--expected-shards", type=int, default=580)
    ap.add_argument("--population-cells", type=int, default=37100)
    args = ap.parse_args()
    print(json.dumps(build_runtime(
        fragments_dir=args.fragments,
        cutoff_plan_path=args.cutoff_plan,
        repair_certificate_path=args.repair_certificate,
        hypothesis_path=args.hypothesis,
        out_path=args.out,
        expected_shards=args.expected_shards,
        population_cells=args.population_cells,
    ), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
