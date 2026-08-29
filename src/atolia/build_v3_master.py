#!/usr/bin/env python3
from __future__ import annotations

"""Build the Atolia v3 phase-01 developer master from the exact v1 propagation spine.

This phase is intentionally conservative. It reuses the canonical v1 sequence:

    TemporalFieldArchaeologicalWorld(...)
    -> world.build(...)
    -> intensity_circulation.propagate_world(...)

and stores those outputs losslessly in a small NetCDF checkpoint. No v2 direct
particle simulator, moment reconstruction, metal-biography transplant, or player
sampling is performed here.
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
import v3_netcdf


DEFAULT_V3_SPINE_PATH = Path("cache/atolia_master_v3_spine.nc")


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


def build_master(
    hypothesis: Mapping[str, Any],
    *,
    out_path: Path,
    world_seed: int,
    workshop_count: int,
    intensity_steps: int,
    target_geography_nodes: int | None = None,
) -> dict[str, Any]:
    result = run_v1_propagation_spine(
        hypothesis,
        world_seed=world_seed,
        workshop_count=workshop_count,
        intensity_steps=intensity_steps,
        target_geography_nodes=target_geography_nodes,
    )
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
            result.flow_summary.get("model_version", intensity.INTENSITY_MODEL_VERSION)
        ),
    })
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Build the Atolia v3 phase-01 master from the exact v1 "
            "TemporalFieldArchaeologicalWorld -> intensity.propagate_world spine"
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
    ap.add_argument("--out", type=Path, default=DEFAULT_V3_SPINE_PATH)
    ap.add_argument(
        "--target-geography-nodes",
        type=int,
        default=None,
        help=(
            "Development/micro-world geography target. Omit for the canonical "
            "v1 geography target."
        ),
    )
    args = ap.parse_args()

    hypothesis = json.loads(args.hypothesis.read_text(encoding="utf-8"))
    print(
        "v3 phase 01: building exact v1 propagation spine "
        f"seed={args.world_seed} workshops={args.workshops} steps={args.steps}",
        file=sys.stderr,
        flush=True,
    )
    summary = build_master(
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
