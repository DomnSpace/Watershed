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
import archaeology_temporal_world as archaeology
import acquisition_campaign as campaign
import procedural_sampler as procedural

PACKAGE_SCHEMA = "dr-corrosion.archaeometallurgy.player-package.v5"
GENERATOR_VERSION = "archaeometallurgy-poari-v5-acquisition-campaign"
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


def build_player_package(*, player_key: str, hypothesis_path: Path = DEFAULT_HYPOTHESIS,
                         workshops: int = 3200, catalogue_cap: int = 30000,
                         generate_validation_catalogue: bool = False,
                         include_debug: bool = False) -> Dict[str, Any]:
    """Generate one 300-find career from acquisition actions over latent intensity.

    The ordinary 30k archaeological catalogue is deliberately NOT the player-career
    candidate pool. It can still be generated independently with
    generate_validation_catalogue=True for model validation/debugging.
    """
    master_seed = seed_from_player_key(player_key)
    seeds = procedural.SeedBundle.from_master(master_seed)
    hypothesis = json.loads(hypothesis_path.read_text(encoding="utf-8"))
    world = archaeology.TemporalFieldArchaeologicalWorld(hypothesis, seed=seeds.world_seed)
    world.build(workshop_count=workshops)
    world.rng = __import__("numpy").random.default_rng(seeds.archaeology_seed)

    validation_generation = None
    if generate_validation_catalogue:
        validation_generation = world.generate_archaeological_catalogue(max_materialized=catalogue_cap)

    sampler = campaign.AcquisitionCampaignSampler(world, seeds)
    # prepare_candidates now builds the latent intensity/loss opportunity space; it
    # does not read world.catalogue_truth or select from the validation 30k.
    sampler.prepare_candidates()
    objects = sampler.sample()
    analyses = sampler.player_analyses()
    report = sampler.career_report()

    selected_rows = [sampler.selected_by_slot[slot.index].row for slot in sampler.slots]
    selected_summary = world.catalogue_stage_summary(selected_rows)
    selected_summary["by_level"] = {
        str(level): world.catalogue_stage_summary([
            sampler.selected_by_slot[slot.index].row for slot in sampler.slots if slot.level == level
        ]) for level in range(1, 31)
    }

    payload: Dict[str, Any] = {
        "meta": {
            "schema": PACKAGE_SCHEMA,
            "generator_version": GENERATOR_VERSION,
            "package_id": package_id(player_key),
            "object_count": len(objects),
            "levels": 30,
            "objects_per_level": 10,
            "reproducible": True,
            "player_key_hash": hashlib.sha256(player_key.strip().encode("utf-8")).hexdigest()[:16],
            "world_seed_fingerprint": hashlib.sha256(str(seeds.world_seed).encode("utf-8")).hexdigest()[:12],
            "physical_artifact_truth": True,
            "tool_specific_measurement_error": True,
            "career_crystallization": campaign.ACQUISITION_VERSION,
            "career_source": "latent loss/intensity world",
            "validation_catalogue_used_for_selection": False,
        },
        "objects": objects,
        "analyses": analyses,
        "curriculum": contract_v1.as_jsonable(),
        "career_schedule": [
            {
                "regime": r.name, "start": r.start, "end": r.end, "p": r.p,
                "description": r.description,
            } for r in campaign.REGIMES
        ],
    }
    if include_debug:
        payload["debug"] = {
            "master_seed": master_seed,
            "seed_bundle": {
                "world": seeds.world_seed, "archaeology": seeds.archaeology_seed,
                "career": seeds.career_seed, "measurement": seeds.measurement_seed,
            },
            "geography": world.geography_report,
            "validation_catalogue_generation": validation_generation,
            "career_selected_summary": selected_summary,
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
    parser = argparse.ArgumentParser(
        description="Generate one reproducible 300-object archaeology career through stray finds, a random hoard, and POARI-routed digs."
    )
    parser.add_argument("player_key", help="Opaque player/account/save key. Same key + generator version => same career.")
    parser.add_argument("--hypothesis", default=str(DEFAULT_HYPOTHESIS))
    parser.add_argument("--out", default="out/player_game.json")
    parser.add_argument("--workshops", type=int, default=3200)
    parser.add_argument("--catalogue-cap", type=int, default=30000,
                        help="Size of optional validation catalogue; not used to select the 300 career finds")
    parser.add_argument("--validation-catalogue", action="store_true",
                        help="Also generate the independent ~30k validation archaeology")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    payload = build_player_package(
        player_key=args.player_key,
        hypothesis_path=Path(args.hypothesis),
        workshops=args.workshops,
        catalogue_cap=args.catalogue_cap,
        generate_validation_catalogue=args.validation_catalogue,
        include_debug=args.debug,
    )
    write_package(payload, Path(args.out))
    print(json.dumps(payload["meta"], indent=2))


if __name__ == "__main__":
    main()
