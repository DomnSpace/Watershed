#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import archaeology_temporal_world as archaeology
import campaign_substrate_cache as cache
import intensity_circulation as intensity
import release_candidate_invariants as release_invariants


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the shared latent campaign substrate once for all players")
    ap.add_argument("--hypothesis", type=Path, default=Path("hypotheses/atolia_atesis_1800_1000_v0.json"))
    ap.add_argument("--world-seed", type=int, default=cache.DEFAULT_CANONICAL_WORLD_SEED)
    ap.add_argument("--workshops", type=int, default=cache.DEFAULT_WORKSHOPS)
    ap.add_argument("--steps", type=int, default=cache.DEFAULT_STEPS)
    ap.add_argument("--out", type=Path, default=cache.DEFAULT_CACHE_PATH)
    args = ap.parse_args()

    release_version = release_invariants.install()
    hypothesis = json.loads(args.hypothesis.read_text(encoding="utf-8"))
    print(f"building shared world seed={args.world_seed} workshops={args.workshops}", file=sys.stderr, flush=True)
    world = archaeology.TemporalFieldArchaeologicalWorld(hypothesis, seed=args.world_seed)
    world.build(workshop_count=args.workshops)
    mass_error_kg = release_invariants.production_mass_error(world)
    tolerance_kg = max(1e-6, sum(
        max(0.0, float(bundle.flux_tonnes.get(t, 0.0))) * 1000.0 * 0.48
        for bundle in world.bundles for t in world.time_slices
    ) * 1e-10)
    if abs(mass_error_kg) > tolerance_kg:
        raise RuntimeError(f"release production mass invariant failed: {mass_error_kg:.9g} kg")

    print(f"propagating latent intensity world for {args.steps} steps ...", file=sys.stderr, flush=True)
    reports, flow = intensity.propagate_world(world, max_steps=args.steps)
    strata = [s for r in reports for s in r.loss_strata if s.loss_intensity > 0]
    payload = cache.build_payload(
        hypothesis=hypothesis,
        world_seed=args.world_seed,
        workshop_count=args.workshops,
        intensity_steps=args.steps,
        flow_summary=flow,
        loss_strata=strata,
        geography_report=getattr(world, "geography_report", {}),
    )
    payload["release_invariants"] = release_version
    path = cache.save_payload(payload, args.out)
    print(json.dumps({
        "cache": str(path),
        "fingerprint": cache.payload_fingerprint(payload),
        "release_invariants": release_version,
        "production_mass_error_kg": mass_error_kg,
        "loss_strata": len(strata),
        "flow": flow,
    }, indent=2))


if __name__ == "__main__":
    main()
