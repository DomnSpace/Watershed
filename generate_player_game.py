from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent
ATOLIA = ROOT / "src" / "atolia"
if str(ATOLIA) not in sys.path:
    sys.path.insert(0, str(ATOLIA))

import campaign_substrate_cache as substrate_cache
import ecmwf_acquisition_campaign as ecmwf_campaign
import release_candidate_invariants as release_invariants
from player_game_package import build_player_package, write_package

DEFAULT_RUNTIME = ROOT / "cache" / "atolia_runtime_v1.nc"
DEFAULT_SUBSTRATE = ROOT / substrate_cache.DEFAULT_CACHE_PATH
ProgressCallback = Callable[[int, str], Any]


def _resolve(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else ROOT / value


def _progress(callback: ProgressCallback | None, percent: int, label: str) -> None:
    if callback is not None:
        callback(int(percent), str(label))


def generate_player_package(
    player_key: str,
    *,
    output_path: str | Path | None = None,
    workshops: int = substrate_cache.DEFAULT_WORKSHOPS,
    catalogue_cap: int = 30000,
    runtime: str | Path = DEFAULT_RUNTIME,
    substrate: str | Path = DEFAULT_SUBSTRATE,
    allow_legacy_json_cache: bool = False,
    allow_slow_build: bool = False,
    generate_validation_catalogue: bool = False,
    include_debug: bool = False,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Generate one deterministic 300-object player career from audited v1.

    The normal path is the compact ``atolia.ecmwf-runtime.v1`` NetCDF product.
    JSON substrate loading and slow world rebuilding remain explicit developer
    compatibility paths and are never selected implicitly.
    """
    clean_key = str(player_key).strip()
    if not clean_key:
        raise ValueError("player_key must not be empty")

    _progress(progress, 55, "PLAYER API START")
    release_version = release_invariants.install()
    _progress(progress, 57, "INSTALLING RELEASE INVARIANTS")

    runtime_path = _resolve(runtime)
    substrate_path = _resolve(substrate)
    _progress(progress, 60, "RESOLVING V1 RUNTIME")

    payload = build_player_package(
        player_key=clean_key,
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
    _progress(progress, 86, "PLAYER PACKAGE READY")

    payload["meta"]["release_invariants"] = release_version
    payload["meta"]["runtime_api"] = "atolia.ecmwf-player-api.v1"

    if output_path is not None:
        out = _resolve(output_path)
        write_package(payload, out)
        _progress(progress, 90, "PLAYER PACKAGE WRITTEN")

    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate one unique 300-object Dr. Corrosion archaeology career from the compact audited-v1 Atolia ECMWF runtime."
    )
    parser.add_argument("player_key", help="Stable opaque key for this player's archaeology career.")
    parser.add_argument("--out", default="out/player_game.json")
    parser.add_argument("--workshops", type=int, default=substrate_cache.DEFAULT_WORKSHOPS)
    parser.add_argument("--catalogue-cap", type=int, default=30000)
    parser.add_argument(
        "--runtime",
        default=str(DEFAULT_RUNTIME),
        help="Compact shared atolia.ecmwf-runtime.v1 NetCDF; normal player/install substrate.",
    )
    parser.add_argument(
        "--substrate",
        default=str(DEFAULT_SUBSTRATE),
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
    print(json.dumps({**payload["meta"], "output": str(_resolve(args.out))}, indent=2))


if __name__ == "__main__":
    main()
