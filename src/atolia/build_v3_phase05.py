#!/usr/bin/env python3
from __future__ import annotations

"""Build Atolia v3 phases 01-05 into one developer master NetCDF."""

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_v3_master as build
import campaign_substrate_cache as cache
import v3_hydro_exchange_deposition as phase05
import v3_phase05_netcdf
import v3_workshop_ecology
import v3_workshop_netcdf


def _load_hydro(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("features", payload) if isinstance(payload, Mapping) else payload
    if not isinstance(rows, list):
        raise ValueError("hydro evidence must be a list or {'features': [...]} object")
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def build_master_with_phase05(
    hypothesis: Mapping[str, Any],
    *,
    out_path: Path,
    world_seed: int,
    workshop_count: int,
    intensity_steps: int,
    target_geography_nodes: int | None = None,
    supplied_hydro_evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    result = build.run_v1_propagation_spine(
        hypothesis,
        world_seed=world_seed,
        workshop_count=workshop_count,
        intensity_steps=intensity_steps,
        target_geography_nodes=target_geography_nodes,
    )
    spine_summary = build._write_phase01(
        result,
        hypothesis,
        out_path=out_path,
        world_seed=world_seed,
        workshop_count=workshop_count,
        intensity_steps=intensity_steps,
        target_geography_nodes=target_geography_nodes,
    )
    lineages, biography_summary = build._append_phase02(
        result,
        out_path=out_path,
        world_seed=world_seed,
        spine_summary=spine_summary,
    )
    chemistry, metallurgy_summary = build._append_phase03(
        result,
        lineages,
        out_path=out_path,
        world_seed=world_seed,
        spine_summary=spine_summary,
        biography_summary=biography_summary,
    )

    workshop_layer = v3_workshop_ecology.materialize_workshop_layer(
        result.world,
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

    layer = phase05.materialize_phase05(
        result.world,
        result.reports,
        lineages,
        world_seed=world_seed,
        supplied_hydro_evidence=supplied_hydro_evidence or (),
    )
    phase05_summary = v3_phase05_netcdf.append_phase05(
        out_path,
        layer=layer,
        world_seed=world_seed,
        phase01_spine_sha256=str(spine_summary["spine_sha256"]),
        phase02_biography_sha256=str(biography_summary["biography_sha256"]),
        phase03_metallurgy_sha256=str(metallurgy_summary["metallurgy_sha256"]),
        phase04_workshop_sha256=str(workshop_summary["workshop_sha256"]),
    )
    return {
        **spine_summary,
        "latest_phase": v3_phase05_netcdf.V3_PHASE05_PHASE,
        "metal_biography": biography_summary,
        "source_metallurgy": metallurgy_summary,
        "workshop_ecology": workshop_summary,
        "hydro_exchange_deposition": phase05_summary,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Build Atolia v3 through phase 05")
    ap.add_argument("--hypothesis", type=Path, default=Path("hypotheses/atolia_atesis_1800_1000_v0.json"))
    ap.add_argument("--world-seed", type=int, default=cache.DEFAULT_CANONICAL_WORLD_SEED)
    ap.add_argument("--workshops", type=int, default=cache.DEFAULT_WORKSHOPS)
    ap.add_argument("--steps", type=int, default=cache.DEFAULT_STEPS)
    ap.add_argument("--target-geography-nodes", type=int, default=None)
    ap.add_argument("--hydro-evidence", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=Path("cache/atolia_master_v3.nc"))
    args = ap.parse_args()

    hypothesis = json.loads(args.hypothesis.read_text(encoding="utf-8"))
    summary = build_master_with_phase05(
        hypothesis,
        out_path=args.out,
        world_seed=args.world_seed,
        workshop_count=args.workshops,
        intensity_steps=args.steps,
        target_geography_nodes=args.target_geography_nodes,
        supplied_hydro_evidence=_load_hydro(args.hydro_evidence),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
