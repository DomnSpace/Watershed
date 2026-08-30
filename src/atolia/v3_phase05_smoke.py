#!/usr/bin/env python3
from __future__ import annotations

"""Fast real integration smoke for Atolia v3 through phase 05.

Runs the same 64-cell proven-v1 subset used by phase 04, appends phase 02/03/04,
then adds hydrology evidence/ensemble/realization, sparse exchange tails, shared
deposition pools and the survival -> discovery -> recording waterfall.

This is a direct Arcade/DVX entry point.
"""

import argparse
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

import netCDF4  # noqa: F401


def _bootstrap_atolia_path() -> Path:
    candidates: list[Path] = [Path.cwd() / "src" / "atolia", Path.cwd()]
    for root in (Path("/home/pyodide/arcade_project"), Path("/home/pyodide/dvx_project")):
        candidates.extend((root / "src" / "atolia", root))
    for entry in list(sys.path):
        if entry:
            root = Path(entry)
            candidates.extend((root / "src" / "atolia", root))
    for candidate in candidates:
        if (candidate / "archaeology_temporal_world.py").is_file():
            key = str(candidate)
            if key not in sys.path:
                sys.path.insert(0, key)
            return candidate
    raise ModuleNotFoundError("Could not locate Watershed src/atolia")


ATOLIA_DIR = _bootstrap_atolia_path()
PROJECT_ROOT = ATOLIA_DIR.parent.parent if ATOLIA_DIR.name == "atolia" else Path.cwd()

import v3_biography_netcdf
import v3_hydro_exchange_deposition as phase05
import v3_netcdf
import v3_phase05_netcdf
import v3_smoke
import v3_workshop_ecology
import v3_workshop_netcdf


DEFAULT_CELLS = 64
DEFAULT_NODES = 12
DEFAULT_WORKSHOPS = 320
DEFAULT_STEPS = 2


def _reports_from_spine(spine: Mapping[str, Any]) -> list[Any]:
    cells = []
    for row in spine["cells"]:
        cells.append(SimpleNamespace(
            bundle_id=row["bundle_id"],
            bundle_family=row["bundle_family"],
            object_class=row["object_class"],
            date_bc=row["date_bc"],
            origin=row["origin"],
            destination=row["destination"],
            source_mix=json.loads(row["source_mix_json"]),
        ))
    grouped: dict[int, list[Any]] = {i: [] for i in range(len(cells))}
    for row in spine["loss_strata"]:
        grouped[int(row["cell_index"])].append(SimpleNamespace(
            node_id=row["node_id"],
            step=row["step"],
            loss_intensity=row["loss_intensity"],
            deposition_mode_weights=json.loads(row["deposition_mode_weights_json"]),
            expected_recycle_count=row["expected_recycle_count"],
            expected_repair_count=row["expected_repair_count"],
            expected_source_entropy=row["expected_source_entropy"],
            expected_field_crossings=row["expected_field_crossings"],
            expected_physical_crossings=row["expected_physical_crossings"],
            route_distance_from_origin_km=row["route_distance_from_origin_km"],
            field_mix=json.loads(row["field_mix_json"]),
        ))
    return [SimpleNamespace(production_cell=cell, loss_strata=grouped[i]) for i, cell in enumerate(cells)]


def _load_hydro(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    resolved = path if path.is_absolute() else PROJECT_ROOT / path
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    rows = payload.get("features", payload) if isinstance(payload, Mapping) else payload
    if not isinstance(rows, list):
        raise ValueError("hydro evidence must be a list or {'features': [...]} object")
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def build_phase05_smoke(
    hypothesis: Mapping[str, Any],
    *,
    out_path: Path,
    world_seed: int = 1300,
    cells: int = DEFAULT_CELLS,
    nodes: int = DEFAULT_NODES,
    workshops: int = DEFAULT_WORKSHOPS,
    steps: int = DEFAULT_STEPS,
    hydro_evidence: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    summary, world, lineages = v3_smoke._build_smoke_phase02_components(
        hypothesis,
        out_path=out_path,
        world_seed=world_seed,
        workshop_count=workshops,
        intensity_steps=steps,
        target_geography_nodes=nodes,
        production_cell_limit=cells,
    )
    summary, chemistry, metallurgy_summary = v3_smoke._append_smoke_phase03(
        summary,
        world,
        lineages,
        out_path=out_path,
        world_seed=world_seed,
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
        phase01_spine_sha256=str(summary["spine_sha256"]),
        phase02_biography_sha256=str(summary["metal_biography"]["biography_sha256"]),
        phase03_metallurgy_sha256=str(metallurgy_summary["metallurgy_sha256"]),
    )
    workshop_read = v3_workshop_netcdf.read_workshop_layer(out_path)
    if workshop_read["workshop_sha256"] != workshop_summary["workshop_sha256"]:
        raise RuntimeError("phase-05 smoke phase-04 workshop roundtrip failed")

    spine = v3_netcdf.read_spine_master(out_path)
    reports = _reports_from_spine(spine)
    layer = phase05.materialize_phase05(
        world,
        reports,
        lineages,
        world_seed=world_seed,
        supplied_hydro_evidence=hydro_evidence,
    )
    phase05_summary = v3_phase05_netcdf.append_phase05(
        out_path,
        layer=layer,
        world_seed=world_seed,
        phase01_spine_sha256=str(summary["spine_sha256"]),
        phase02_biography_sha256=str(summary["metal_biography"]["biography_sha256"]),
        phase03_metallurgy_sha256=str(metallurgy_summary["metallurgy_sha256"]),
        phase04_workshop_sha256=str(workshop_summary["workshop_sha256"]),
    )
    read = v3_phase05_netcdf.read_phase05(out_path)

    particle_ids = {str(lineage.particle_id) for lineage in lineages}
    deposition_ids = {row["particle_id"] for row in read["deposition_assignments"]}
    archaeology_ids = {row["particle_id"] for row in read["archaeology"]}
    pool_ids = {row["deposition_pool_id"] for row in read["deposition_pools"]}
    realization_ids = {row["realization_id"] for row in read["hydro_realization"]}
    waterfall_ok = all(
        0.0 <= row["recorded_weight"] <= row["discovery_weight"] <= row["survival_weight"] <= row["represented_loss_weight"] + 1e-12
        for row in read["archaeology"]
    )
    if deposition_ids != particle_ids or archaeology_ids != particle_ids:
        raise RuntimeError("phase-05 smoke lost phase-02 particle identity")
    if any(row["deposition_pool_id"] not in pool_ids for row in read["deposition_assignments"]):
        raise RuntimeError("phase-05 smoke deposition pool linkage failed")
    if len(realization_ids) > 1:
        raise RuntimeError("phase-05 smoke produced more than one hydro realization")
    if not waterfall_ok:
        raise RuntimeError("phase-05 smoke archaeology waterfall is not monotone")

    return {
        **summary,
        "latest_phase": v3_phase05_netcdf.V3_PHASE05_PHASE,
        "source_metallurgy": metallurgy_summary,
        "workshop_ecology": workshop_summary,
        "hydro_exchange_deposition": phase05_summary,
        "roundtrip": {
            "phase01_spine_hash_equal": spine["spine_sha256"] == summary["spine_sha256"],
            "phase02_biography_hash_link_equal": read["phase02_biography_sha256"] == summary["metal_biography"]["biography_sha256"],
            "phase03_metallurgy_hash_link_equal": read["phase03_metallurgy_sha256"] == metallurgy_summary["metallurgy_sha256"],
            "phase04_workshop_hash_link_equal": read["phase04_workshop_sha256"] == workshop_summary["workshop_sha256"],
            "phase05_hash_equal": read["phase05_sha256"] == phase05_summary["phase05_sha256"],
            "phase05_particles_equal_phase02": deposition_ids == particle_ids == archaeology_ids,
            "one_hydro_realization": len(realization_ids) <= 1,
            "deposition_pool_links_closed": True,
            "shared_deposition_pools_exercised": phase05_summary["shared_deposition_pools"],
            "external_exchange_tails_exercised": phase05_summary["external_exchange_tails"],
            "survival_discovery_record_monotone": waterfall_ok,
            "hydro_evidence_status": read["hydro_evidence_status"],
            "exchange_status": read["exchange_status"],
            "observation_status": read["observation_status"],
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the fast real Atolia v3 phase-05 smoke build")
    ap.add_argument("--hypothesis", type=Path, default=Path("hypotheses/atolia_atesis_1800_1000_v0.json"))
    ap.add_argument("--out", type=Path, default=Path("cache/atolia_v3_phase05_smoke.nc"))
    ap.add_argument("--world-seed", type=int, default=1300)
    ap.add_argument("--cells", type=int, default=DEFAULT_CELLS)
    ap.add_argument("--nodes", type=int, default=DEFAULT_NODES)
    ap.add_argument("--workshops", type=int, default=DEFAULT_WORKSHOPS)
    ap.add_argument("--steps", type=int, default=DEFAULT_STEPS)
    ap.add_argument("--hydro-evidence", type=Path, default=None)
    args = ap.parse_args()

    hypothesis_path = args.hypothesis if args.hypothesis.is_absolute() else PROJECT_ROOT / args.hypothesis
    out_path = args.out if args.out.is_absolute() else PROJECT_ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    hypothesis = json.loads(hypothesis_path.read_text(encoding="utf-8"))
    result = build_phase05_smoke(
        hypothesis,
        out_path=out_path,
        world_seed=args.world_seed,
        cells=args.cells,
        nodes=args.nodes,
        workshops=args.workshops,
        steps=args.steps,
        hydro_evidence=_load_hydro(args.hydro_evidence),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    host_emit = globals().get("emit")
    if callable(host_emit):
        host_emit(result)


if __name__ == "__main__":
    main()
