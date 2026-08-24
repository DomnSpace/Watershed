#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import archaeology_field_world as afw
import intensity_circulation as intensity
import rare_event_materializer as materializer


def main() -> None:
    ap = argparse.ArgumentParser(description="Run aggregate hidden economy -> rich rare archaeological biography diagnostics")
    ap.add_argument("--hypothesis", type=Path, default=Path("hypotheses/atolia_atesis_1800_1000_v0.json"))
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--steps", type=int, default=28)
    ap.add_argument("--candidates", type=int, default=100000)
    ap.add_argument("--workshops", type=int, default=3200)
    ap.add_argument("--out", type=Path, default=Path("output/intensity_world_summary.json"))
    ap.add_argument("--candidate-out", type=Path, default=None,
                    help="Optional developer-only JSONL dump including physical artifact truth")
    args = ap.parse_args()

    hypothesis = json.loads(args.hypothesis.read_text(encoding="utf-8"))
    world = afw.FieldArchaeologicalObservationWorld(hypothesis, seed=args.seed)
    world.build(workshop_count=args.workshops)
    reports, flow = intensity.propagate_world(world, max_steps=args.steps)
    candidates, mat = materializer.materialize_biographies(world, reports, args.candidates, args.seed)

    by_class = defaultdict(float); by_region = defaultdict(float); by_mode = defaultdict(float)
    for row in candidates:
        w = float(row["importance_weight"])
        by_class[row["production_cell_truth"]["object_class"]] += w
        by_region[row["deposition_truth"]["region"]] += w
        by_mode[row["deposition_truth"]["mode"]] += w

    summary = {
        "flow": flow, "materialization": mat,
        "physical_world": {"sources": len(world.sources), "workshops": len(world.workshops),
                           "guilds": len(getattr(world, "guilds", {}))},
        "weighted_candidate_distribution": {
            "object_class": dict(sorted(by_class.items())),
            "deposition_region": dict(sorted(by_region.items())),
            "deposition_mode": dict(sorted(by_mode.items())),
        },
        "carrier": getattr(world, "geography_report", None),
        "warning": "Developer truth diagnostic; never include this file in player package.",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if args.candidate_out:
        args.candidate_out.parent.mkdir(parents=True, exist_ok=True)
        with args.candidate_out.open("w", encoding="utf-8") as fh:
            for row in candidates:
                fh.write(json.dumps(row, separators=(",", ":")) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
