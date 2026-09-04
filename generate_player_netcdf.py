from __future__ import annotations

"""Generate one deterministic private 300-object Dr. Corrosion NetCDF from R17."""

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent
ATOLIA = ROOT / "src" / "atolia"
if str(ATOLIA) not in sys.path:
    sys.path.insert(0, str(ATOLIA))

import v3_player_crystallizer as crystallizer
import v3_player_integrity as player_integrity
import v3_player_netcdf as player_netcdf


def generate_player_netcdf(
    player_key: str,
    *,
    runtime: Path,
    output_path: Path,
    progress_callback: Callable[[int, str], None] | None = None,
) -> dict[str, Any]:
    runtime = Path(runtime)
    output_path = Path(output_path)
    if not runtime.is_file():
        raise FileNotFoundError(runtime)
    state = crystallizer.crystallize(
        player_key,
        runtime_path=runtime,
        progress_callback=progress_callback,
    )
    player_netcdf.write_player_netcdf(
        state,
        output_path,
        progress_callback=progress_callback,
    )
    # v3_player_netcdf historically fingerprinted only the object header rows.
    # Replace that transient attribute with a digest of every hidden table and
    # simultaneously validate all foreign-key/chemistry/deposition invariants.
    return player_integrity.finalize_player_netcdf(output_path)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("player_key")
    ap.add_argument("--runtime", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("out/player_17.nc"))
    args = ap.parse_args()
    result = generate_player_netcdf(
        args.player_key,
        runtime=args.runtime,
        output_path=args.out,
    )
    print(json.dumps({k: v for k, v in result.items() if k != "object_ids"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
