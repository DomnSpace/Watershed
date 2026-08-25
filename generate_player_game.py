from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ATOLIA = ROOT / "src" / "atolia"
if str(ATOLIA) not in sys.path:
    sys.path.insert(0, str(ATOLIA))

import campaign_substrate_cache as substrate_cache
import ecmwf_acquisition_campaign as ecmwf_campaign
import release_candidate_invariants as release_invariants
from player_game_package import build_player_package, write_package


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate one unique 300-object Dr. Corrosion archaeology career from the compact Atolia ECMWF runtime."
    )
    parser.add_argument("player_key", help="Stable opaque key for this player's archaeology career.")
    parser.add_argument("--out", default="out/player_game.json")
    parser.add_argument("--workshops", type=int, default=substrate_cache.DEFAULT_WORKSHOPS)
    parser.add_argument("--catalogue-cap", type=int, default=30000)
    parser.add_argument(
        "--runtime",
        default=str(ecmwf_campaign.DEFAULT_RUNTIME),
        help="Compact shared ECMWF runtime (.nc); normal player/install substrate.",
    )
    parser.add_argument(
        "--substrate",
        default=str(substrate_cache.DEFAULT_CACHE_PATH),
        help="Legacy developer gzip JSON substrate; ignored unless --allow-legacy-json-cache is set.",
    )
    parser.add_argument(
        "--allow-legacy-json-cache",
        action="store_true",
        help="Developer compatibility only: use the old gzip cache when the compact runtime is absent.",
    )
    parser.add_argument(
        "--allow-slow-build",
        action="store_true",
        help="Developer only: if no runtime/cache exists, rerun expensive propagation and persist the legacy cache.",
    )
    parser.add_argument(
        "--validation-catalogue",
        action="store_true",
        help="Developer only: additionally build the independent validation catalogue; never used to choose the 300 career finds.",
    )
    parser.add_argument("--debug", action="store_true", help="Developer only: include hidden truth and routing diagnostics.")
    args = parser.parse_args()

    release_version = release_invariants.install()
    runtime = Path(args.runtime)
    if not runtime.is_absolute():
        runtime = ROOT / runtime
    substrate = Path(args.substrate)
    if not substrate.is_absolute():
        substrate = ROOT / substrate

    payload = build_player_package(
        player_key=args.player_key,
        hypothesis_path=ROOT / "hypotheses" / "atolia_atesis_1800_1000_v0.json",
        workshops=args.workshops,
        catalogue_cap=args.catalogue_cap,
        generate_validation_catalogue=args.validation_catalogue,
        include_debug=args.debug,
        runtime_path=runtime,
        substrate_path=substrate,
        allow_legacy_json_cache=args.allow_legacy_json_cache,
        allow_slow_build=args.allow_slow_build,
    )
    payload["meta"]["release_invariants"] = release_version
    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    write_package(payload, out)
    print(json.dumps({**payload["meta"], "output": str(out)}, indent=2))


if __name__ == "__main__":
    main()
