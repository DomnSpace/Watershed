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
import cached_acquisition_campaign as cached_campaign
import campaign_substrate_cache as substrate_cache
import ecmwf_acquisition_campaign as ecmwf_campaign
import procedural_sampler as procedural

PACKAGE_SCHEMA = "dr-corrosion.archaeometallurgy.player-package.v8"
GENERATOR_VERSION = "archaeometallurgy-poari-v8-v2-metal-lineage-runtime"
DEFAULT_HYPOTHESIS = Path("hypotheses/atolia_atesis_1800_1000_v0.json")
DEFAULT_RUNTIME = ecmwf_campaign.DEFAULT_RUNTIME
V2_RUNTIME_SCHEMA = "atolia.ecmwf-runtime.v2-metal-lineage"


def seed_from_player_key(player_key: str, namespace: str = "dr-corrosion-archaeometallurgy-v1") -> int:
    clean = player_key.strip()
    if not clean:
        raise ValueError("player_key must not be empty")
    digest = hashlib.sha256(f"{namespace}:{clean}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & 0x7FFFFFFF


def package_id(player_key: str) -> str:
    digest = hashlib.sha256(f"{GENERATOR_VERSION}:{player_key.strip()}".encode("utf-8")).hexdigest()
    return digest[:20]


def _player_seeds(player_key: str, canonical_world_seed: int) -> procedural.SeedBundle:
    # Every player explores the same calibrated hidden world. Only archaeology draw,
    # career route and measurement noise vary by player key.
    derived = procedural.SeedBundle.from_master(seed_from_player_key(player_key))
    return procedural.SeedBundle(
        world_seed=int(canonical_world_seed),
        archaeology_seed=derived.archaeology_seed,
        career_seed=derived.career_seed,
        measurement_seed=derived.measurement_seed,
    )


def _runtime_world_metadata(runtime_path: Path) -> tuple[int, int, str]:
    """Read canonical world metadata without deserializing the latent field."""
    from netCDF4 import Dataset

    with Dataset(runtime_path, "r") as ds:
        schema = str(getattr(ds, "schema", ""))
        if schema not in {ecmwf_campaign.RUNTIME_SCHEMA, V2_RUNTIME_SCHEMA}:
            raise ValueError(f"not a supported Atolia runtime: schema={schema!r}")
        world_seed = int(getattr(ds, "world_seed", substrate_cache.DEFAULT_CANONICAL_WORLD_SEED))
        workshop_count = int(getattr(ds, "workshop_count", substrate_cache.DEFAULT_WORKSHOPS))
    return world_seed, workshop_count, schema


def build_player_package(*, player_key: str, hypothesis_path: Path = DEFAULT_HYPOTHESIS,
                         workshops: int = substrate_cache.DEFAULT_WORKSHOPS,
                         catalogue_cap: int = 30000,
                         generate_validation_catalogue: bool = False,
                         include_debug: bool = False,
                         runtime_path: Path = DEFAULT_RUNTIME,
                         substrate_path: Path = substrate_cache.DEFAULT_CACHE_PATH,
                         allow_legacy_json_cache: bool = False,
                         allow_slow_build: bool = False) -> Dict[str, Any]:
    """Generate one deterministic 300-find career from a compact Atolia runtime.

    The shipping v2 path reads weighted metal-lineage profiles directly from the
    grouped NetCDF product.  Exact terminal ``/states`` rows are not required and
    propagation is never rerun.  The v1 flat ECMWF and explicit developer legacy
    paths remain available for reproducibility.
    """
    hypothesis = json.loads(hypothesis_path.read_text(encoding="utf-8"))
    runtime_path = Path(runtime_path)
    substrate_path = Path(substrate_path)
    substrate = None
    runtime_schema: str | None = None

    if runtime_path.exists():
        canonical_world_seed, workshops, runtime_schema = _runtime_world_metadata(runtime_path)
        if runtime_schema == V2_RUNTIME_SCHEMA:
            # Installs the v2 2000--1000 BCE object chronology before the shared
            # structural world is built. No simulation is rerun here.
            import v2_config
            v2_config.install_v2_object_chronology()
            substrate_source = "v2_metal_lineage_netcdf_runtime"
        else:
            substrate_source = "ecmwf_netcdf_runtime"
    elif allow_legacy_json_cache and substrate_path.exists():
        substrate = substrate_cache.load_payload(substrate_path)
        substrate_cache.validate_payload(substrate, hypothesis)
        canonical_world_seed = int(substrate["world_seed"])
        workshops = int(substrate["workshop_count"])
        substrate_source = "legacy_json_cache"
    else:
        if not allow_slow_build:
            raise FileNotFoundError(
                f"Compact Atolia runtime not found: {runtime_path}. "
                "Developer compatibility may explicitly use --allow-legacy-json-cache."
            )
        canonical_world_seed = substrate_cache.DEFAULT_CANONICAL_WORLD_SEED
        substrate_source = "slow_build_legacy_cache"

    master_seed = seed_from_player_key(player_key)
    seeds = _player_seeds(player_key, canonical_world_seed)
    world = archaeology.TemporalFieldArchaeologicalWorld(hypothesis, seed=canonical_world_seed)
    world.build(workshop_count=workshops)
    world.rng = __import__("numpy").random.default_rng(seeds.archaeology_seed)

    validation_generation = None
    if generate_validation_catalogue:
        validation_generation = world.generate_archaeological_catalogue(max_materialized=catalogue_cap)

    if runtime_path.exists():
        if runtime_schema == V2_RUNTIME_SCHEMA:
            import v2_runtime_acquisition as v2_campaign
            sampler = v2_campaign.V2AcquisitionCampaignSampler(
                world,
                seeds,
                runtime_path=runtime_path,
            )
        else:
            sampler = ecmwf_campaign.ECMWFAcquisitionCampaignSampler(
                world,
                seeds,
                runtime_path=runtime_path,
            )
        sampler.prepare_candidates()
        substrate_fingerprint = sampler.runtime_fingerprint
    elif substrate is not None:
        sampler = cached_campaign.CachedAcquisitionCampaignSampler(world, seeds, substrate_payload=substrate)
        sampler.prepare_candidates()
        substrate_fingerprint = substrate_cache.payload_fingerprint(substrate)
    else:
        sampler = campaign.AcquisitionCampaignSampler(world, seeds)
        sampler.prepare_candidates()
        substrate = substrate_cache.build_payload(
            hypothesis=hypothesis,
            world_seed=canonical_world_seed,
            workshop_count=workshops,
            intensity_steps=sampler.intensity_steps,
            flow_summary=sampler.flow_summary,
            loss_strata=sampler.loss_strata,
            geography_report=getattr(world, "geography_report", {}),
        )
        substrate_cache.save_payload(substrate, substrate_path)
        substrate_fingerprint = substrate_cache.payload_fingerprint(substrate)

    try:
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
                "canonical_world_seed_fingerprint": hashlib.sha256(str(canonical_world_seed).encode("utf-8")).hexdigest()[:12],
                "physical_artifact_truth": True,
                "tool_specific_measurement_error": True,
                "career_crystallization": campaign.ACQUISITION_VERSION,
                "career_source": (
                    "shared weighted metal-lineage profile field"
                    if substrate_source == "v2_metal_lineage_netcdf_runtime"
                    else "shared latent loss/intensity field"
                ),
                "campaign_substrate_source": substrate_source,
                "campaign_substrate_fingerprint": substrate_fingerprint,
                "runtime_schema": runtime_schema,
                "runtime_materialization": (
                    "selected weighted v2 profile only"
                    if substrate_source == "v2_metal_lineage_netcdf_runtime"
                    else ("selected profile only" if substrate_source == "ecmwf_netcdf_runtime" else "legacy")
                ),
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
            debug_substrate: Dict[str, Any] = {
                "source": substrate_source,
                "fingerprint": substrate_fingerprint,
            }
            if substrate_source in {"ecmwf_netcdf_runtime", "v2_metal_lineage_netcdf_runtime"}:
                debug_substrate.update({
                    "runtime_path": str(runtime_path),
                    "runtime_schema": runtime_schema,
                    "runtime_profiles": int(sampler.runtime_store.profile_count),
                    "production_cells": int(sampler.runtime_store.cell_count),
                    "python_loss_strata_at_prepare": len(sampler.loss_strata),
                })
            elif substrate is not None:
                debug_substrate.update({
                    "path": str(substrate_path),
                    "loss_strata": len(substrate.get("loss_strata", [])),
                })
            payload["debug"] = {
                "master_seed": master_seed,
                "seed_bundle": {
                    "canonical_world": canonical_world_seed,
                    "archaeology": seeds.archaeology_seed,
                    "career": seeds.career_seed,
                    "measurement": seeds.measurement_seed,
                },
                "campaign_substrate": debug_substrate,
                "geography": world.geography_report,
                "validation_catalogue_generation": validation_generation,
                "career_selected_summary": selected_summary,
                "career_report": report,
                "truth": sampler.debug_truth(),
                "route_trace": sampler.debug_route_trace(),
                "guilds_truth": world.guild_truth(),
            }
        return payload
    finally:
        close_runtime = getattr(sampler, "close_runtime", None)
        if callable(close_runtime):
            close_runtime()


def write_package(payload: Dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate one reproducible 300-object archaeology career from a compact Atolia runtime."
    )
    parser.add_argument("player_key", help="Opaque player/account/save key. Same key + generator version => same career.")
    parser.add_argument("--hypothesis", default=str(DEFAULT_HYPOTHESIS))
    parser.add_argument("--out", default="out/player_game.json")
    parser.add_argument("--workshops", type=int, default=substrate_cache.DEFAULT_WORKSHOPS,
                        help="Developer fallback only; normal runtime runs use the runtime's workshop count")
    parser.add_argument("--runtime", default=str(DEFAULT_RUNTIME),
                        help="Compact shared Atolia runtime (.nc); normal shipping substrate")
    parser.add_argument("--substrate", default=str(substrate_cache.DEFAULT_CACHE_PATH),
                        help="Legacy developer gzip JSON substrate; ignored unless explicitly allowed")
    parser.add_argument("--allow-legacy-json-cache", action="store_true",
                        help="Developer compatibility only: use old gzip cache when the runtime is absent")
    parser.add_argument("--allow-slow-build", action="store_true",
                        help="Developer only: if no runtime/cache exists, rerun expensive propagation and save the legacy cache")
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
        runtime_path=Path(args.runtime),
        substrate_path=Path(args.substrate),
        allow_legacy_json_cache=args.allow_legacy_json_cache,
        allow_slow_build=args.allow_slow_build,
    )
    write_package(payload, Path(args.out))
    print(json.dumps(payload["meta"], indent=2))


if __name__ == "__main__":
    main()
