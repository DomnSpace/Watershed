#!/usr/bin/env python3
from __future__ import annotations

"""Fast real integration smoke for Atolia v3 through phase 04.

This is deliberately *not* a canonical world product. It builds the real v1
world, checks the release mass invariant, propagates a deterministic prefix of
real v1 ProductionCells through the unchanged ``propagate_cell`` kernel, then
uses the normal phase-01/02/03/04 NetCDF append/read paths.

The file is also a direct Arcade/DVX entry point.
"""

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

# Keep the native dependency visible in the selected entry itself so browser
# hosts using loadPackagesFromImports() discover it without traversing locals.
import netCDF4  # noqa: F401


def _bootstrap_atolia_path() -> Path:
    candidates: list[Path] = []
    cwd = Path.cwd()
    candidates.extend((cwd / "src" / "atolia", cwd))
    for root in (
        Path("/home/pyodide/arcade_project"),
        Path("/home/pyodide/dvx_project"),
    ):
        candidates.extend((root / "src" / "atolia", root))
    for entry in list(sys.path):
        if not entry:
            continue
        try:
            root = Path(entry)
        except TypeError:
            continue
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

    searched = "\n  ".join(sorted(seen))
    raise ModuleNotFoundError(
        "Could not locate Watershed src/atolia for the v3 smoke runner. "
        "Searched:\n  " + searched
    )


ATOLIA_DIR = _bootstrap_atolia_path()
PROJECT_ROOT = ATOLIA_DIR.parent.parent if ATOLIA_DIR.name == "atolia" else Path.cwd()

import archaeology_temporal_world as archaeology
import build_v3_master
import intensity_circulation as intensity
import release_candidate_invariants as release_invariants
import v3_biography_netcdf
import v3_metal_biography
import v3_metallurgy_netcdf
import v3_netcdf
import v3_source_metallurgy
import v3_workshop_ecology
import v3_workshop_netcdf


DEFAULT_SMOKE_CELLS = 64
DEFAULT_SMOKE_GEOGRAPHY_NODES = 12
DEFAULT_SMOKE_WORKSHOPS = 320
DEFAULT_SMOKE_STEPS = 2


def _summary_from_reports(
    reports: Sequence[Any],
    *,
    available_production_cells: int,
) -> dict[str, Any]:
    totals = defaultdict(float)
    strata = 0
    for report in reports:
        totals["produced"] += report.produced
        totals["circulation_seed"] += report.circulation_seed
        totals["transfer_flux"] += report.transfer_flux
        totals["return_flux"] += report.return_flux
        totals["recycle_flux"] += report.recycle_flux
        totals["loss_flux"] += report.loss_flux
        totals["retire_flux"] += report.retire_flux
        totals["residual_active"] += report.residual_active
        strata += len(report.loss_strata)

    conservation = totals["circulation_seed"] - (
        totals["return_flux"]
        + totals["loss_flux"]
        + totals["retire_flux"]
        + totals["residual_active"]
    )
    return {
        "model_version": intensity.INTENSITY_MODEL_VERSION,
        "production_cells": len(reports),
        "available_production_cells": int(available_production_cells),
        "loss_strata": int(strata),
        **{key: float(value) for key, value in totals.items()},
        "conservation_error": float(conservation),
        "relative_conservation_error": float(
            conservation / max(1.0, totals["circulation_seed"])
        ),
        "transfer_flux_semantics": "internal_throughput",
        "recycle_flux_semantics": "internal_throughput",
        "smoke_subset": True,
    }


def _build_smoke_phase02_components(
    hypothesis: Mapping[str, Any],
    *,
    out_path: Path,
    world_seed: int,
    workshop_count: int,
    intensity_steps: int,
    target_geography_nodes: int,
    production_cell_limit: int,
) -> tuple[dict[str, Any], Any, list[v3_metal_biography.MetalLineage]]:
    if production_cell_limit <= 0:
        raise ValueError("production_cell_limit must be positive")

    release_version = release_invariants.install()
    world = archaeology.TemporalFieldArchaeologicalWorld(
        hypothesis,
        seed=int(world_seed),
        target_geography_nodes=int(target_geography_nodes),
    )
    world.build(workshop_count=int(workshop_count))

    mass_error_kg = float(release_invariants.production_mass_error(world))
    tolerance_kg = build_v3_master._production_mass_tolerance_kg(world)
    if abs(mass_error_kg) > tolerance_kg:
        raise RuntimeError(
            "release production mass invariant failed in smoke build: "
            f"{mass_error_kg:.9g} kg > tolerance {tolerance_kg:.9g} kg"
        )

    all_cells = intensity.production_cells(world)
    selected_cells = all_cells[: int(production_cell_limit)]
    if not selected_cells:
        raise RuntimeError("smoke build found no production cells")

    reports = [
        intensity.propagate_cell(world, cell, max_steps=int(intensity_steps))
        for cell in selected_cells
    ]
    flow_summary = _summary_from_reports(
        reports,
        available_production_cells=len(all_cells),
    )
    result = build_v3_master.V1SpineResult(
        world=world,
        reports=reports,
        flow_summary=flow_summary,
        release_invariants_version=str(release_version),
        production_mass_error_kg=mass_error_kg,
    )

    spine_summary = build_v3_master._write_phase01(
        result,
        hypothesis,
        out_path=Path(out_path),
        world_seed=int(world_seed),
        workshop_count=int(workshop_count),
        intensity_steps=int(intensity_steps),
        target_geography_nodes=int(target_geography_nodes),
    )

    lineages = v3_metal_biography.materialize_loss_lineages(
        world,
        reports,
        world_seed=int(world_seed),
    )
    biography_summary = v3_biography_netcdf.append_biography(
        Path(out_path),
        lineages=lineages,
        world_seed=int(world_seed),
        phase01_spine_sha256=str(spine_summary["spine_sha256"]),
    )

    summary = {
        **spine_summary,
        "latest_phase": v3_biography_netcdf.V3_BIOGRAPHY_PHASE,
        "metal_biography": biography_summary,
        "smoke": {
            "production_cell_limit": int(production_cell_limit),
            "available_production_cells": len(all_cells),
            "target_geography_nodes": int(target_geography_nodes),
            "workshops": int(workshop_count),
            "steps": int(intensity_steps),
        },
    }
    return summary, world, lineages


def _append_smoke_phase03(
    summary: Mapping[str, Any],
    world: Any,
    lineages: Sequence[v3_metal_biography.MetalLineage],
    *,
    out_path: Path,
    world_seed: int,
) -> tuple[
    dict[str, Any],
    list[v3_source_metallurgy.MetallurgyLineage],
    dict[str, Any],
]:
    chemistry = v3_source_metallurgy.materialize_metallurgy(world, lineages)
    metallurgy_summary = v3_metallurgy_netcdf.append_metallurgy(
        Path(out_path),
        world=world,
        lineages=lineages,
        chemistry=chemistry,
        world_seed=int(world_seed),
        phase01_spine_sha256=str(summary["spine_sha256"]),
        phase02_biography_sha256=str(summary["metal_biography"]["biography_sha256"]),
    )
    out = {
        **summary,
        "latest_phase": v3_metallurgy_netcdf.V3_METALLURGY_PHASE,
        "source_metallurgy": metallurgy_summary,
    }
    return out, chemistry, metallurgy_summary


def _verify_phase03_roundtrip(
    path: Path,
    lineages: Sequence[v3_metal_biography.MetalLineage],
    metallurgy_summary: Mapping[str, Any],
) -> dict[str, Any]:
    spine = v3_netcdf.read_spine_master(path)
    bio = v3_biography_netcdf.read_biography(path)
    metal = v3_metallurgy_netcdf.read_metallurgy(path)
    if spine["spine_sha256"] != metal["phase01_spine_sha256"]:
        raise RuntimeError("phase-03 smoke spine hash linkage failed")
    if bio["biography_sha256"] != metal["phase02_biography_sha256"]:
        raise RuntimeError("phase-03 smoke biography hash linkage failed")
    phase2_batch_ids = [
        batch.batch_id for lineage in lineages for batch in lineage.batches
    ]
    phase3_batch_ids = [row["batch_id"] for row in metal["chemistry_batches"]]
    if phase2_batch_ids != phase3_batch_ids:
        raise RuntimeError("phase-03 chemistry batch identities differ from phase 02")
    return {
        "phase01_spine_hash_equal": True,
        "phase02_biography_hash_equal": True,
        "phase03_metallurgy_hash_equal": (
            metal["metallurgy_sha256"] == metallurgy_summary["metallurgy_sha256"]
        ),
        "phase02_phase03_batch_ids_equal": True,
        "source_calibration_status": metal["source_calibration_status"],
    }


def build_smoke_master_with_biography(
    hypothesis: Mapping[str, Any],
    *,
    out_path: Path,
    world_seed: int = 1300,
    workshop_count: int = DEFAULT_SMOKE_WORKSHOPS,
    intensity_steps: int = DEFAULT_SMOKE_STEPS,
    target_geography_nodes: int = DEFAULT_SMOKE_GEOGRAPHY_NODES,
    production_cell_limit: int = DEFAULT_SMOKE_CELLS,
) -> dict[str, Any]:
    summary, _, _ = _build_smoke_phase02_components(
        hypothesis,
        out_path=out_path,
        world_seed=world_seed,
        workshop_count=workshop_count,
        intensity_steps=intensity_steps,
        target_geography_nodes=target_geography_nodes,
        production_cell_limit=production_cell_limit,
    )
    return summary


def build_smoke_master_with_metallurgy(
    hypothesis: Mapping[str, Any],
    *,
    out_path: Path,
    world_seed: int = 1300,
    workshop_count: int = DEFAULT_SMOKE_WORKSHOPS,
    intensity_steps: int = DEFAULT_SMOKE_STEPS,
    target_geography_nodes: int = DEFAULT_SMOKE_GEOGRAPHY_NODES,
    production_cell_limit: int = DEFAULT_SMOKE_CELLS,
) -> dict[str, Any]:
    summary, world, lineages = _build_smoke_phase02_components(
        hypothesis,
        out_path=out_path,
        world_seed=world_seed,
        workshop_count=workshop_count,
        intensity_steps=intensity_steps,
        target_geography_nodes=target_geography_nodes,
        production_cell_limit=production_cell_limit,
    )
    summary, _, metallurgy_summary = _append_smoke_phase03(
        summary,
        world,
        lineages,
        out_path=Path(out_path),
        world_seed=world_seed,
    )
    return {
        **summary,
        "roundtrip": _verify_phase03_roundtrip(
            Path(out_path), lineages, metallurgy_summary
        ),
    }


def build_smoke_master_with_workshops(
    hypothesis: Mapping[str, Any],
    *,
    out_path: Path,
    world_seed: int = 1300,
    workshop_count: int = DEFAULT_SMOKE_WORKSHOPS,
    intensity_steps: int = DEFAULT_SMOKE_STEPS,
    target_geography_nodes: int = DEFAULT_SMOKE_GEOGRAPHY_NODES,
    production_cell_limit: int = DEFAULT_SMOKE_CELLS,
) -> dict[str, Any]:
    summary, world, lineages = _build_smoke_phase02_components(
        hypothesis,
        out_path=out_path,
        world_seed=world_seed,
        workshop_count=workshop_count,
        intensity_steps=intensity_steps,
        target_geography_nodes=target_geography_nodes,
        production_cell_limit=production_cell_limit,
    )
    summary, chemistry, metallurgy_summary = _append_smoke_phase03(
        summary,
        world,
        lineages,
        out_path=Path(out_path),
        world_seed=world_seed,
    )
    phase03_roundtrip = _verify_phase03_roundtrip(
        Path(out_path), lineages, metallurgy_summary
    )

    layer = v3_workshop_ecology.materialize_workshop_layer(
        world,
        lineages,
        chemistry,
        world_seed=int(world_seed),
    )
    workshop_summary = v3_workshop_netcdf.append_workshop_layer(
        Path(out_path),
        layer=layer,
        world_seed=int(world_seed),
        phase01_spine_sha256=str(summary["spine_sha256"]),
        phase02_biography_sha256=str(summary["metal_biography"]["biography_sha256"]),
        phase03_metallurgy_sha256=str(metallurgy_summary["metallurgy_sha256"]),
    )
    phase04 = v3_workshop_netcdf.read_workshop_layer(Path(out_path))

    if phase04["phase03_metallurgy_sha256"] != metallurgy_summary["metallurgy_sha256"]:
        raise RuntimeError("phase-04 metallurgy hash linkage failed")

    phase2_batch_ids = {
        batch.batch_id for lineage in lineages for batch in lineage.batches
    }
    operation_batch_ids = {row["batch_id"] for row in phase04["operations"]}
    if not operation_batch_ids.issubset(phase2_batch_ids):
        raise RuntimeError("phase-04 operation points outside phase-02 batch graph")

    bad_unlocalized = [
        row for row in phase04["operations"]
        if row["node_id"] is None and row["workshop_id"] is not None
    ]
    if bad_unlocalized:
        raise RuntimeError("phase-04 fabricated workshops for unlocalized route events")

    localized = [row for row in phase04["operations"] if row["localized"]]
    if not localized:
        raise RuntimeError(
            "phase-04 smoke did not exercise any localized workshop operation; "
            "increase --workshops for this micro-world"
        )

    return {
        **summary,
        "latest_phase": v3_workshop_netcdf.V3_WORKSHOP_PHASE,
        "workshop_ecology": workshop_summary,
        "roundtrip": {
            **phase03_roundtrip,
            "phase04_workshop_hash_equal": (
                phase04["workshop_sha256"] == workshop_summary["workshop_sha256"]
            ),
            "phase03_phase04_hash_link_equal": True,
            "phase04_operation_batches_in_phase02": True,
            "route_interior_unknown_workshops_preserved": True,
            "localized_operations_exercised": len(localized),
            "assignment_policy": phase04["assignment_policy"],
            "operator_model_status": phase04["operator_model_status"],
            "material_fit_status": phase04["material_fit_status"],
        },
    }


def _resolve_project_path(path: Path) -> Path:
    if path.is_absolute() or path.exists():
        return path
    candidate = PROJECT_ROOT / path
    return candidate if candidate.exists() else path


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Run the fast real Atolia v3 phase-04 workshop/guild/tool smoke build"
    )
    ap.add_argument(
        "--hypothesis",
        type=Path,
        default=Path("hypotheses/atolia_atesis_1800_1000_v0.json"),
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path("cache/atolia_v3_phase04_smoke.nc"),
    )
    ap.add_argument("--world-seed", type=int, default=1300)
    ap.add_argument("--cells", type=int, default=DEFAULT_SMOKE_CELLS)
    ap.add_argument("--nodes", type=int, default=DEFAULT_SMOKE_GEOGRAPHY_NODES)
    ap.add_argument("--workshops", type=int, default=DEFAULT_SMOKE_WORKSHOPS)
    ap.add_argument("--steps", type=int, default=DEFAULT_SMOKE_STEPS)
    phase_group = ap.add_mutually_exclusive_group()
    phase_group.add_argument(
        "--biography-only",
        action="store_true",
        help="Stop after phase 02.",
    )
    phase_group.add_argument(
        "--metallurgy-only",
        action="store_true",
        help="Stop after phase 03.",
    )
    args = ap.parse_args()

    hypothesis_path = _resolve_project_path(args.hypothesis)
    out_path = args.out if args.out.is_absolute() else PROJECT_ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)

    hypothesis = json.loads(hypothesis_path.read_text(encoding="utf-8"))
    if args.biography_only:
        builder = build_smoke_master_with_biography
    elif args.metallurgy_only:
        builder = build_smoke_master_with_metallurgy
    else:
        builder = build_smoke_master_with_workshops

    summary = builder(
        hypothesis,
        out_path=out_path,
        world_seed=args.world_seed,
        workshop_count=args.workshops,
        intensity_steps=args.steps,
        target_geography_nodes=args.nodes,
        production_cell_limit=args.cells,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))

    host_emit = globals().get("emit")
    if callable(host_emit):
        host_emit(summary)


if __name__ == "__main__":
    main()
