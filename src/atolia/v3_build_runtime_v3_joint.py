from __future__ import annotations

"""Final local R17 builder: repaired field plus packed joint representatives."""

import argparse
import json
from pathlib import Path
from typing import Any

import v3_build_runtime_v3 as core
import v3_build_runtime_v3_repaired_hydro_impl as repaired
import v3_r17_representatives as representatives


def build_runtime(**kwargs: Any) -> dict[str, Any]:
    result = repaired.build_runtime(**kwargs)
    packed = representatives.append_representatives(
        Path(kwargs["out_path"]),
        Path(kwargs["fragments_dir"]),
        read_fragment=core._read_fragment,
        semantic_fingerprint=core._semantic_runtime_fingerprint,
    )
    result.update(packed)
    out = Path(kwargs["out_path"])
    result["bytes"] = int(out.stat().st_size)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Build final joint-conditioned R17 from repaired Phase-08 fragments")
    parser.add_argument("--fragments", required=True, type=Path)
    parser.add_argument("--repair-certificate", required=True, type=Path)
    parser.add_argument("--cutoff-plan", required=True, type=Path)
    parser.add_argument("--hypothesis", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--expected-shards", type=int, default=580)
    parser.add_argument("--population-cells", type=int, default=37100)
    args = parser.parse_args()
    result = build_runtime(
        fragments_dir=args.fragments,
        cutoff_plan_path=args.cutoff_plan,
        repair_certificate_path=args.repair_certificate,
        hypothesis_path=args.hypothesis,
        out_path=args.out,
        expected_shards=args.expected_shards,
        population_cells=args.population_cells,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
