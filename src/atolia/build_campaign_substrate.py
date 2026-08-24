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


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the shared latent campaign substrate once for all players")
    ap.add_argument("--hypothesis", type=Path, default=Path("hypotheses/atolia_atesis_1800_1000_v0.json"))
    ap.add_argument("--world-seed", type=int, default=cache.DEFAULT_CANONICAL_WORLD_SEED)
    ap.add_argument("--workshops", type=int, default=cache.DEFAULT_WORKSHOPS)
    ap.add_argument("--steps", type=int, default=cache.DEFAULT_STEPS)
    ap.add_argument("--out", type=Path, default=cache.DEFAULT_CACHE_PATH)
    args = ap.parse_args()

    hypothesis = json.loads(args.hypothesis.read_text(encoding="utf-8"))
    print(f"building shared world seed={args.world_seed} workshops={args.workshops}", file=sys.stderr, flush=True)
    world = archaeology.TemporalFieldArchaeologicalWorld(hypothesis, seed=args.world_seed)
    world.build(workshop_count=args.workshops)
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
    path = cache.save_payload(payload, args.out)
    print(json.dumps({
        "cache": str(path),
        "fingerprint": cache.payload_fingerprint(payload),
        "loss_strata": len(strata),
        "flow": flow,
    }, indent=2))


if __name__ == "__main__":
    main()
