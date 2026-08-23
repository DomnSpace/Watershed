from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import curriculum_contract_v1 as contract_v1
import poari_career_router_strict as poari
import procedural_sampler as procedural
import provenance_field_mediterranean as med

PACKAGE_SCHEMA = "dr-corrosion.archaeometallurgy.player-package.v1"
GENERATOR_VERSION = "archaeometallurgy-poari-v1"
DEFAULT_HYPOTHESIS = Path("hypotheses/atolia_atesis_1800_1000_v0.json")


def seed_from_player_key(player_key: str, namespace: str = "dr-corrosion-archaeometallurgy-v1") -> int:
    clean = player_key.strip()
    if not clean:
        raise ValueError("player_key must not be empty")
    digest = hashlib.sha256(f"{namespace}:{clean}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & 0x7FFFFFFF


def package_id(player_key: str) -> str:
    digest = hashlib.sha256(f"{GENERATOR_VERSION}:{player_key.strip()}".encode("utf-8")).hexdigest()
    return digest[:20]


def build_player_package(
    *,
    player_key: str,
    hypothesis_path: Path = DEFAULT_HYPOTHESIS,
    workshops: int = 3200,
    catalogue_cap: int = 30000,
    include_debug: bool = False,
) -> Dict[str, Any]:
    master_seed = seed_from_player_key(player_key)
    seeds = procedural.SeedBundle.from_master(master_seed)
    hypothesis = json.loads(hypothesis_path.read_text(encoding="utf-8"))

    world = med.MediterraneanProvenanceWorld(hypothesis, seed=seeds.world_seed)
    world.build(workshop_count=workshops)
    world.rng = __import__("numpy").random.default_rng(seeds.archaeology_seed)
    generation = world.generate_archaeological_catalogue(max_materialized=catalogue_cap)

    sampler = poari.StrictPOARICareerSampler(world, seeds)
    sampler.prepare_candidates()
    objects = sampler.sample()
    analyses = sampler.player_analyses()
    report = sampler.career_report()

    public_meta = {
        "schema": PACKAGE_SCHEMA,
        "generator_version": GENERATOR_VERSION,
        "package_id": package_id(player_key),
        "object_count": len(objects),
        "levels": 30,
        "objects_per_level": 10,
        "reproducible": True,
        "player_key_hash": hashlib.sha256(player_key.strip().encode("utf-8")).hexdigest()[:16],
        "world_seed_fingerprint": hashlib.sha256(str(seeds.world_seed).encode("utf-8")).hexdigest()[:12],
    }

    payload: Dict[str, Any] = {
        "meta": public_meta,
        "objects": objects,
        "analyses": analyses,
        "curriculum": contract_v1.as_jsonable(),
    }

    if include_debug:
        payload["debug"] = {
            "master_seed": master_seed,
            "seed_bundle": {
                "world": seeds.world_seed,
                "archaeology": seeds.archaeology_seed,
                "career": seeds.career_seed,
                "measurement": seeds.measurement_seed,
            },
            "generation": generation,
            "career_report": report,
            "truth": sampler.debug_truth(),
            "route_trace": sampler.debug_route_trace(),
            "guilds_truth": world.guild_truth(),
        }
    return payload


def write_package(payload: Dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate one reproducible 300-object player archaeology package from a player key.")
    parser.add_argument("player_key", help="Opaque player/account/save key. Same key + generator version => same career.")
    parser.add_argument("--hypothesis", default=str(DEFAULT_HYPOTHESIS))
    parser.add_argument("--out", default="out/player_game.json")
    parser.add_argument("--workshops", type=int, default=3200)
    parser.add_argument("--catalogue-cap", type=int, default=30000)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    payload = build_player_package(
        player_key=args.player_key,
        hypothesis_path=Path(args.hypothesis),
        workshops=args.workshops,
        catalogue_cap=args.catalogue_cap,
        include_debug=args.debug,
    )
    write_package(payload, Path(args.out))
    print(json.dumps(payload["meta"], indent=2))


if __name__ == "__main__":
    main()
