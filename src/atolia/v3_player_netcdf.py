from __future__ import annotations

"""Write/read the private 300-object Dr. Corrosion player NetCDF."""

import hashlib
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from netCDF4 import Dataset

import v3_phase08_runtime_fragment as phase08
import v3_runtime_v3 as runtime_v3
import v3_source_metallurgy as metallurgy
from v3_player_crystallizer import CrystallizedWorld


def _token(world_build_id: str, kind: str, raw: object | None) -> str:
    if raw is None or str(raw) == "":
        return ""
    return phase08.anonymous_token(world_build_id, kind, raw)


def _object_id(player_key_hash: str, particle_id: str) -> str:
    digest = hashlib.sha256(
        (runtime_v3.PLAYER_SCHEMA + "|" + player_key_hash + "|" + particle_id).encode("utf-8")
    ).hexdigest()
    return f"o_{digest[:20]}"


def _semantic_fingerprint(rows: Sequence[Mapping[str, Any]], runtime_fingerprint: str) -> str:
    payload = {
        "schema": runtime_v3.PLAYER_SCHEMA,
        "runtime_fingerprint": runtime_fingerprint,
        "objects": list(rows),
    }
    return hashlib.sha256(runtime_v3.stable_json(payload).encode("utf-8")).hexdigest()


def _write_str_var(group: Any, name: str, dim: str, values: Sequence[str]) -> None:
    var = group.createVariable(name, str, (dim,))
    if values:
        var[:] = np.asarray([str(x) for x in values], dtype=object)


def _write_num(group: Any, name: str, dtype: str, dims: tuple[str, ...], values: Any) -> None:
    var = group.createVariable(name, dtype, dims, zlib=True, complevel=6, shuffle=True)
    var[:] = np.asarray(values)


def write_player_netcdf(
    state: CrystallizedWorld,
    out_path: Path,
    *,
    progress_callback: Any = None,
) -> dict[str, Any]:
    selected = list(state.selected)
    if len(selected) != runtime_v3.TARGET_OBJECTS:
        raise ValueError(f"player NetCDF requires exactly {runtime_v3.TARGET_OBJECTS} selected objects")
    chemistry = list(state.chemistry)
    if len(chemistry) != len(selected):
        raise ValueError("selected lineage / chemistry count mismatch")
    chem_by_particle = {row.particle_id: row for row in chemistry}

    core_rows: list[dict[str, Any]] = []
    for i, selected_row in enumerate(selected):
        cand = selected_row.candidate
        lin = cand.lineage
        assignment = cand.assignment
        obs = cand.observation
        core_rows.append({
            "object_id": _object_id(state.player_key_hash, lin.particle_id),
            "particle": _token(state.world_build_id, "particle", lin.particle_id),
            "selection_index": i,
            "global_cell_index": cand.global_cell_index,
            "cell_loss_index": cand.cell_loss_index,
            "object_class": lin.object_class,
            "date_bc": lin.date_bc,
            "loss_node": _token(state.world_build_id, "node", lin.loss_node_id),
            "loss_step": lin.loss_step,
            "loss_intensity": float(cand.stratum.loss_intensity),
            "recorded_weight": float(obs.recorded_weight),
            "deposition_mode": assignment.mode,
            "p_survival": float(obs.p_survival),
            "p_discovery": float(obs.p_discovery),
            "p_record": float(obs.p_record),
            "measurement_seed": int(selected_row.measurement_seed),
        })
    object_ids = [row["object_id"] for row in core_rows]
    if len(set(object_ids)) != runtime_v3.TARGET_OBJECTS:
        raise ValueError("private player object IDs are not unique")
    player_fingerprint = _semantic_fingerprint(core_rows, state.runtime_fingerprint)

    batch_rows: list[dict[str, Any]] = []
    batch_ancestry: list[dict[str, Any]] = []
    batch_parent: list[dict[str, Any]] = []
    episode_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []
    event_inputs: list[dict[str, Any]] = []
    chemistry_rows: list[dict[str, Any]] = []
    element_rows: list[dict[str, Any]] = []
    isotope_rows: list[dict[str, Any]] = []
    pb_source_rows: list[dict[str, Any]] = []

    object_index_by_particle = {row.candidate.lineage.particle_id: i for i, row in enumerate(selected)}
    final_batch_row_by_object: dict[int, int] = {}
    for obj_index, selected_row in enumerate(selected):
        lin = selected_row.candidate.lineage
        for batch in lin.batches:
            bi = len(batch_rows)
            if batch.batch_id == lin.final_batch_id:
                final_batch_row_by_object[obj_index] = bi
            batch_rows.append({
                "object": obj_index,
                "batch": _token(state.world_build_id, "batch", batch.batch_id),
                "role": batch.role,
                "metal_mass_kg": float(batch.metal_mass_kg),
                "date_bc": int(batch.date_bc),
                "route_position_km": float(batch.route_position_km),
                "node": _token(state.world_build_id, "node", batch.node_id),
                "recycle_generation": int(batch.recycle_generation),
                "retained_mass_fraction": float(batch.retained_mass_fraction),
            })
            total = float(batch.metal_mass_kg)
            for source_id, mass in sorted(batch.ancestry_mass_kg.items()):
                batch_ancestry.append({
                    "batch_row": bi,
                    "source": _token(state.world_build_id, "source", source_id),
                    "mass_kg": float(mass),
                    "fraction": float(mass) / total if total > 0.0 else 0.0,
                })
            for parent_id, mass in sorted(batch.parent_contributions_kg.items()):
                batch_parent.append({
                    "batch_row": bi,
                    "parent_batch": _token(state.world_build_id, "batch", parent_id),
                    "contribution_kg": float(mass),
                })
        for episode in lin.episodes:
            episode_rows.append({
                "object": obj_index,
                "episode": _token(state.world_build_id, "episode", episode.episode_id),
                "batch": _token(state.world_build_id, "batch", episode.batch_id),
                "life_index": int(episode.life_index),
                "start_position_km": float(episode.start_position_km),
                "end_position_km": float(episode.end_position_km),
                "start_node": _token(state.world_build_id, "node", episode.start_node_id),
                "end_node": _token(state.world_build_id, "node", episode.end_node_id),
                "end_event_kind": episode.end_event_kind,
            })
        for event in lin.events:
            ei = len(event_rows)
            event_rows.append({
                "object": obj_index,
                "event": _token(state.world_build_id, "event", event.event_id),
                "ordinal": int(event.ordinal),
                "kind": event.kind,
                "route_position_km": float(event.route_position_km),
                "node": _token(state.world_build_id, "node", event.node_id),
                "episode": _token(state.world_build_id, "episode", event.object_episode_id),
                "output_batch": _token(state.world_build_id, "batch", event.output_batch_id),
                "retained_mass_fraction": np.nan if event.retained_mass_fraction is None else float(event.retained_mass_fraction),
            })
            for parent_id in event.input_batch_ids:
                event_inputs.append({
                    "event_row": ei,
                    "batch": _token(state.world_build_id, "batch", parent_id),
                })

        chem_line = chem_by_particle[lin.particle_id]
        if [x.batch_id for x in chem_line.batches] != [x.batch_id for x in lin.batches]:
            raise ValueError("selected Phase-02/03 batch identity mismatch")
        for chem_batch in chem_line.batches:
            ci = len(chemistry_rows)
            ratios = metallurgy.pb_ratios_from_inventory(chem_batch.pb_isotope_mass_kg)
            chemistry_rows.append({
                "object": obj_index,
                "batch": _token(state.world_build_id, "batch", chem_batch.batch_id),
                "metal_mass_kg": float(chem_batch.metal_mass_kg),
                "Pb206_204": float(ratios["Pb206_204"]),
                "Pb207_204": float(ratios["Pb207_204"]),
                "Pb208_204": float(ratios["Pb208_204"]),
            })
            for name in metallurgy.ELEMENTS:
                mass = float(chem_batch.element_mass_kg[name])
                element_rows.append({
                    "chemistry_row": ci,
                    "element": name,
                    "mass_kg": mass,
                    "mass_fraction": mass / float(chem_batch.metal_mass_kg),
                })
            for name in metallurgy.PB_ISOTOPES:
                isotope_rows.append({
                    "chemistry_row": ci,
                    "isotope": name,
                    "mass_kg": float(chem_batch.pb_isotope_mass_kg[name]),
                })
            pb_total = max(0.0, float(chem_batch.element_mass_kg["Pb"]))
            for source_id, mass in sorted(chem_batch.source_pb_mass_kg.items()):
                pb_source_rows.append({
                    "chemistry_row": ci,
                    "source": _token(state.world_build_id, "source", source_id),
                    "pb_mass_kg": float(mass),
                    "fraction_of_pb": float(mass) / pb_total if pb_total > 0.0 else 0.0,
                })

    if set(final_batch_row_by_object) != set(range(runtime_v3.TARGET_OBJECTS)):
        raise ValueError("not every selected object has a final batch row")

    operation_rows: list[dict[str, Any]] = []
    operation_tools: list[dict[str, Any]] = []
    for op in state.workshop_layer.operations:
        obj_index = object_index_by_particle.get(op.particle_id)
        if obj_index is None:
            raise ValueError("workshop operation points outside selected 300")
        oi = len(operation_rows)
        operation_rows.append({
            "object": obj_index,
            "operation": _token(state.world_build_id, "operation", op.operation_id),
            "event_kind": op.event_kind,
            "operation_type": op.operation_type,
            "route_position_km": float(op.route_position_km),
            "node": _token(state.world_build_id, "node", op.node_id),
            "workshop": _token(state.world_build_id, "workshop", op.workshop_id),
            "guild": _token(state.world_build_id, "guild", op.primary_guild_id),
            "guild_affinity": float(op.primary_guild_affinity),
            "capability": np.nan if op.capability is None else float(op.capability),
            "operator_skill": np.nan if op.operator_skill is None else float(op.operator_skill),
            "tool_fit": np.nan if op.tool_fit is None else float(op.tool_fit),
            "support_fit": np.nan if op.support_fit is None else float(op.support_fit),
            "thermal_fit": np.nan if op.thermal_fit is None else float(op.thermal_fit),
            "measurement_fit": np.nan if op.measurement_fit is None else float(op.measurement_fit),
            "material_fit": np.nan if op.material_fit is None else float(op.material_fit),
        })
        for rank, tool_id in enumerate(op.tool_ids):
            operation_tools.append({
                "operation_row": oi,
                "rank": rank,
                "tool": _token(state.world_build_id, "tool", tool_id),
            })

    external_rows: list[dict[str, Any]] = []
    for row in state.external_exchange:
        obj_index = object_index_by_particle.get(row.particle_id)
        if obj_index is None:
            raise ValueError("external exchange points outside selected 300")
        external_rows.append({
            "object": obj_index,
            "exchange": _token(state.world_build_id, "exchange", row.exchange_id),
            "component": row.external_component_id,
            "trigger": row.trigger,
            "contact_probability": float(row.contact_probability),
            "contact_intensity": float(row.contact_intensity),
            "node": _token(state.world_build_id, "node", row.node_id),
        })

    modes = sorted({mode for row in selected for mode in row.candidate.assignment.mode_weights})
    mode_index = {name: i for i, name in enumerate(modes)}
    mode_weights = np.zeros((runtime_v3.TARGET_OBJECTS, len(modes)), dtype=np.float64)
    for i, row in enumerate(selected):
        for name, value in row.candidate.assignment.mode_weights.items():
            mode_weights[i, mode_index[name]] = float(value)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()
    if progress_callback:
        progress_callback(94, "WRITING PLAYER_17.NC")

    with Dataset(out_path, "w", format="NETCDF4") as ds:
        ds.schema = runtime_v3.PLAYER_SCHEMA
        ds.generator_version = runtime_v3.GENERATOR_VERSION
        ds.product_kind = "sealed-private-300-object-world-slice"
        ds.runtime_fingerprint = state.runtime_fingerprint
        ds.world_build_id = state.world_build_id
        ds.player_key_hash = state.player_key_hash
        ds.player_state_fingerprint = player_fingerprint
        ds.object_count = runtime_v3.TARGET_OBJECTS
        ds.levels = 30
        ds.objects_per_level = 10
        ds.canonical_hydro_realization_id = state.canonical_hydro_realization_id

        dims = {
            "object": runtime_v3.TARGET_OBJECTS,
            "deposition_mode": len(modes),
            "batch": len(batch_rows),
            "batch_ancestry": len(batch_ancestry),
            "batch_parent": len(batch_parent),
            "episode": len(episode_rows),
            "event": len(event_rows),
            "event_input": len(event_inputs),
            "chemistry": len(chemistry_rows),
            "element_row": len(element_rows),
            "isotope_row": len(isotope_rows),
            "pb_source": len(pb_source_rows),
            "operation": len(operation_rows),
            "operation_tool": len(operation_tools),
            "external": len(external_rows),
        }
        for name, size in dims.items():
            ds.createDimension(name, size)

        go = ds.createGroup("objects")
        _write_str_var(go, "object_id", "object", object_ids)
        _write_str_var(go, "particle_token", "object", [row["particle"] for row in core_rows])
        _write_str_var(go, "object_class", "object", [row["object_class"] for row in core_rows])
        _write_str_var(go, "bundle_token", "object", [
            _token(state.world_build_id, "bundle", row.candidate.lineage.bundle_id) for row in selected
        ])
        _write_str_var(go, "loss_node_token", "object", [row["loss_node"] for row in core_rows])
        _write_str_var(go, "deposition_mode", "object", [row["deposition_mode"] for row in core_rows])
        _write_str_var(go, "deposition_pool_token", "object", [
            _token(state.world_build_id, "pool", row.candidate.assignment.deposition_pool_id) for row in selected
        ])
        _write_num(go, "selection_index", "i4", ("object",), [row["selection_index"] for row in core_rows])
        _write_num(go, "career_level", "i2", ("object",), [i // 10 + 1 for i in range(len(core_rows))])
        _write_num(go, "career_slot", "i1", ("object",), [i % 10 for i in range(len(core_rows))])
        _write_num(go, "global_cell_index", "i4", ("object",), [row["global_cell_index"] for row in core_rows])
        _write_num(go, "cell_loss_index", "i4", ("object",), [row["cell_loss_index"] for row in core_rows])
        _write_num(go, "date_bc", "i4", ("object",), [row["date_bc"] for row in core_rows])
        _write_num(go, "loss_step", "i2", ("object",), [row["loss_step"] for row in core_rows])
        _write_num(go, "loss_intensity", "f8", ("object",), [row["loss_intensity"] for row in core_rows])
        _write_num(go, "recorded_weight", "f8", ("object",), [row["recorded_weight"] for row in core_rows])
        _write_num(go, "p_survival", "f8", ("object",), [row["p_survival"] for row in core_rows])
        _write_num(go, "p_discovery", "f8", ("object",), [row["p_discovery"] for row in core_rows])
        _write_num(go, "p_record", "f8", ("object",), [row["p_record"] for row in core_rows])
        _write_num(go, "hydro_context_score", "f8", ("object",), [row.candidate.assignment.hydro_context_score for row in selected])
        _write_num(go, "ore_distance_km", "f8", ("object",), [row.candidate.lineage.ore_distance_km for row in selected])
        _write_num(go, "cumulative_metal_distance_km", "f8", ("object",), [row.candidate.lineage.cumulative_metal_distance_km for row in selected])
        _write_num(go, "current_object_distance_km", "f8", ("object",), [row.candidate.lineage.current_object_distance_km for row in selected])
        _write_num(go, "remelt_count", "i2", ("object",), [row.candidate.lineage.remelt_count for row in selected])
        _write_num(go, "repair_count", "i2", ("object",), [row.candidate.lineage.repair_count for row in selected])
        _write_num(go, "source_entropy", "f8", ("object",), [row.candidate.lineage.source_entropy for row in selected])
        _write_num(go, "measurement_seed", "u8", ("object",), [row.measurement_seed for row in selected])
        _write_num(go, "final_batch_row", "i4", ("object",), [final_batch_row_by_object[i] for i in range(len(selected))])

        gd = ds.createGroup("deposition")
        _write_str_var(gd, "mode_name", "deposition_mode", modes)
        _write_num(gd, "mode_weight", "f8", ("object", "deposition_mode"), mode_weights)

        gb = ds.createGroup("biography_batches")
        _write_num(gb, "object_index", "i4", ("batch",), [r["object"] for r in batch_rows])
        _write_str_var(gb, "batch_token", "batch", [r["batch"] for r in batch_rows])
        _write_str_var(gb, "role", "batch", [r["role"] for r in batch_rows])
        _write_str_var(gb, "node_token", "batch", [r["node"] for r in batch_rows])
        for name, dtype in (("metal_mass_kg", "f8"), ("date_bc", "i4"), ("route_position_km", "f8"), ("recycle_generation", "i2"), ("retained_mass_fraction", "f8")):
            _write_num(gb, name, dtype, ("batch",), [r[name] for r in batch_rows])

        ga = ds.createGroup("batch_ancestry")
        _write_num(ga, "batch_row", "i4", ("batch_ancestry",), [r["batch_row"] for r in batch_ancestry])
        _write_str_var(ga, "source_token", "batch_ancestry", [r["source"] for r in batch_ancestry])
        _write_num(ga, "mass_kg", "f8", ("batch_ancestry",), [r["mass_kg"] for r in batch_ancestry])
        _write_num(ga, "fraction", "f8", ("batch_ancestry",), [r["fraction"] for r in batch_ancestry])

        gp = ds.createGroup("batch_parents")
        _write_num(gp, "batch_row", "i4", ("batch_parent",), [r["batch_row"] for r in batch_parent])
        _write_str_var(gp, "parent_batch_token", "batch_parent", [r["parent_batch"] for r in batch_parent])
        _write_num(gp, "contribution_kg", "f8", ("batch_parent",), [r["contribution_kg"] for r in batch_parent])

        ge = ds.createGroup("episodes")
        _write_num(ge, "object_index", "i4", ("episode",), [r["object"] for r in episode_rows])
        for name in ("episode", "batch", "start_node", "end_node", "end_event_kind"):
            _write_str_var(ge, name + ("_token" if name in {"episode", "batch", "start_node", "end_node"} else ""), "episode", [r[name] for r in episode_rows])
        for name, dtype in (("life_index", "i2"), ("start_position_km", "f8"), ("end_position_km", "f8")):
            _write_num(ge, name, dtype, ("episode",), [r[name] for r in episode_rows])

        gev = ds.createGroup("events")
        _write_num(gev, "object_index", "i4", ("event",), [r["object"] for r in event_rows])
        for name in ("event", "kind", "node", "episode", "output_batch"):
            suffix = "_token" if name in {"event", "node", "episode", "output_batch"} else ""
            _write_str_var(gev, name + suffix, "event", [r[name] for r in event_rows])
        for name, dtype in (("ordinal", "i2"), ("route_position_km", "f8"), ("retained_mass_fraction", "f8")):
            _write_num(gev, name, dtype, ("event",), [r[name] for r in event_rows])

        gei = ds.createGroup("event_inputs")
        _write_num(gei, "event_row", "i4", ("event_input",), [r["event_row"] for r in event_inputs])
        _write_str_var(gei, "batch_token", "event_input", [r["batch"] for r in event_inputs])

        gc = ds.createGroup("chemistry")
        _write_num(gc, "object_index", "i4", ("chemistry",), [r["object"] for r in chemistry_rows])
        _write_str_var(gc, "batch_token", "chemistry", [r["batch"] for r in chemistry_rows])
        for name in ("metal_mass_kg", "Pb206_204", "Pb207_204", "Pb208_204"):
            _write_num(gc, name, "f8", ("chemistry",), [r[name] for r in chemistry_rows])

        gel = ds.createGroup("elements")
        _write_num(gel, "chemistry_row", "i4", ("element_row",), [r["chemistry_row"] for r in element_rows])
        _write_str_var(gel, "element", "element_row", [r["element"] for r in element_rows])
        _write_num(gel, "mass_kg", "f8", ("element_row",), [r["mass_kg"] for r in element_rows])
        _write_num(gel, "mass_fraction", "f8", ("element_row",), [r["mass_fraction"] for r in element_rows])

        gi = ds.createGroup("pb_isotopes")
        _write_num(gi, "chemistry_row", "i4", ("isotope_row",), [r["chemistry_row"] for r in isotope_rows])
        _write_str_var(gi, "isotope", "isotope_row", [r["isotope"] for r in isotope_rows])
        _write_num(gi, "mass_kg", "f8", ("isotope_row",), [r["mass_kg"] for r in isotope_rows])

        gps = ds.createGroup("pb_sources")
        _write_num(gps, "chemistry_row", "i4", ("pb_source",), [r["chemistry_row"] for r in pb_source_rows])
        _write_str_var(gps, "source_token", "pb_source", [r["source"] for r in pb_source_rows])
        _write_num(gps, "pb_mass_kg", "f8", ("pb_source",), [r["pb_mass_kg"] for r in pb_source_rows])
        _write_num(gps, "fraction_of_pb", "f8", ("pb_source",), [r["fraction_of_pb"] for r in pb_source_rows])

        gop = ds.createGroup("operations")
        _write_num(gop, "object_index", "i4", ("operation",), [r["object"] for r in operation_rows])
        for name in ("operation", "event_kind", "operation_type", "node", "workshop", "guild"):
            suffix = "_token" if name in {"operation", "node", "workshop", "guild"} else ""
            _write_str_var(gop, name + suffix, "operation", [r[name] for r in operation_rows])
        for name in ("route_position_km", "guild_affinity", "capability", "operator_skill", "tool_fit", "support_fit", "thermal_fit", "measurement_fit", "material_fit"):
            _write_num(gop, name, "f8", ("operation",), [r[name] for r in operation_rows])

        got = ds.createGroup("operation_tools")
        _write_num(got, "operation_row", "i4", ("operation_tool",), [r["operation_row"] for r in operation_tools])
        _write_num(got, "rank", "i1", ("operation_tool",), [r["rank"] for r in operation_tools])
        _write_str_var(got, "tool_token", "operation_tool", [r["tool"] for r in operation_tools])

        gx = ds.createGroup("external_exchange")
        _write_num(gx, "object_index", "i4", ("external",), [r["object"] for r in external_rows])
        for name in ("exchange", "component", "trigger", "node"):
            suffix = "_token" if name in {"exchange", "node"} else ""
            _write_str_var(gx, name + suffix, "external", [r[name] for r in external_rows])
        _write_num(gx, "contact_probability", "f8", ("external",), [r["contact_probability"] for r in external_rows])
        _write_num(gx, "contact_intensity", "f8", ("external",), [r["contact_intensity"] for r in external_rows])

    result = validate_player_netcdf(out_path)
    if result["player_state_fingerprint"] != player_fingerprint:
        raise RuntimeError("player NetCDF semantic fingerprint changed in roundtrip")
    if progress_callback:
        progress_callback(100, "PLAYER_17.NC READY")
    return {**result, "bytes": out_path.stat().st_size, "output": str(out_path)}


def _read_strings(var: Any) -> list[str]:
    values = var[:]
    return [x.decode("utf-8") if isinstance(x, bytes) else str(x) for x in values]


def validate_player_netcdf(path: Path) -> dict[str, Any]:
    path = Path(path)
    with Dataset(path, "r") as ds:
        if str(getattr(ds, "schema", "")) != runtime_v3.PLAYER_SCHEMA:
            raise ValueError("not a Dr. Corrosion player_17 NetCDF")
        if "object" not in ds.dimensions or len(ds.dimensions["object"]) != runtime_v3.TARGET_OBJECTS:
            raise ValueError("player_17.nc does not contain exactly 300 objects")
        if "objects" not in ds.groups or "object_id" not in ds.groups["objects"].variables:
            raise ValueError("player_17.nc lacks object identity table")
        ids = _read_strings(ds.groups["objects"].variables["object_id"])
        if len(ids) != runtime_v3.TARGET_OBJECTS or len(set(ids)) != runtime_v3.TARGET_OBJECTS:
            raise ValueError("player_17.nc object identities are incomplete or duplicated")
        return {
            "schema": str(ds.schema),
            "generator_version": str(ds.generator_version),
            "runtime_fingerprint": str(ds.runtime_fingerprint),
            "world_build_id": str(ds.world_build_id),
            "player_key_hash": str(ds.player_key_hash),
            "player_state_fingerprint": str(ds.player_state_fingerprint),
            "object_count": len(ids),
            "object_ids": ids,
        }


def read_player_objects(path: Path) -> list[dict[str, Any]]:
    """Small compatibility projection for Dr. Corrosion runtime callers."""
    with Dataset(Path(path), "r") as ds:
        if str(getattr(ds, "schema", "")) != runtime_v3.PLAYER_SCHEMA:
            raise ValueError("not a Dr. Corrosion player_17 NetCDF")
        g = ds.groups["objects"]
        ids = _read_strings(g.variables["object_id"])
        classes = _read_strings(g.variables["object_class"])
        modes = _read_strings(g.variables["deposition_mode"])
        cells = np.asarray(g.variables["global_cell_index"][:], dtype=np.int64)
        levels = np.asarray(g.variables["career_level"][:], dtype=np.int64)
        recorded = np.asarray(g.variables["recorded_weight"][:], dtype=np.float64)
        return [
            {
                "object_id": ids[i],
                "level": int(levels[i]),
                "object_class": classes[i],
                "deposition_mode": modes[i],
                "production_cell_index": int(cells[i]),
                "recorded_weight": float(recorded[i]),
            }
            for i in range(len(ids))
        ]
