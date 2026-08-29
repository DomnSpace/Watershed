from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
ATOLIA = ROOT / "src" / "atolia"
if str(ATOLIA) not in sys.path:
    sys.path.insert(0, str(ATOLIA))

import campaign_substrate_cache as substrate_cache
import release_candidate_invariants as release_invariants
from player_game_package import build_player_package, write_package

DEFAULT_RUNTIME = ROOT / "cache" / "atolia_runtime_v2.nc"


def _rooted(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else ROOT / value


def generate_player_package(
    player_key: str,
    *,
    output_path: str | Path | None = None,
    workshops: int = substrate_cache.DEFAULT_WORKSHOPS,
    catalogue_cap: int = 30000,
    runtime: str | Path = DEFAULT_RUNTIME,
    substrate: str | Path = substrate_cache.DEFAULT_CACHE_PATH,
    allow_legacy_json_cache: bool = False,
    allow_slow_build: bool = False,
    generate_validation_catalogue: bool = False,
    include_debug: bool = False,
) -> dict[str, Any]:
    """Generate one deterministic Dr. Corrosion player package in-process.

    This is the canonical application API as well as the implementation behind
    the CLI.  Callers pass a stable opaque ``player_key`` and, for normal
    releases, the compact ``cache/atolia_runtime_v2.nc`` substrate.  No CLI,
    subprocess, HTTP or debug layer is required to obtain the 300-object
    package.
    """
    player_key = str(player_key).strip()
    if not player_key:
        raise ValueError("player_key is required")

    release_version = release_invariants.install()
    runtime_path = _rooted(runtime)
    substrate_path = _rooted(substrate)

    payload = build_player_package(
        player_key=player_key,
        hypothesis_path=ROOT / "hypotheses" / "atolia_atesis_1800_1000_v0.json",
        workshops=int(workshops),
        catalogue_cap=int(catalogue_cap),
        generate_validation_catalogue=bool(generate_validation_catalogue),
        include_debug=bool(include_debug),
        runtime_path=runtime_path,
        substrate_path=substrate_path,
        allow_legacy_json_cache=bool(allow_legacy_json_cache),
        allow_slow_build=bool(allow_slow_build),
    )
    payload["meta"]["release_invariants"] = release_version

    if output_path is not None:
        write_package(payload, _rooted(output_path))
    return payload


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
        default=str(DEFAULT_RUNTIME),
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

    payload = generate_player_package(
        args.player_key,
        output_path=args.out,
        workshops=args.workshops,
        catalogue_cap=args.catalogue_cap,
        runtime=args.runtime,
        substrate=args.substrate,
        allow_legacy_json_cache=args.allow_legacy_json_cache,
        allow_slow_build=args.allow_slow_build,
        generate_validation_catalogue=args.validation_catalogue,
        include_debug=args.debug,
    )
    print(json.dumps({**payload["meta"], "output": str(_rooted(args.out))}, indent=2))


if __name__ == "__main__":
    main()
