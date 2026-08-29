from __future__ import annotations

"""Lossless v1-propagation spine storage for Atolia v3 phase 01.

This module intentionally stores the exact aggregate ``CellFlowReport`` and
``LossStratum`` outputs produced by ``intensity_circulation.propagate_world``.
It does not reconstruct latent objects, aggregate rows into moments, or import
the v2 direct particle simulator.

The schema is deliberately small. Later v3 phases may add richer metal,
workshop, hydrological and archaeological state around this spine, but the
phase-01 rows form an equivalence checkpoint against the last coherent v1
world-propagation process.
"""

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from netCDF4 import Dataset


V3_SPINE_SCHEMA = "atolia-v3-v1-propagation-spine-v1"
V3_PHASE = "atolia-v3-01-v1-propagation-spine"

CELL_FLOAT_FIELDS = (
    "production_intensity",
    "circulation_seed_intensity",
    "recycle_mean",
    "produced",
    "circulation_seed",
    "transfer_flux",
    "return_flux",
    "recycle_flux",
    "loss_flux",
    "retire_flux",
    "residual_active",
    "conservation_error",
    "relative_conservation_error",
)

LOSS_FLOAT_FIELDS = (
    "loss_intensity",
    "expected_recycle_count",
    "expected_repair_count",
    "expected_source_entropy",
    "expected_field_crossings",
    "expected_physical_crossings",
    "route_distance_from_origin_km",
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
    return json.dumps(_plain(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def cell_rows_from_reports(reports: Sequence[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cell_index, report in enumerate(reports):
        cell = report.production_cell
        rows.append({
            "cell_index": int(cell_index),
            "bundle_id": str(cell.bundle_id),
            "bundle_family": str(cell.bundle_family),
            "object_class": str(cell.object_class),
            "date_bc": int(cell.date_bc),
            "origin": str(cell.origin),
            "destination": str(cell.destination),
            "production_intensity": float(cell.production_intensity),
            "circulation_seed_intensity": float(cell.circulation_seed_intensity),
            "source_mix_json": stable_json(cell.source_mix),
            "recycle_mean": float(cell.recycle_mean),
            "produced": float(report.produced),
            "circulation_seed": float(report.circulation_seed),
            "transfer_flux": float(report.transfer_flux),
            "return_flux": float(report.return_flux),
            "recycle_flux": float(report.recycle_flux),
            "loss_flux": float(report.loss_flux),
            "retire_flux": float(report.retire_flux),
            "residual_active": float(report.residual_active),
            "max_active_nodes": int(report.max_active_nodes),
            "loss_strata_count": int(len(report.loss_strata)),
            "conservation_error": float(report.conservation_error()),
            "relative_conservation_error": float(report.relative_conservation_error()),
        })
    return rows


def loss_rows_from_reports(reports: Sequence[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    loss_index = 0
    for cell_index, report in enumerate(reports):
        for cell_loss_index, stratum in enumerate(report.loss_strata):
            rows.append({
                "loss_index": int(loss_index),
                "cell_index": int(cell_index),
                "cell_loss_index": int(cell_loss_index),
                "node_id": str(stratum.node_id),
                "step": int(stratum.step),
                "loss_intensity": float(stratum.loss_intensity),
                "deposition_mode_weights_json": stable_json(stratum.deposition_mode_weights),
                "expected_recycle_count": float(stratum.expected_recycle_count),
                "expected_repair_count": float(stratum.expected_repair_count),
                "expected_source_entropy": float(stratum.expected_source_entropy),
                "expected_field_crossings": float(stratum.expected_field_crossings),
                "expected_physical_crossings": float(stratum.expected_physical_crossings),
                "route_distance_from_origin_km": float(stratum.route_distance_from_origin_km),
                "field_mix_json": stable_json(stratum.field_mix),
            })
            loss_index += 1
    return rows


def normalized_flow_summary(flow_summary: Mapping[str, Any]) -> dict[str, Any]:
    return {str(k): _plain(v) for k, v in sorted(flow_summary.items(), key=lambda kv: str(kv[0]))}


def spine_hash(
    cell_rows: Sequence[Mapping[str, Any]],
    loss_rows: Sequence[Mapping[str, Any]],
    flow_summary: Mapping[str, Any],
) -> str:
    payload = {
        "cells": [_plain(dict(row)) for row in cell_rows],
        "loss_strata": [_plain(dict(row)) for row in loss_rows],
        "flow_summary": normalized_flow_summary(flow_summary),
    }
    return hashlib.sha256(stable_json(payload).encode("utf-8")).hexdigest()


def _string_var(group: Any, name: str, dim: str, values: Sequence[str]) -> None:
    var = group.createVariable(name, str, (dim,))
    if values:
        var[:] = np.asarray(list(values), dtype=object)


def _numeric_var(group: Any, name: str, dtype: str, dim: str, values: Sequence[Any]) -> None:
    var = group.createVariable(name, dtype, (dim,), zlib=True, complevel=4, shuffle=True)
    if values:
        var[:] = np.asarray(list(values))


def write_spine_master(
    path: Path,
    *,
    reports: Sequence[Any],
    flow_summary: Mapping[str, Any],
    world_seed: int,
    workshop_count: int,
    intensity_steps: int,
    hypothesis_sha256: str,
    release_invariants_version: str,
    production_mass_error_kg: float,
    target_geography_nodes: int | None = None,
) -> dict[str, Any]:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    cells = cell_rows_from_reports(reports)
    losses = loss_rows_from_reports(reports)
    flow = normalized_flow_summary(flow_summary)
    digest = spine_hash(cells, losses, flow)

    with Dataset(path, "w", format="NETCDF4") as ds:
        ds.schema = V3_SPINE_SCHEMA
        ds.phase = V3_PHASE
        ds.product_kind = "developer_master_spine"
        ds.world_seed = int(world_seed)
        ds.workshop_count = int(workshop_count)
        ds.intensity_steps = int(intensity_steps)
        ds.hypothesis_sha256 = str(hypothesis_sha256)
        ds.release_invariants_version = str(release_invariants_version)
        ds.production_mass_error_kg = float(production_mass_error_kg)
        ds.target_geography_nodes = -1 if target_geography_nodes is None else int(target_geography_nodes)
        ds.intensity_model_version = str(flow.get("model_version", ""))
        ds.poari_contract = "POARI routes archaeological inquiry, not hidden artefact selection."
        ds.spine_sha256 = digest
        ds.flow_summary_json = stable_json(flow)

        gc = ds.createGroup("cells")
        gc.createDimension("cell", len(cells))
        _numeric_var(gc, "cell_index", "i8", "cell", [r["cell_index"] for r in cells])
        _string_var(gc, "bundle_id", "cell", [r["bundle_id"] for r in cells])
        _string_var(gc, "bundle_family", "cell", [r["bundle_family"] for r in cells])
        _string_var(gc, "object_class", "cell", [r["object_class"] for r in cells])
        _numeric_var(gc, "date_bc", "i4", "cell", [r["date_bc"] for r in cells])
        _string_var(gc, "origin", "cell", [r["origin"] for r in cells])
        _string_var(gc, "destination", "cell", [r["destination"] for r in cells])
        _string_var(gc, "source_mix_json", "cell", [r["source_mix_json"] for r in cells])
        for name in CELL_FLOAT_FIELDS:
            _numeric_var(gc, name, "f8", "cell", [r[name] for r in cells])
        _numeric_var(gc, "max_active_nodes", "i8", "cell", [r["max_active_nodes"] for r in cells])
        _numeric_var(gc, "loss_strata_count", "i8", "cell", [r["loss_strata_count"] for r in cells])

        gl = ds.createGroup("loss_strata")
        gl.createDimension("loss", len(losses))
        _numeric_var(gl, "loss_index", "i8", "loss", [r["loss_index"] for r in losses])
        _numeric_var(gl, "cell_index", "i8", "loss", [r["cell_index"] for r in losses])
        _numeric_var(gl, "cell_loss_index", "i8", "loss", [r["cell_loss_index"] for r in losses])
        _string_var(gl, "node_id", "loss", [r["node_id"] for r in losses])
        _numeric_var(gl, "step", "i4", "loss", [r["step"] for r in losses])
        _string_var(
            gl,
            "deposition_mode_weights_json",
            "loss",
            [r["deposition_mode_weights_json"] for r in losses],
        )
        _string_var(gl, "field_mix_json", "loss", [r["field_mix_json"] for r in losses])
        for name in LOSS_FLOAT_FIELDS:
            _numeric_var(gl, name, "f8", "loss", [r[name] for r in losses])

    return {
        "path": str(path),
        "schema": V3_SPINE_SCHEMA,
        "phase": V3_PHASE,
        "cells": len(cells),
        "loss_strata": len(losses),
        "spine_sha256": digest,
        "flow_summary": flow,
    }


def _read_strings(var: Any) -> list[str]:
    values = var[:]
    return [
        value.decode("utf-8") if isinstance(value, bytes) else str(value)
        for value in values
    ]


def _read_numeric(group: Any, name: str) -> Any:
    return group.variables[name][:]


def read_spine_master(path: Path) -> dict[str, Any]:
    path = Path(path)
    with Dataset(path, "r") as ds:
        gc = ds.groups["cells"]
        gl = ds.groups["loss_strata"]
        cell_count = len(gc.dimensions["cell"])
        loss_count = len(gl.dimensions["loss"])

        # Read each backend variable once. Scalar var[i] reads across every row
        # are semantically equivalent but catastrophically slow in WASM and add
        # needless C-extension crossings even on native CPython.
        c_cell_index = _read_numeric(gc, "cell_index")
        c_bundle_id = _read_strings(gc.variables["bundle_id"])
        c_bundle_family = _read_strings(gc.variables["bundle_family"])
        c_object_class = _read_strings(gc.variables["object_class"])
        c_date_bc = _read_numeric(gc, "date_bc")
        c_origin = _read_strings(gc.variables["origin"])
        c_destination = _read_strings(gc.variables["destination"])
        c_source_mix_json = _read_strings(gc.variables["source_mix_json"])
        c_float = {name: _read_numeric(gc, name) for name in CELL_FLOAT_FIELDS}
        c_max_active_nodes = _read_numeric(gc, "max_active_nodes")
        c_loss_strata_count = _read_numeric(gc, "loss_strata_count")

        cells: list[dict[str, Any]] = []
        for i in range(cell_count):
            row: dict[str, Any] = {
                "cell_index": int(c_cell_index[i]),
                "bundle_id": c_bundle_id[i],
                "bundle_family": c_bundle_family[i],
                "object_class": c_object_class[i],
                "date_bc": int(c_date_bc[i]),
                "origin": c_origin[i],
                "destination": c_destination[i],
                "source_mix_json": c_source_mix_json[i],
            }
            for name in CELL_FLOAT_FIELDS:
                row[name] = float(c_float[name][i])
            row["max_active_nodes"] = int(c_max_active_nodes[i])
            row["loss_strata_count"] = int(c_loss_strata_count[i])
            cells.append(row)

        l_loss_index = _read_numeric(gl, "loss_index")
        l_cell_index = _read_numeric(gl, "cell_index")
        l_cell_loss_index = _read_numeric(gl, "cell_loss_index")
        l_node_id = _read_strings(gl.variables["node_id"])
        l_step = _read_numeric(gl, "step")
        l_deposition = _read_strings(gl.variables["deposition_mode_weights_json"])
        l_field_mix = _read_strings(gl.variables["field_mix_json"])
        l_float = {name: _read_numeric(gl, name) for name in LOSS_FLOAT_FIELDS}

        losses: list[dict[str, Any]] = []
        for i in range(loss_count):
            row = {
                "loss_index": int(l_loss_index[i]),
                "cell_index": int(l_cell_index[i]),
                "cell_loss_index": int(l_cell_loss_index[i]),
                "node_id": l_node_id[i],
                "step": int(l_step[i]),
                "deposition_mode_weights_json": l_deposition[i],
                "field_mix_json": l_field_mix[i],
            }
            for name in LOSS_FLOAT_FIELDS:
                row[name] = float(l_float[name][i])
            losses.append(row)

        flow = json.loads(str(ds.flow_summary_json))
        stored_hash = str(ds.spine_sha256)
        computed_hash = spine_hash(cells, losses, flow)
        if stored_hash != computed_hash:
            raise RuntimeError(
                f"v3 spine hash mismatch: stored={stored_hash} computed={computed_hash}"
            )

        return {
            "schema": str(ds.schema),
            "phase": str(ds.phase),
            "world_seed": int(ds.world_seed),
            "workshop_count": int(ds.workshop_count),
            "intensity_steps": int(ds.intensity_steps),
            "hypothesis_sha256": str(ds.hypothesis_sha256),
            "release_invariants_version": str(ds.release_invariants_version),
            "production_mass_error_kg": float(ds.production_mass_error_kg),
            "target_geography_nodes": int(ds.target_geography_nodes),
            "intensity_model_version": str(ds.intensity_model_version),
            "spine_sha256": stored_hash,
            "flow_summary": flow,
            "cells": cells,
            "loss_strata": losses,
        }
