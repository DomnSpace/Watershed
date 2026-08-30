from __future__ import annotations

"""NetCDF append/read support for Atolia v3 phase-06 medium stratification."""

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from netCDF4 import Dataset

import v3_medium_stratified as medium


V3_PHASE06_SCHEMA = "atolia-v3-medium-stratified-v1"
V3_PHASE06_PHASE = "atolia-v3-06-medium-stratified"
PHASE06_HASH_POLICY = "canonical-float-10sig-v1"


def _canonical(value: Any) -> Any:
    if isinstance(value, np.generic):
        return _canonical(value.item())
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("phase-06 hash cannot contain non-finite floats")
        if value == 0.0:
            return 0.0
        return float(format(float(value), ".10g"))
    if isinstance(value, Mapping):
        return {str(k): _canonical(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    return value


def phase06_hash(payload: Mapping[str, Any]) -> str:
    wrapped = {"hash_policy": PHASE06_HASH_POLICY, "payload": _canonical(payload)}
    raw = json.dumps(wrapped, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _string_var(group: Any, name: str, dim: str, values: Sequence[str]) -> None:
    var = group.createVariable(name, str, (dim,))
    if values:
        var[:] = np.asarray([str(v) for v in values], dtype=object)


def _numeric_var(group: Any, name: str, dtype: str, dim: str, values: Sequence[Any]) -> None:
    var = group.createVariable(name, dtype, (dim,), zlib=True, complevel=4, shuffle=True)
    if values:
        var[:] = np.asarray(values)


def append_phase06(
    path: Path,
    *,
    plan: medium.SelectionPlan,
    probe_indices: Sequence[int],
    metrics: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
    phase05_sha256: str,
) -> dict[str, Any]:
    path = Path(path)
    selection_rows = [row.__dict__.copy() for row in plan.selected]
    strata_rows = [row.__dict__.copy() for row in plan.strata]
    metric_rows = [dict(row) for row in metrics]
    payload = {
        "selection": selection_rows,
        "strata": strata_rows,
        "probe_indices": [int(x) for x in probe_indices],
        "metrics": metric_rows,
        "summary": dict(summary),
        "phase05_sha256": str(phase05_sha256),
    }
    digest = phase06_hash(payload)

    with Dataset(path, "a") as ds:
        if "medium" in ds.groups:
            raise RuntimeError("phase-06 medium group already exists")
        if str(getattr(ds, "phase05_sha256", "")) != str(phase05_sha256):
            raise RuntimeError("phase-06 append does not match phase-05 hash")

        ds.latest_phase = V3_PHASE06_PHASE
        ds.phase06_schema = V3_PHASE06_SCHEMA
        ds.phase06_model_version = medium.PHASE06_MODEL_VERSION
        ds.phase06_selection_policy = medium.SELECTION_POLICY
        ds.phase06_probe_policy = medium.PROBE_POLICY
        ds.phase06_hash_policy = PHASE06_HASH_POLICY
        ds.phase06_phase05_sha256 = str(phase05_sha256)
        ds.phase06_sha256 = digest
        ds.phase06_summary_json = json.dumps(_canonical(dict(summary)), sort_keys=True, separators=(",", ":"))

        root = ds.createGroup("medium")

        gs = root.createGroup("selection")
        gs.createDimension("selected_cell", len(selection_rows))
        _numeric_var(gs, "local_cell_index", "i8", "selected_cell", [r["local_cell_index"] for r in selection_rows])
        _numeric_var(gs, "global_cell_index", "i8", "selected_cell", [r["global_cell_index"] for r in selection_rows])
        _string_var(gs, "stratum_id", "selected_cell", [r["stratum_id"] for r in selection_rows])
        _numeric_var(gs, "inclusion_probability", "f8", "selected_cell", [r["inclusion_probability"] for r in selection_rows])
        _numeric_var(gs, "reconstruction_weight", "f8", "selected_cell", [r["reconstruction_weight"] for r in selection_rows])
        _numeric_var(gs, "tail_score", "i4", "selected_cell", [r["tail_score"] for r in selection_rows])

        gt = root.createGroup("strata")
        gt.createDimension("stratum", len(strata_rows))
        _string_var(gt, "stratum_id", "stratum", [r["stratum_id"] for r in strata_rows])
        _numeric_var(gt, "population_cells", "i8", "stratum", [r["population_cells"] for r in strata_rows])
        _numeric_var(gt, "selected_cells", "i8", "stratum", [r["selected_cells"] for r in strata_rows])
        _numeric_var(gt, "population_production_intensity", "f8", "stratum", [r["population_production_intensity"] for r in strata_rows])

        gp = root.createGroup("probe")
        gp.createDimension("probe_cell", len(probe_indices))
        _numeric_var(gp, "global_cell_index", "i8", "probe_cell", [int(x) for x in probe_indices])

        gm = root.createGroup("preservation")
        gm.createDimension("metric", len(metric_rows))
        _string_var(gm, "stage", "metric", [r["stage"] for r in metric_rows])
        _string_var(gm, "axis", "metric", [r["axis"] for r in metric_rows])
        _string_var(gm, "metric", "metric", [r["metric"] for r in metric_rows])
        _numeric_var(gm, "value", "f8", "metric", [r["value"] for r in metric_rows])
        _numeric_var(gm, "threshold", "f8", "metric", [r["threshold"] for r in metric_rows])
        _numeric_var(gm, "passed", "i1", "metric", [1 if r["passed"] else 0 for r in metric_rows])

    return {
        "path": str(path),
        "phase": V3_PHASE06_PHASE,
        "schema": V3_PHASE06_SCHEMA,
        "model_version": medium.PHASE06_MODEL_VERSION,
        "selection_policy": medium.SELECTION_POLICY,
        "probe_policy": medium.PROBE_POLICY,
        "hash_policy": PHASE06_HASH_POLICY,
        "phase05_sha256": str(phase05_sha256),
        "phase06_sha256": digest,
        "population_cells": int(plan.population_cells),
        "selected_cells": len(selection_rows),
        "strata": len(strata_rows),
        "probe_cells": len(probe_indices),
        "preservation_metrics": len(metric_rows),
        "all_preservation_metrics_passed": all(bool(r["passed"]) for r in metric_rows),
        **dict(summary),
    }


def _read_strings(var: Any) -> list[str]:
    values = var[:]
    return [value.decode("utf-8") if isinstance(value, bytes) else str(value) for value in values]


def read_phase06(path: Path) -> dict[str, Any]:
    path = Path(path)
    with Dataset(path, "r") as ds:
        root = ds.groups["medium"]
        gs = root.groups["selection"]
        selected_count = len(gs.dimensions["selected_cell"])
        local = gs.variables["local_cell_index"][:]
        global_index = gs.variables["global_cell_index"][:]
        stratum = _read_strings(gs.variables["stratum_id"])
        inclusion = gs.variables["inclusion_probability"][:]
        reconstruction = gs.variables["reconstruction_weight"][:]
        tail = gs.variables["tail_score"][:]
        selection = [
            {
                "local_cell_index": int(local[i]),
                "global_cell_index": int(global_index[i]),
                "stratum_id": stratum[i],
                "inclusion_probability": float(inclusion[i]),
                "reconstruction_weight": float(reconstruction[i]),
                "tail_score": int(tail[i]),
            }
            for i in range(selected_count)
        ]

        gt = root.groups["strata"]
        stratum_count = len(gt.dimensions["stratum"])
        ids = _read_strings(gt.variables["stratum_id"])
        pop = gt.variables["population_cells"][:]
        sel = gt.variables["selected_cells"][:]
        prod = gt.variables["population_production_intensity"][:]
        strata = [
            {
                "stratum_id": ids[i],
                "population_cells": int(pop[i]),
                "selected_cells": int(sel[i]),
                "population_production_intensity": float(prod[i]),
            }
            for i in range(stratum_count)
        ]

        gp = root.groups["probe"]
        probe_indices = [int(v) for v in gp.variables["global_cell_index"][:]]

        gm = root.groups["preservation"]
        metric_count = len(gm.dimensions["metric"])
        stage = _read_strings(gm.variables["stage"])
        axis = _read_strings(gm.variables["axis"])
        metric_name = _read_strings(gm.variables["metric"])
        value = gm.variables["value"][:]
        threshold = gm.variables["threshold"][:]
        passed = gm.variables["passed"][:]
        metrics = [
            {
                "stage": stage[i],
                "axis": axis[i],
                "metric": metric_name[i],
                "value": float(value[i]),
                "threshold": float(threshold[i]),
                "passed": bool(int(passed[i])),
            }
            for i in range(metric_count)
        ]

        summary = json.loads(str(ds.phase06_summary_json))
        payload = {
            "selection": selection,
            "strata": strata,
            "probe_indices": probe_indices,
            "metrics": metrics,
            "summary": summary,
            "phase05_sha256": str(ds.phase06_phase05_sha256),
        }
        stored = str(ds.phase06_sha256)
        computed = phase06_hash(payload)
        if stored != computed:
            raise RuntimeError(f"v3 phase-06 hash mismatch: stored={stored} computed={computed}")
        return {
            "phase": str(ds.latest_phase),
            "schema": str(ds.phase06_schema),
            "model_version": str(ds.phase06_model_version),
            "selection_policy": str(ds.phase06_selection_policy),
            "probe_policy": str(ds.phase06_probe_policy),
            "hash_policy": str(ds.phase06_hash_policy),
            "phase05_sha256": str(ds.phase06_phase05_sha256),
            "phase06_sha256": stored,
            "selection": selection,
            "strata": strata,
            "probe_indices": probe_indices,
            "metrics": metrics,
            "summary": summary,
        }
