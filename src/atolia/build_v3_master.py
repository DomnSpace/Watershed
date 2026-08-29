#!/usr/bin/env python3
from __future__ import annotations

"""Build Atolia v3 from the exact v1 propagation spine.

Compatibility entry points stay explicit:

``build_master``
    phase 01 only: exact proven v1 propagation checkpoint.
``build_master_with_biography``
    phase 01 + phase 02 weighted metal genealogy.
``build_master_with_metallurgy``
    phase 01 + phase 02 + phase 03 conserved source/metallurgy state.

Phase 03 never reruns circulation or replaces the phase-02 batch graph. It adds
material inventories to the existing batches: elemental masses, Pb isotope
masses and source-resolved Pb carrier mass. Isotope ratios are derived views.
"""

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import archaeology_temporal_world as archaeology
import campaign_substrate_cache as cache
import intensity_circulation as intensity
import release_candidate_invariants as release_invariants
import v3_biography_netcdf
import v3_metal_biography
import v3_metallurgy_netcdf
import v3_netcdf
import v3_source_metallurgy


DEFAULT_V3_SPINE_PATH = Path("cache/atolia_master_v3_spine.nc")
DEFAULT_V3_MASTER_PATH = Path("cache/atolia_master_v3.nc")


@dataclass
class V1SpineResult:
    world: Any
    reports: Sequence[Any]
    flow_summary: Mapping[str, Any]
    release_invariants_version: str
    production_mass_error_kg: float


def canonical_hypothesis_sha256(hypothesis: Mapping[str, Any]) -> str:
    payload = json.dumps(
        hypothesis,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _production_mass_tolerance_kg(world: Any) -> float:
    total_copper_kg = sum(
        max(0.0, float(bundle.flux_tonnes.get(t, 0.0))) * 1000.0 * 0.48
        for bundle in world.bundles
        for t in world.time_slices
    )
    return max(1e-6, total_copper_kg * 1e-10)


def run_v1_propagation_spine(
    hypothesis: Mapping[str, Any],
    *,
    world_seed: int,
    workshop_count: int,
    intensity_steps: int,
    target_geography_nodes: int | None = None,
) -> V1SpineResult:
    """Execute the canonical v1 world-build and propagation sequence unchanged."""
    release_version = release_invariants.install()

    world_kwargs: dict[str, Any] = {}
    if target_geography_nodes is not None:
        world_kwargs["target_geography_nodes"] = int(target_geography_nodes)

    world = archaeology.TemporalFieldArchaeologicalWorld(
        hypothesis,
        seed=int(world_seed),
        **world_kwargs,
    )
    world.build(workshop_count=int(workshop_count))

    mass_error_kg = float(release_invariants.production_mass_error(world))
    tolerance_kg = _production_mass_tolerance_kg(world)
    if abs(mass_error_kg) > tolerance_kg:
        raise RuntimeError(
            "release production mass invariant failed: "
            f"{mass_error_kg:.9g} kg > tolerance {tolerance_kg:.9g} kg"
        )

    reports, flow_summary = intensity.propagate_world(
        world,
        max_steps=int(intensity_steps),
    )
    return V1SpineResult(
        world=world,
        reports=reports,
        flow_summary=flow_summary,
        release_invariants_version=str(release_version),
        production_mass_error_kg=mass_error_kg,
    )


def _write_phase01(
    result: V1SpineResult,
    hypothesis: Mapping[str, Any],
    *,
    out_path: Path,
    world_seed: int,
    workshop_count: int,
    intensity_steps: int,
    target_geography_nodes: int | None,
) -> dict[str, Any]:
    summary = v3_netcdf.write_spine_master(
        out_path,
        reports=result.reports,
        flow_summary=result.flow_summary,
        world_seed=world_seed,
        workshop_count=workshop_count,
        intensity_steps=intensity_steps,
        hypothesis_sha256=canonical_hypothesis_sha256(hypothesis),
        release_invariants_version=result.release_invariants_version,
        production_mass_error_kg=result.production_mass_error_kg,
        target_geography_nodes=target_geography_nodes,
    )
    summary.update({
        "release_invariants_version": result.release_invariants_version,
        "production_mass_error_kg": result.production_mass_error_kg,
        "propagation_model_version": str(
            result.flow_summary.get(
                "model_version",
                intensity.INTENSITY_MODEL_VERSION,
            )
        ),
    })
    return summary


def _append_phase02(
    result: V1SpineResult,
    *,
    out_path: Path,
    world_seed: int,
    spine_summary: Mapping[str, Any],
) -> tuple[list[v3_metal_biography.MetalLineage], dict[str, Any]]:
    lineages = v3_metal_biography.materialize_loss_lineages(
        result.world,
        result.reports,
        world_seed=world_seed,
    )
    biography_summary = v3_biography_netcdf.append_biography(
        out_path,
        lineages=lineages,
        world_seed=world_seed,
        phase01_spine_sha256=str(spine_summary["spine_sha256"]),
    )
    return lineages, biography_summary


def build_master(
    hypothesis: Mapping[str, Any],
    *,
    out_path: Path,
    world_seed: int,
    workshop_count: int,
    intensity_steps: int,
    target_geography_nodes: int | None = None,
) -> dict[str, Any]:
    """Build only the proven phase-01 lossless propagation checkpoint."""
    result = run_v1_propagation_spine(
        hypothesis,
        world_seed=world_seed,
        workshop_count=workshop_count,
        intensity_steps=intensity_steps,
        target_geography_nodes=target_geography_nodes,
    )
    return _write_phase01(
        result,
        hypothesis,
        out_path=out_path,
        world_seed=world_seed,
        workshop_count=workshop_count,
        intensity_steps=intensity_steps,
        target_geography_nodes=target_geography_nodes,
    )


def build_master_with_biography(
    hypothesis: Mapping[str, Any],
    *,
    out_path: Path,
    world_seed: int,
    workshop_count: int,
    intensity_steps: int,
    target_geography_nodes: int | None = None,
) -> dict[str, Any]:
    """Build phase 01 once, then append phase-02 metal/object biographies."""
    result = run_v1_propagation_spine(
        hypothesis,
        world_seed=world_seed,
        workshop_count=workshop_count,
        intensity_steps=intensity_steps,
        target_geography_nodes=target_geography_nodes,
    )
    spine_summary = _write_phase01(
        result,
        hypothesis,
        out_path=out_path,
        world_seed=world_seed,
        workshop_count=workshop_count,
        intensity_steps=intensity_steps,
        target_geography_nodes=target_geography_nodes,
    )
    _, biography_summary = _append_phase02(
        result,
        out_path=out_path,
        world_seed=world_seed,
        spine_summary=spine_summary,
    )
    return {
        **spine_summary,
        "latest_phase": v3_biography_netcdf.V3_BIOGRAPHY_PHASE,
        "metal_biography": biography_summary,
    }


def build_master_with_metallurgy(
    hypothesis: Mapping[str, Any],
    *,
    out_path: Path,
    world_seed: int,
    workshop_count: int,
    intensity_steps: int,
    target_geography_nodes: int | None = None,
) -> dict[str, Any]:
    """Build phases 01-03 once, preserving the exact v1 and phase-02 graphs."""
    result = run_v1_propagation_spine(
        hypothesis,
        world_seed=world_seed,
        workshop_count=workshop_count,
        intensity_steps=intensity_steps,
        target_geography_nodes=target_geography_nodes,
    )
    spine_summary = _write_phase01(
        result,
        hypothesis,
        out_path=out_path,
        world_seed=world_seed,
        workshop_count=workshop_count,
        intensity_steps=intensity_steps,
        target_geography_nodes=target_geography_nodes,
    )
    lineages, biography_summary = _append_phase02(
        result,
        out_path=out_path,
        world_seed=world_seed,
        spine_summary=spine_summary,
    )
    chemistry = v3_source_metallurgy.materialize_metallurgy(
        result.world,
        lineages,
    )
    metallurgy_summary = v3_metallurgy_netcdf.append_metallurgy(
        out_path,
        world=result.world,
        lineages=lineages,
        chemistry=chemistry,
        world_seed=world_seed,
        phase01_spine_sha256=str(spine_summary["spine_sha256"]),
        phase02_biography_sha256=str(biography_summary["biography_sha256"]),
    )
    return {
        **spine_summary,
        "latest_phase": v3_metallurgy_netcdf.V3_METALLURGY_PHASE,
        "metal_biography": biography_summary,
        "source_metallurgy": metallurgy_summary,
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Build the Atolia v3 exact v1 propagation spine and, by default, "
            "append phase-02 genealogy plus phase-03 source metallurgy."
        )
    )
    ap.add_argument(
        "--hypothesis",
        type=Path,
        default=Path("hypotheses/atolia_atesis_1800_1000_v0.json"),
    )
    ap.add_argument("--world-seed", type=int, default=cache.DEFAULT_CANONICAL_WORLD_SEED)
    ap.add_argument("--workshops", type=int, default=cache.DEFAULT_WORKSHOPS)
    ap.add_argument("--steps", type=int, default=cache.DEFAULT_STEPS)
    ap.add_argument("--out", type=Path, default=DEFAULT_V3_MASTER_PATH)
    ap.add_argument(
        "--target-geography-nodes",
        type=int,
        default=None,
        help=(
            "Development/micro-world geography target. Omit for the canonical "
            "v1 geography target."
        ),
    )
    phase_group = ap.add_mutually_exclusive_group()
    phase_group.add_argument(
        "--spine-only",
        action="store_true",
        help="Write the phase-01 checkpoint only.",
    )
    phase_group.add_argument(
        "--biography-only",
        action="store_true",
        help="Write phases 01-02 but do not append phase-03 metallurgy.",
    )
    args = ap.parse_args()

    hypothesis = json.loads(args.hypothesis.read_text(encoding="utf-8"))
    if args.spine_only:
        phase_label = "phase 01 spine only"
        builder = build_master
    elif args.biography_only:
        phase_label = "phase 02 metal biography"
        builder = build_master_with_biography
    else:
        phase_label = "phase 03 source metallurgy"
        builder = build_master_with_metallurgy

    print(
        f"v3 {phase_label}: seed={args.world_seed} "
        f"workshops={args.workshops} steps={args.steps}",
        file=sys.stderr,
        flush=True,
    )
    summary = builder(
        hypothesis,
        out_path=args.out,
        world_seed=args.world_seed,
        workshop_count=args.workshops,
        intensity_steps=args.steps,
        target_geography_nodes=args.target_geography_nodes,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
