#!/usr/bin/env python3
from __future__ import annotations

"""Structural/scientific validator for the direct-NetCDF Atolia v2 products."""

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any, Dict

import numpy as np
from netCDF4 import Dataset

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import v2_config as cfg


def _strings(var: Any) -> list[str]:
    return [str(x) for x in var[:].tolist()]


def _finite(name: str, arr: np.ndarray, errors: list[str]) -> None:
    if not np.all(np.isfinite(arr)):
        errors.append(f"{name} contains non-finite values")


def validate(master: Path, runtime: Path | None = None, *, full_expectations: bool = False,
             abs_mass_tolerance_kg: float = 1e-5, rel_mass_tolerance: float = 1e-10) -> Dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    report: Dict[str, Any] = {"schema": "atolia.v2-direct-validator.v1", "errors": errors, "warnings": warnings}

    with Dataset(master, "r") as ds:
        if str(getattr(ds, "schema", "")) != cfg.V2_MASTER_SCHEMA:
            errors.append(f"master schema is {getattr(ds, 'schema', None)!r}, expected {cfg.V2_MASTER_SCHEMA!r}")
        required = {"vocab", "cells", "states", "profiles", "workshops", "tools", "hydro", "events"}
        missing = sorted(required - set(ds.groups))
        if missing:
            errors.append(f"master missing groups: {missing}")
            return report

        vocab = ds.groups["vocab"]
        cells = ds.groups["cells"]
        states = ds.groups["states"]
        profiles = ds.groups["profiles"]
        workshops = ds.groups["workshops"]
        tools = ds.groups["tools"]
        hydro = ds.groups["hydro"]

        moment_names = _strings(vocab.variables["state_moment_name"])
        if tuple(moment_names) != tuple(cfg.STATE_MOMENTS):
            errors.append("state moment vocabulary does not match v2_config.STATE_MOMENTS")
        moment_index = {name: i for i, name in enumerate(moment_names)}
        state_m = np.asarray(states.variables["moment"][:], dtype=np.float64)
        _finite("states/moment", state_m, errors)
        n_state = state_m.shape[0]
        report["exact_states"] = int(n_state)
        report["profiles"] = int(len(profiles.dimensions["profile"]))
        report["production_cells"] = int(len(cells.dimensions["cell"]))
        report["workshops"] = int(len(workshops.dimensions["workshop"]))
        report["tools"] = int(len(tools.dimensions["tool"]))
        report["hydro_candidates"] = int(len(hydro.dimensions["candidate"]))

        if n_state <= 0:
            errors.append("master has no exact terminal states")
        else:
            cum = state_m[:, moment_index["cumulative_metal_distance_km"]]
            obj = state_m[:, moment_index["current_object_distance_km"]]
            ore = state_m[:, moment_index["ore_distance_km"]]
            mem = state_m[:, moment_index["technical_memory_fraction"]]
            remelt = state_m[:, moment_index["remelt_count"]]
            repair = state_m[:, moment_index["repair_count"]]
            atesis = state_m[:, moment_index["atesis_crossing_count"]]
            water = state_m[:, moment_index["water_mode_count"]]
            quality = state_m[:, moment_index["manufacture_quality"]]
            if np.any(cum + 1e-9 < obj):
                errors.append("cumulative metal distance is below current-object distance")
            if np.any(obj < -1e-9) or np.any(ore < -1e-9):
                errors.append("negative distance coordinate")
            if np.any(mem < -1e-8) or np.any(mem > 1.0 + 1e-8):
                errors.append("technical_memory_fraction outside [0,1]")
            if np.any(quality < -1e-8):
                errors.append("negative manufacture quality")
            report["states_with_remelt"] = int(np.count_nonzero(remelt > 0))
            report["states_with_repair"] = int(np.count_nonzero(repair > 0))
            report["states_with_atesis_crossing"] = int(np.count_nonzero(atesis > 0))
            report["states_with_water_mode"] = int(np.count_nonzero(water > 0))
            report["max_cumulative_metal_distance_km"] = float(np.max(cum))
            report["max_current_object_distance_km"] = float(np.max(obj))

        # Profile joint covariance is mandatory in v2.
        cov = np.asarray(profiles.variables["covariance_packed"][:], dtype=np.float64)
        expected_packed = len(cfg.COVARIANCE_MOMENTS) * (len(cfg.COVARIANCE_MOMENTS) + 1) // 2
        if cov.ndim != 2 or cov.shape[1] != expected_packed:
            errors.append(f"profile covariance width {cov.shape if cov.ndim else None}, expected packed width {expected_packed}")
        _finite("profiles/covariance_packed", cov, errors)

        # Cell/source CSR.
        ptr = np.asarray(cells.variables["source_ptr"][:], dtype=np.int64)
        source_weight = np.asarray(cells.variables["source_weight"][:], dtype=np.float64)
        if ptr.size != report["production_cells"] + 1:
            errors.append("cell source_ptr length is not cell_count+1")
        if ptr.size and (ptr[0] != 0 or np.any(np.diff(ptr) < 0) or ptr[-1] != source_weight.size):
            errors.append("cell source CSR pointers are invalid")
        source_sums = np.asarray([source_weight[ptr[i]:ptr[i+1]].sum() for i in range(max(0, ptr.size - 1))], dtype=float)
        if source_sums.size:
            report["source_mix_sum_min"] = float(source_sums.min())
            report["source_mix_sum_max"] = float(source_sums.max())
            if np.any(source_sums <= 0) or np.any(np.abs(source_sums - 1.0) > .01):
                errors.append("one or more source mixtures are non-positive or farther than 1% from unity")

        # Full tracked-element closure. Remelt a2 is inventory-conserving; any
        # non-zero discrepancy is therefore numerical/storage error, not a hidden sink.
        accounting = json.loads(str(getattr(ds, "accounting_json", "{}")))
        report["accounting"] = accounting
        initial = dict(accounting.get("initial_explicit_element_mass_kg", {}))
        terminal = dict(accounting.get("terminal_explicit_element_mass_kg", {}))
        closure_report = {}
        for element in cfg.ELEMENTS:
            a = float(initial.get(element, 0.0)); b = float(terminal.get(element, 0.0))
            err = a - b
            tol = max(float(abs_mass_tolerance_kg), abs(a) * float(rel_mass_tolerance))
            closure_report[element] = {"initial_kg": a, "terminal_kg": b, "error_kg": err, "tolerance_kg": tol}
            if abs(err) > tol:
                errors.append(f"{element} explicit mass closure error {err:.9g} kg exceeds {tol:.9g} kg")
        report["element_closure"] = closure_report

        # Primary ledger and horizon.
        cu = np.asarray(cells.variables["primary_cu_kg"][:], dtype=np.float64)
        af = np.asarray(cells.variables["atesis_source_fraction"][:], dtype=np.float64)
        report["primary_cu_kg"] = float(cu.sum())
        report["atesis_associated_primary_cu_kg"] = float(np.sum(cu * af))
        dates = np.asarray(cells.variables["date_bc"][:], dtype=np.int64)
        if dates.size:
            report["cell_date_bc_max"] = int(dates.max())
            report["cell_date_bc_min"] = int(dates.min())
            report["cell_horizon_years"] = int(dates.max() - dates.min())

        metadata = json.loads(str(getattr(ds, "model_metadata_json", "{}")))
        report["model_metadata"] = metadata
        mode = str(metadata.get("mode", "unknown"))
        if "legacy" in str(metadata.get("geochemistry_mode", "")):
            warnings.append("master uses legacy/fallback geochemistry")
        if "provisional" in str(metadata.get("hydrology_mode", "")):
            warnings.append("master uses provisional graph-derived hydrology")
        if full_expectations or mode == "full":
            if "legacy" in str(metadata.get("geochemistry_mode", "")):
                errors.append("full release candidate may not use legacy/fallback geochemistry")
            if "provisional" in str(metadata.get("hydrology_mode", "")):
                errors.append("full release candidate may not use provisional hydrology")
            if dates.size and dates.max() - dates.min() < 900:
                errors.append("full v2 cell horizon is under 900 years; use the 2000–1000 structural hypothesis")
            target_cu = cfg.DEFAULT_CONFIG.primary_cu_tonnes * 1000.0
            if abs(float(cu.sum()) - target_cu) > max(1e-3, target_cu * 1e-10):
                errors.append("full primary Cu ledger does not close to 1 Mt")
            target_atesis = cfg.DEFAULT_CONFIG.atesis_primary_cu_tonnes * 1000.0
            realized_atesis = float(np.sum(cu * af))
            if abs(realized_atesis - target_atesis) > max(1e-3, target_atesis * .01):
                errors.append("full Atesis-associated primary Cu is more than 1% from 200 kt target")

        # Workshop/tool ecology must not collapse to one guild or v1-only tools.
        affinities = np.asarray(workshops.variables["guild_affinity"][:], dtype=np.float64)
        if affinities.size:
            multi = np.sum(affinities > .2, axis=1)
            report["workshops_with_multiple_guild_affinities_gt_0_2"] = int(np.count_nonzero(multi >= 2))
            if not np.any(multi >= 2):
                errors.append("workshop ecology collapsed to one-hot guild identities")
        depths = np.asarray(tools.variables["lineage_depth"][:], dtype=np.int64)
        report["tool_lineage_depth_max"] = int(depths.max()) if depths.size else 0
        report["tools_with_lineage_depth_gt_1"] = int(np.count_nonzero(depths > 1))
        if depths.size and not np.any(depths > 1):
            errors.append("no evolved tool lineage has depth > 1")

        observed = np.asarray(hydro.variables["observed"][:], dtype=np.int64)
        realized = np.asarray(hydro.variables["realized"][:], dtype=np.int64)
        report["hydro_observed_rows"] = int(np.count_nonzero(observed))
        report["hydro_inferred_realized_rows"] = int(np.count_nonzero((observed == 0) & (realized != 0)))
        if observed.size and not np.any(observed):
            errors.append("hydro product has no observed/base carrier rows")

    if runtime is not None:
        with Dataset(runtime, "r") as rt:
            if str(getattr(rt, "schema", "")) != cfg.V2_RUNTIME_SCHEMA:
                errors.append(f"runtime schema is {getattr(rt, 'schema', None)!r}")
            if "states" in rt.groups:
                errors.append("runtime leaks exact /states group")
            for name in ("vocab", "cells", "profiles", "workshops", "tools", "hydro", "events"):
                if name not in rt.groups:
                    errors.append(f"runtime missing /{name}")
            report["runtime_exact_state_rows_omitted"] = int(getattr(rt, "exact_state_rows_omitted", 0))
            if report["runtime_exact_state_rows_omitted"] != 1:
                errors.append("runtime does not declare exact-state omission")

    report["ok"] = not errors
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate direct-NetCDF Atolia v2 master/runtime")
    ap.add_argument("--master", type=Path, default=Path("cache/atolia_master_v2.nc"))
    ap.add_argument("--runtime", type=Path, default=Path("cache/atolia_runtime_v2.nc"))
    ap.add_argument("--no-runtime", action="store_true")
    ap.add_argument("--full-expectations", action="store_true")
    args = ap.parse_args()
    report = validate(args.master, None if args.no_runtime else args.runtime, full_expectations=args.full_expectations)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["ok"] else 2)


if __name__ == "__main__":
    main()
