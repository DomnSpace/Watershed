#!/usr/bin/env python3
from __future__ import annotations

"""Build the Atolia v3 stratified medium cohort through phase 06.

The world is built once.  All ProductionCells are cheap-framed for exact selection
baselines, then only the deterministic medium cohort and independent probe cohort
are propagated.  The medium cohort is written through the normal phase-01..05
schemas and receives an appended phase-06 selection/preservation manifest.

This is not the canonical full product.  It deliberately bounds memory at the
medium cohort; propagation itself is chunked, while the existing phase-02..05
appenders still materialize the selected cohort.  Phase 07 is responsible for the
full-world streaming writer.
"""

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

import netCDF4  # noqa: F401


def _bootstrap_atolia_path() -> Path:
    candidates = [Path.cwd() / "src" / "atolia", Path.cwd()]
    for root in (Path("/home/pyodide/arcade_project"), Path("/home/pyodide/dvx_project")):
        candidates.extend((root / "src" / "atolia", root))
    for entry in list(sys.path):
        if entry:
            root = Path(entry)
            candidates.extend((root / "src" / "atolia", root))
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if (candidate / "archaeology_temporal_world.py").is_file():
            if key not in sys.path:
                sys.path.insert(0, key)
            return candidate
    raise ModuleNotFoundError("Could not locate Watershed src/atolia")


ATOLIA_DIR = _bootstrap_atolia_path()
PROJECT_ROOT = ATOLIA_DIR.parent.parent if ATOLIA_DIR.name == "atolia" else Path.cwd()

import archaeology_temporal_world as archaeology
import build_v3_master
import intensity_circulation as intensity
import release_candidate_invariants as release_invariants
import v3_biography_netcdf
import v3_hydro_exchange_deposition as phase05
import v3_medium_stratified as medium
import v3_metal_biography as biography
import v3_metallurgy_netcdf
import v3_netcdf
import v3_phase05_netcdf
import v3_phase06_netcdf
import v3_source_metallurgy
import v3_workshop_ecology
import v3_workshop_netcdf


NATIVE_DEFAULT_CELLS = medium.DEFAULT_MEDIUM_CELLS
NATIVE_DEFAULT_PROBE = medium.DEFAULT_PROBE_CELLS
WASM_DEFAULT_CELLS = 256
WASM_DEFAULT_PROBE = 96
DEFAULT_NODES = 12
DEFAULT_WORKSHOPS = 320
DEFAULT_STEPS = 2


def _flow_summary(reports: Sequence[Any], available: int) -> dict[str, Any]:
    totals = defaultdict(float)
    strata = 0
    for report in reports:
        for key in (
            "produced", "circulation_seed", "transfer_flux", "return_flux",
            "recycle_flux", "loss_flux", "retire_flux", "residual_active",
        ):
            totals[key] += float(getattr(report, key))
        strata += len(report.loss_strata)
    conservation = totals["circulation_seed"] - (
        totals["return_flux"] + totals["loss_flux"] + totals["retire_flux"] + totals["residual_active"]
    )
    return {
        "model_version": intensity.INTENSITY_MODEL_VERSION,
        "production_cells": len(reports),
        "available_production_cells": int(available),
        "loss_strata": int(strata),
        **{key: float(value) for key, value in totals.items()},
        "conservation_error": float(conservation),
        "relative_conservation_error": float(conservation / max(1.0, totals["circulation_seed"])),
        "transfer_flux_semantics": "internal_throughput",
        "recycle_flux_semantics": "internal_throughput",
        "smoke_subset": False,
        "medium_stratified_subset": True,
    }


def _propagate_indices(
    world: Any,
    all_cells: Sequence[Any],
    indices: Sequence[int],
    *,
    steps: int,
    chunk_cells: int,
) -> list[Any]:
    reports: list[Any] = []
    for chunk in medium.chunked(list(indices), chunk_cells):
        reports.extend(
            intensity.propagate_cell(world, all_cells[int(index)], max_steps=int(steps))
            for index in chunk
        )
    return reports


def _lineages_with_global_indices(
    world: Any,
    reports: Sequence[Any],
    global_indices: Sequence[int],
    *,
    world_seed: int,
) -> list[biography.MetalLineage]:
    if len(reports) != len(global_indices):
        raise ValueError("report/global production index length mismatch")
    out: list[biography.MetalLineage] = []
    for report, global_index in zip(reports, global_indices):
        for loss_index, stratum in enumerate(report.loss_strata):
            out.append(biography.materialize_loss_lineage(
                world,
                stratum,
                world_seed=int(world_seed),
                production_cell_index=int(global_index),
                cell_loss_index=int(loss_index),
            ))
    return out


def _sparse_report_sequence(
    population_cells: int,
    reports: Sequence[Any],
    global_indices: Sequence[int],
) -> list[Any]:
    sparse = [SimpleNamespace(loss_strata=()) for _ in range(int(population_cells))]
    for report, index in zip(reports, global_indices):
        sparse[int(index)] = report
    return sparse


def _build_world(
    hypothesis: Mapping[str, Any],
    *,
    world_seed: int,
    nodes: int,
    workshops: int,
) -> tuple[Any, str, float]:
    release_version = release_invariants.install()
    world = archaeology.TemporalFieldArchaeologicalWorld(
        hypothesis,
        seed=int(world_seed),
        target_geography_nodes=int(nodes),
    )
    world.build(workshop_count=int(workshops))
    mass_error = float(release_invariants.production_mass_error(world))
    tolerance = build_v3_master._production_mass_tolerance_kg(world)
    if abs(mass_error) > tolerance:
        raise RuntimeError("phase-06 production mass invariant failed")
    return world, str(release_version), mass_error


def build_medium(
    hypothesis: Mapping[str, Any],
    *,
    out_path: Path,
    world_seed: int = 1300,
    target_cells: int = NATIVE_DEFAULT_CELLS,
    probe_cells: int = NATIVE_DEFAULT_PROBE,
    chunk_cells: int = medium.DEFAULT_CHUNK_CELLS,
    nodes: int = DEFAULT_NODES,
    workshops: int = DEFAULT_WORKSHOPS,
    steps: int = DEFAULT_STEPS,
) -> dict[str, Any]:
    world, release_version, mass_error = _build_world(
        hypothesis,
        world_seed=world_seed,
        nodes=nodes,
        workshops=workshops,
    )
    all_cells = intensity.production_cells(world)
    frame = medium.build_cell_frame(world, all_cells)
    plan = medium.select_medium_cohort(frame, target_cells=target_cells, seed=world_seed)
    if not plan.selected:
        raise RuntimeError("phase-06 selected no production cells")
    selected_indices = [row.global_cell_index for row in plan.selected]
    inclusion_by_global = {row.global_cell_index: row.inclusion_probability for row in plan.selected}

    reports = _propagate_indices(
        world,
        all_cells,
        selected_indices,
        steps=steps,
        chunk_cells=chunk_cells,
    )
    flow_summary = _flow_summary(reports, len(all_cells))
    result = build_v3_master.V1SpineResult(
        world=world,
        reports=reports,
        flow_summary=flow_summary,
        release_invariants_version=release_version,
        production_mass_error_kg=mass_error,
    )
    spine_summary = build_v3_master._write_phase01(
        result,
        hypothesis,
        out_path=out_path,
        world_seed=world_seed,
        workshop_count=workshops,
        intensity_steps=steps,
        target_geography_nodes=nodes,
    )

    lineages = _lineages_with_global_indices(
        world,
        reports,
        selected_indices,
        world_seed=world_seed,
    )
    biography_summary = v3_biography_netcdf.append_biography(
        out_path,
        lineages=lineages,
        world_seed=world_seed,
        phase01_spine_sha256=str(spine_summary["spine_sha256"]),
    )

    chemistry = v3_source_metallurgy.materialize_metallurgy(world, lineages)
    metallurgy_summary = v3_metallurgy_netcdf.append_metallurgy(
        out_path,
        world=world,
        lineages=lineages,
        chemistry=chemistry,
        world_seed=world_seed,
        phase01_spine_sha256=str(spine_summary["spine_sha256"]),
        phase02_biography_sha256=str(biography_summary["biography_sha256"]),
    )

    workshop_layer = v3_workshop_ecology.materialize_workshop_layer(
        world,
        lineages,
        chemistry,
        world_seed=world_seed,
    )
    workshop_summary = v3_workshop_netcdf.append_workshop_layer(
        out_path,
        layer=workshop_layer,
        world_seed=world_seed,
        phase01_spine_sha256=str(spine_summary["spine_sha256"]),
        phase02_biography_sha256=str(biography_summary["biography_sha256"]),
        phase03_metallurgy_sha256=str(metallurgy_summary["metallurgy_sha256"]),
    )

    sparse_reports = _sparse_report_sequence(len(all_cells), reports, selected_indices)
    layer05 = phase05.materialize_phase05(
        world,
        sparse_reports,
        lineages,
        world_seed=world_seed,
    )
    phase05_summary = v3_phase05_netcdf.append_phase05(
        out_path,
        layer=layer05,
        world_seed=world_seed,
        phase01_spine_sha256=str(spine_summary["spine_sha256"]),
        phase02_biography_sha256=str(biography_summary["biography_sha256"]),
        phase03_metallurgy_sha256=str(metallurgy_summary["metallurgy_sha256"]),
        phase04_workshop_sha256=str(workshop_summary["workshop_sha256"]),
    )

    production_metrics, production_summary = medium.production_preservation(frame, plan)

    probe_indices = medium.select_probe_indices(
        len(all_cells),
        probe_cells=probe_cells,
        seed=world_seed,
    )
    probe_reports = _propagate_indices(
        world,
        all_cells,
        probe_indices,
        steps=steps,
        chunk_cells=chunk_cells,
    )
    probe_lineages = _lineages_with_global_indices(
        world,
        probe_reports,
        probe_indices,
        world_seed=world_seed,
    )
    probe_sparse = _sparse_report_sequence(len(all_cells), probe_reports, probe_indices)
    probe_layer05 = phase05.materialize_phase05(
        world,
        probe_sparse,
        probe_lineages,
        world_seed=world_seed,
    )

    medium_rows = medium.downstream_feature_rows(lineages, layer05, inclusion_by_global)
    probe_probability = float(len(probe_indices) / len(all_cells)) if all_cells else 1.0
    probe_rows = medium.downstream_feature_rows(
        probe_lineages,
        probe_layer05,
        {int(index): probe_probability for index in probe_indices},
    )
    downstream_metrics, downstream_summary = medium.downstream_preservation(medium_rows, probe_rows)
    metrics = production_metrics + downstream_metrics
    all_passed = all(bool(row["passed"]) for row in metrics)
    if not all_passed:
        failed = [f"{r['stage']}:{r['axis']}:{r['metric']}={r['value']:.4g}>{r['threshold']:.4g}" for r in metrics if not r["passed"]]
        raise RuntimeError("phase-06 preservation gate failed: " + ", ".join(failed[:8]))

    phase06_summary_payload = {
        "production_preservation": production_summary,
        "downstream_probe_preservation": downstream_summary,
        "medium_loss_lineages": len(lineages),
        "probe_loss_lineages": len(probe_lineages),
        "medium_external_exchange_tails": len(layer05.external_exchange),
        "probe_external_exchange_tails": len(probe_layer05.external_exchange),
        "medium_shared_deposition_pools": sum(pool.member_count > 1 for pool in layer05.deposition_pools),
        "probe_shared_deposition_pools": sum(pool.member_count > 1 for pool in probe_layer05.deposition_pools),
        "chunk_cells": int(chunk_cells),
        "materialization_status": "all-world-frame-only; propagation-chunked; selected-phase02-05-bounded-in-memory; full streaming deferred phase07",
    }
    phase06_summary = v3_phase06_netcdf.append_phase06(
        out_path,
        plan=plan,
        probe_indices=probe_indices,
        metrics=metrics,
        summary=phase06_summary_payload,
        phase05_sha256=str(phase05_summary["phase05_sha256"]),
    )
    read06 = v3_phase06_netcdf.read_phase06(out_path)
    if read06["phase06_sha256"] != phase06_summary["phase06_sha256"]:
        raise RuntimeError("phase-06 NetCDF roundtrip hash mismatch")

    return {
        **spine_summary,
        "latest_phase": v3_phase06_netcdf.V3_PHASE06_PHASE,
        "metal_biography": biography_summary,
        "source_metallurgy": metallurgy_summary,
        "workshop_ecology": workshop_summary,
        "hydro_exchange_deposition": phase05_summary,
        "medium_stratified": phase06_summary,
        "roundtrip": {
            "phase05_phase06_hash_link_equal": read06["phase05_sha256"] == phase05_summary["phase05_sha256"],
            "phase06_hash_equal": True,
            "global_cell_indices_preserved": [r["global_cell_index"] for r in read06["selection"]] == selected_indices,
            "production_preservation_passed": production_summary["all_passed"],
            "downstream_probe_preservation_passed": downstream_summary["all_passed"],
        },
    }


def main() -> None:
    is_wasm = sys.platform == "emscripten"
    ap = argparse.ArgumentParser(description="Build Atolia v3 phase-06 stratified medium cohort")
    ap.add_argument("--hypothesis", type=Path, default=Path("hypotheses/atolia_atesis_1800_1000_v0.json"))
    ap.add_argument("--out", type=Path, default=Path("cache/atolia_v3_phase06_medium.nc"))
    ap.add_argument("--world-seed", type=int, default=1300)
    ap.add_argument("--cells", type=int, default=(WASM_DEFAULT_CELLS if is_wasm else NATIVE_DEFAULT_CELLS))
    ap.add_argument("--probe-cells", type=int, default=(WASM_DEFAULT_PROBE if is_wasm else NATIVE_DEFAULT_PROBE))
    ap.add_argument("--chunk-cells", type=int, default=medium.DEFAULT_CHUNK_CELLS)
    ap.add_argument("--nodes", type=int, default=DEFAULT_NODES)
    ap.add_argument("--workshops", type=int, default=DEFAULT_WORKSHOPS)
    ap.add_argument("--steps", type=int, default=DEFAULT_STEPS)
    args = ap.parse_args()

    hypothesis_path = args.hypothesis if args.hypothesis.is_absolute() else PROJECT_ROOT / args.hypothesis
    out_path = args.out if args.out.is_absolute() else PROJECT_ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    hypothesis = json.loads(hypothesis_path.read_text(encoding="utf-8"))
    result = build_medium(
        hypothesis,
        out_path=out_path,
        world_seed=args.world_seed,
        target_cells=args.cells,
        probe_cells=args.probe_cells,
        chunk_cells=args.chunk_cells,
        nodes=args.nodes,
        workshops=args.workshops,
        steps=args.steps,
    )
    result["runner"] = {
        "platform": sys.platform,
        "scale_profile": "wasm-phone-gate" if is_wasm else "native-medium",
        "cells": args.cells,
        "probe_cells": args.probe_cells,
        "chunk_cells": args.chunk_cells,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    host_emit = globals().get("emit")
    if callable(host_emit):
        host_emit(result)


if __name__ == "__main__":
    main()
