#!/usr/bin/env python3
from __future__ import annotations

"""Fast real integration smoke for Atolia v3 phase 02.

This is deliberately *not* a canonical world product. It builds the real v1 world,
checks the real release mass invariant, then propagates a deterministic prefix of
real v1 ProductionCells through the unchanged ``intensity.propagate_cell`` kernel.
The resulting reports go through the normal phase-01 NetCDF writer and normal
phase-02 metal-biography append/read format.

Use this for the edit/test loop. G2 remains the full equivalence gate.

The file is also a direct Arcade/DVX entry point. Those hosts execute the selected
source as a synthetic ``<arcade.py>``/entry script, so they do not necessarily add
``src/atolia`` to ``sys.path``. Bootstrap the mounted project before importing local
Atolia modules.
"""

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

# Keep the native dependency visible in the selected entry itself so browser hosts
# using loadPackagesFromImports() do not have to discover it through local modules.
import netCDF4  # noqa: F401


def _bootstrap_atolia_path() -> Path:
    candidates: list[Path] = []

    # Normal repo execution: cwd is the repository root.
    cwd = Path.cwd()
    candidates.extend((cwd / "src" / "atolia", cwd))

    # Known browser-runtime project mounts. Keeping these explicit is useful for
    # direct entry execution where __file__ is synthetic (for example <arcade.py>).
    for root in (
        Path("/home/pyodide/arcade_project"),
        Path("/home/pyodide/dvx_project"),
    ):
        candidates.extend((root / "src" / "atolia", root))

    # Also inspect existing import roots in case the host uses a different mount.
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


DEFAULT_SMOKE_CELLS = 64
DEFAULT_SMOKE_GEOGRAPHY_NODES = 12
DEFAULT_SMOKE_WORKSHOPS = 2
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
    """Build a small real phase-01 -> phase-02 product for rapid verification."""
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

    return {
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


def _resolve_project_path(path: Path) -> Path:
    if path.is_absolute() or path.exists():
        return path
    candidate = PROJECT_ROOT / path
    return candidate if candidate.exists() else path


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the fast real Atolia v3 phase-02 smoke build")
    ap.add_argument(
        "--hypothesis",
        type=Path,
        default=Path("hypotheses/atolia_atesis_1800_1000_v0.json"),
    )
    ap.add_argument("--out", type=Path, default=Path("cache/atolia_v3_phase02_smoke.nc"))
    ap.add_argument("--world-seed", type=int, default=1300)
    ap.add_argument("--cells", type=int, default=DEFAULT_SMOKE_CELLS)
    ap.add_argument("--nodes", type=int, default=DEFAULT_SMOKE_GEOGRAPHY_NODES)
    ap.add_argument("--workshops", type=int, default=DEFAULT_SMOKE_WORKSHOPS)
    ap.add_argument("--steps", type=int, default=DEFAULT_SMOKE_STEPS)
    args = ap.parse_args()

    hypothesis_path = _resolve_project_path(args.hypothesis)
    out_path = args.out if args.out.is_absolute() else PROJECT_ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)

    hypothesis = json.loads(hypothesis_path.read_text(encoding="utf-8"))
    summary = build_smoke_master_with_biography(
        hypothesis,
        out_path=out_path,
        world_seed=args.world_seed,
        workshop_count=args.workshops,
        intensity_steps=args.steps,
        target_geography_nodes=args.nodes,
        production_cell_limit=args.cells,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))

    # Arcade Terminal exposes emit() in the selected Python entry's globals. Keep
    # normal CLI behaviour unchanged while giving the phone runner a result card.
    host_emit = globals().get("emit")
    if callable(host_emit):
        host_emit(summary)


if __name__ == "__main__":
    main()
