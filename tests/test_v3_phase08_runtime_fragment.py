from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ATOLIA = ROOT / "src" / "atolia"
if str(ATOLIA) not in sys.path:
    sys.path.insert(0, str(ATOLIA))

import v3_phase08_runtime_fragment as phase08


def _certificate() -> dict:
    return {
        "world_build_id": "world-08",
        "canonical_hydro_realization_id": "hyr-canonical",
    }


def test_canonicalize_phase05_applies_exact_replay_actions_and_context() -> None:
    read05 = {
        "external_exchange": [
            {"particle_id": "p-update", "contact_probability": 0.1},
            {"particle_id": "p-remove", "contact_probability": 0.2},
        ],
        "deposition_assignments": [
            {
                "particle_id": pid,
                "hydro_realization_id": "hyr-minority",
                "hydro_context_score": 0.25,
                "deposition_pool_id": "pool-a",
            }
            for pid in ("p-update", "p-remove", "p-add", "p-absent")
        ],
        "deposition_pools": [
            {
                "deposition_pool_id": "pool-a",
                "node_id": "node-a",
                "hydro_realization_id": "hyr-minority",
                "hydro_context_score": 0.25,
            }
        ],
        "archaeology": [],
    }
    entry = {
        "chunk_ordinal": 507,
        "action": "PROJECT_MINORITY_TO_CANONICAL",
        "source_chunk_sha256": "chunk",
        "source_phase05_sha256": "phase05",
        "external_exchange_count_delta": 0,
        "replay_capsule_sha256": "capsule-hash",
    }
    canonical_external = {
        "p-update": {"particle_id": "p-update", "contact_probability": 0.11},
        "p-add": {"particle_id": "p-add", "contact_probability": 0.03},
    }
    capsule = {
        "schema": phase08.replay_capsule.SCHEMA,
        "world_build_id": "world-08",
        "chunk_ordinal": 507,
        "source_chunk_sha256": "chunk",
        "source_phase05_sha256": "phase05",
        "canonical_hydro_realization_id": "hyr-canonical",
        "replay_rows": [
            {
                "particle_id": "p-update",
                "external_action": "UPDATE",
                "canonical_external_row": canonical_external["p-update"],
                "canonical_hydro_context": 0.75,
            },
            {
                "particle_id": "p-remove",
                "external_action": "REMOVE",
                "canonical_external_row": None,
                "canonical_hydro_context": 0.75,
            },
            {
                "particle_id": "p-add",
                "external_action": "ADD",
                "canonical_external_row": canonical_external["p-add"],
                "canonical_hydro_context": 0.75,
            },
            {
                "particle_id": "p-absent",
                "external_action": "UNCHANGED_ABSENT",
                "canonical_external_row": None,
                "canonical_hydro_context": 0.75,
            },
        ],
        "pool_replacements": [
            {
                "deposition_pool_id": "pool-a",
                "canonical": {
                    "deposition_pool_id": "pool-a",
                    "node_id": "node-a",
                    "hydro_realization_id": "hyr-canonical",
                    "hydro_context_score": 0.75,
                },
            }
        ],
    }

    projected = phase08.canonicalize_phase05(
        read05,
        certificate=_certificate(),
        entry=entry,
        capsule=capsule,
    )

    external = {row["particle_id"]: row for row in projected["external_exchange"]}
    assert set(external) == {"p-update", "p-add"}
    assert external["p-update"]["contact_probability"] == 0.11
    assert external["p-add"]["contact_probability"] == 0.03
    assert all(
        row["hydro_realization_id"] == "hyr-canonical"
        for row in projected["deposition_assignments"]
    )
    assert all(
        row["hydro_context_score"] == 0.75
        for row in projected["deposition_assignments"]
    )
    assert projected["deposition_pools"][0]["hydro_realization_id"] == "hyr-canonical"
    assert projected["deposition_pools"][0]["hydro_context_score"] == 0.75


def _joint_inputs() -> dict:
    spine = {
        "cells": [
            {
                "cell_index": 10,
                "bundle_id": "secret-bundle",
                "bundle_family": "utilitarian",
                "object_class": "axe",
                "date_bc": 1450,
                "origin": "secret-origin",
                "destination": "secret-destination",
                "production_intensity": 4.0,
                "circulation_seed_intensity": 3.0,
                "recycle_mean": 1.5,
                "source_mix_json": json.dumps({"secret-source": 1.0}),
            }
        ],
        "loss_strata": [
            {
                "cell_index": 10,
                "cell_loss_index": 2,
                "node_id": "secret-loss-node",
                "step": 4,
                "loss_intensity": 0.8,
                "deposition_mode_weights_json": json.dumps({"hoard": 0.7, "river": 0.3}),
                "expected_recycle_count": 1.2,
                "expected_repair_count": 0.4,
                "expected_source_entropy": 0.2,
                "expected_field_crossings": 2.5,
                "expected_physical_crossings": 1.5,
                "route_distance_from_origin_km": 140.0,
                "field_mix_json": json.dumps({"secret-field": 1.0}),
            }
        ],
    }
    biography = {
        "particles": [
            {
                "particle_id": "secret-particle",
                "production_cell_index": 10,
                "cell_loss_index": 2,
                "metal_batch_id": "final-batch",
                "final_batch_index": 7,
                "represented_weight": 0.8,
                "metal_mass_kg": 1.1,
                "ore_distance_km": 40.0,
                "cumulative_metal_distance_km": 190.0,
                "current_object_distance_km": 80.0,
                "source_entropy": 0.3,
                "remelt_count": 1,
                "repair_count": 2,
            }
        ],
        "ancestry": [
            {
                "batch_index": 7,
                "source_id": "secret-source",
                "fraction": 1.0,
                "mass_kg": 1.1,
            }
        ],
    }
    metallurgy = {
        "chemistry_batches": [
            {
                "chemistry_batch_index": 3,
                "batch_id": "final-batch",
                "metal_mass_kg": 1.1,
                "pb_mass_kg": 0.02,
                "Pb206_204": 18.2,
                "Pb207_204": 15.6,
                "Pb208_204": 38.1,
            }
        ],
        "elements": [
            {"chemistry_batch_index": 3, "element": "Cu", "mass_fraction": 0.9},
            {"chemistry_batch_index": 3, "element": "Sn", "mass_fraction": 0.1},
        ],
        "source_pb": [
            {"chemistry_batch_index": 3, "source_id": "secret-source", "fraction_of_pb": 1.0}
        ],
    }
    workshop = {
        "operations": [
            {
                "particle_id": "secret-particle",
                "operation_type": "hammering",
                "localized": True,
                "capability": 0.8,
                "operator_skill": 0.7,
                "tool_fit": 0.9,
                "support_fit": 0.6,
                "thermal_fit": 0.5,
                "measurement_fit": 0.4,
                "material_fit": 0.85,
            }
        ]
    }
    phase05 = {
        "deposition_assignments": [
            {
                "particle_id": "secret-particle",
                "deposition_pool_id": "secret-pool",
                "mode": "hoard",
                "mode_probability": 0.7,
                "represented_weight": 0.8,
                "expected_field_crossings": 2.5,
                "expected_physical_crossings": 1.5,
                "hydro_context_score": 0.6,
            }
        ],
        "archaeology": [
            {
                "particle_id": "secret-particle",
                "represented_loss_weight": 0.8,
                "p_survival": 0.7,
                "survival_weight": 0.56,
                "p_discovery": 0.03,
                "discovery_weight": 0.0168,
                "p_record": 0.6,
                "recorded_weight": 0.01008,
            }
        ],
        "external_exchange": [
            {
                "particle_id": "secret-particle",
                "external_component_id": "external_eastern_med",
                "trigger": "source-or-bundle-tagged",
                "contact_probability": 0.03,
                "contact_intensity": 0.08,
                "represented_weight": 0.8,
            }
        ],
        "deposition_pools": [
            {
                "deposition_pool_id": "secret-pool",
                "member_count": 3,
                "represented_weight": 2.0,
            }
        ],
    }
    return {
        "spine": spine,
        "biography": biography,
        "metallurgy": metallurgy,
        "workshop": workshop,
        "phase05": phase05,
    }


def test_joint_profile_preserves_cross_phase_fields_without_raw_developer_ids() -> None:
    inputs = _joint_inputs()
    profiles = phase08.build_empirical_profiles(world_build_id="world-08", **inputs)
    assert len(profiles) == 1
    row = profiles[0]

    assert row["cell"]["object_class"] == "axe"
    assert row["loss"]["loss_intensity"] == 0.8
    assert row["lineage"]["represented_weight"] == 0.8
    assert row["chemistry"]["Pb206_204"] == 18.2
    assert row["operations"]["operation_types"] == [
        {"operation_type": "hammering", "count": 1}
    ]
    assert row["deposition"]["pool_member_count"] == 3
    assert row["archaeology"]["recorded_weight"] == 0.01008
    assert row["external_tail"]["component"] == "external_eastern_med"

    serialized = json.dumps(row, sort_keys=True)
    for forbidden in (
        "secret-particle",
        "secret-bundle",
        "secret-origin",
        "secret-destination",
        "secret-loss-node",
        "secret-source",
        "secret-pool",
        "secret-field",
    ):
        assert forbidden not in serialized


def test_tokens_and_fragment_hash_are_deterministic_and_world_scoped() -> None:
    a = phase08.anonymous_token("world-a", "source", "source-1")
    b = phase08.anonymous_token("world-a", "source", "source-1")
    c = phase08.anonymous_token("world-b", "source", "source-1")
    assert a == b
    assert a != c

    payload = {"schema": phase08.SCHEMA, "profiles": [{"x": 1.25}]}
    first = phase08.fragment_hash(payload)
    second = phase08.fragment_hash({**payload, "fragment_sha256": "ignored"})
    assert first == second
