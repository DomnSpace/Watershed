from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ATOLIA = ROOT / "src" / "atolia"
if str(ATOLIA) not in sys.path:
    sys.path.insert(0, str(ATOLIA))

from player_game_package import build_player_package, write_package


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate one unique 300-object Dr. Corrosion archaeology career.")
    parser.add_argument("player_key", help="Stable opaque key for this player's archaeology career.")
    parser.add_argument("--out", default="out/player_game.json")
    parser.add_argument("--workshops", type=int, default=3200)
    parser.add_argument("--catalogue-cap", type=int, default=30000)
    parser.add_argument("--debug", action="store_true", help="Developer only: include hidden truth and routing diagnostics.")
    args = parser.parse_args()

    payload = build_player_package(
        player_key=args.player_key,
        hypothesis_path=ROOT / "hypotheses" / "atolia_atesis_1800_1000_v0.json",
        workshops=args.workshops,
        catalogue_cap=args.catalogue_cap,
        include_debug=args.debug,
    )
    out = ROOT / args.out
    write_package(payload, out)
    print(json.dumps({**payload["meta"], "output": str(out)}, indent=2))


if __name__ == "__main__":
    main()
