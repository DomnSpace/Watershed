#!/usr/bin/env python3
from __future__ import annotations

"""Project one immutable Phase-07 shard into a Phase-08 empirical runtime fragment.

The physical NetCDF is opened read-only and validated through the ordinary
Phase-07 reader. Minority hydro shards are canonicalized in memory from the
Phase-07 repair certificate and, where required, the exact replay capsule.
No Phase-01..05 source hash is rewritten.
"""

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, Sequence

from netCDF4 import Dataset

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import v3_biography_netcdf
import v3_metallurgy_netcdf
import v3_netcdf
import v3_phase07_canonical as phase07
import v3_phase07_fragment as phase07_fragment
import v3_phase07_repair as phase07_repair
import v3_phase07_replay_capsule as replay_capsule


SCHEMA = "atolia-v3-phase08-empirical-runtime-fragment-v1"
HASH_POLICY = "lossless-json-float-roundtrip-v1"
PROJECTION_POLICY = (
    "weighted-joint-lineage-profile; canonical-phase07-hydro-overlay; "
    "exact-sparse-external-tail; world-scoped-developer-id-tokenization"
)
TOKEN_NAMESPACE = "atolia-v3-phase08-anonymous-id-v1"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fragment_hash(payload: Mapping[str, Any]) -> str:
    clean = dict(payload)
    clean.pop("fragment_sha256", None)
    return hashlib.sha256(_stable_json(clean).encode("utf-8")).hexdigest()


def anonymous_token(world_build_id: str, kind: str, raw_id: object) -> str:
    """Stable world-scoped token for developer identities.

    This is an anti-spoiler namespace boundary, not a cryptographic secrecy
    guarantee. The raw identifier is never written beside the token.
    """
    digest = hashlib.sha256(
        f"{TOKEN_NAMESPACE}|{world_build_id}|{kind}|{raw_id}".encode("utf-8")
    ).hexdigest()
    prefix = {
        "particle": "p",
        "node": "n",
        "bundle": "b",
        "source": "s",
        "pool": "d",
        "field": "f",
    }.get(str(kind), "x")
    return f"{prefix}_{digest[:20]}"


def _mean(rows: Sequence[Mapping[str, Any]], field: str) -> float:
    if not rows:
        return 0.0
    values = [float(row[field]) for row in rows]
    return float(math.fsum(values) / len(values))


def _json_weights(raw: str | Mapping[str, Any]) -> dict[str, float]:
    value = json.loads(raw) if isinstance(raw, str) else dict(raw)
    return {str(key): float(value[key]) for key in sorted(value)}


def _tokenized_weights(
    raw: str | Mapping[str, Any], *, world_build_id: str, kind: str
) -> list[dict[str, Any]]:
    weights = _json_weights(raw)
    return [
        {
            "token": anonymous_token(world_build_id, kind, key),
            "weight": float(weights[key]),
        }
        for key in sorted(weights)
        if float(weights[key]) != 0.0
    ]


def _certificate_without_hash(certificate: Mapping[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(dict(certificate))
    payload.pop("certificate_sha256", None)
    return payload


def validate_certificate(certificate: Mapping[str, Any]) -> None:
    if certificate.get("schema") != phase07_repair.CERTIFICATE_SCHEMA:
        raise RuntimeError(f"unsupported Phase-07 repair certificate schema: {certificate.get('schema')!r}")
    supplied = str(certificate.get("certificate_sha256", ""))
    expected = phase07_fragment._fragment_hash(_certificate_without_hash(certificate))
    if not supplied or supplied != expected:
        raise RuntimeError("Phase-07 repair certificate hash mismatch")


def certificate_entry(certificate: Mapping[str, Any], ordinal: int) -> dict[str, Any]:
    rows = [
        dict(row)
        for row in certificate.get("entries", [])
        if int(row["chunk_ordinal"]) == int(ordinal)
    ]
    if len(rows) != 1:
        raise RuntimeError(
            f"expected exactly one Phase-07 repair certificate entry for ordinal {ordinal}; found {len(rows)}"
        )
    return rows[0]


def _validate_capsule_for_entry(
    capsule: Mapping[str, Any],
    *,
    certificate: Mapping[str, Any],
    entry: Mapping[str, Any],
    ordinal: int,
) -> None:
    if capsule.get("schema") != replay_capsule.SCHEMA:
        raise RuntimeError("unsupported Phase-07 replay capsule schema")
    expected = {
        "world_build_id": str(certificate["world_build_id"]),
        "chunk_ordinal": str(int(ordinal)),
        "source_chunk_sha256": str(entry["source_chunk_sha256"]),
        "source_phase05_sha256": str(entry["source_phase05_sha256"]),
        "canonical_hydro_realization_id": str(certificate["canonical_hydro_realization_id"]),
    }
    for field, value in expected.items():
        if str(capsule.get(field)) != value:
            raise RuntimeError(
                f"Phase-07 replay capsule mismatch for {field}: {capsule.get(field)!r} != {value!r}"
            )


def canonicalize_phase05(
    read05: Mapping[str, Any],
    *,
    certificate: Mapping[str, Any],
    entry: Mapping[str, Any],
    capsule: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a canonical in-memory Phase-05 projection for one source shard."""
    action = str(entry["action"])
    if action not in {"RETAIN_CANONICAL_SOURCE", "PROJECT_MINORITY_TO_CANONICAL"}:
        raise RuntimeError(f"unsupported Phase-07 repair action: {action}")

    canonical_rid = str(certificate["canonical_hydro_realization_id"])
    repaired = action == "PROJECT_MINORITY_TO_CANONICAL"
    result = {
        name: [copy.deepcopy(dict(row)) for row in read05[name]]
        for name in (
            "external_exchange",
            "deposition_assignments",
            "deposition_pools",
            "archaeology",
        )
    }

    expected_capsule_sha = str(entry.get("replay_capsule_sha256", ""))
    if expected_capsule_sha and capsule is None:
        raise RuntimeError("affected repaired shard requires its exact replay capsule")
    if capsule is not None and not expected_capsule_sha:
        raise RuntimeError("unexpected replay capsule for a shard with no capsule-backed repair")

    if repaired:
        for row in result["deposition_assignments"]:
            row["hydro_realization_id"] = canonical_rid
        for row in result["deposition_pools"]:
            row["hydro_realization_id"] = canonical_rid

    if capsule is not None:
        _validate_capsule_for_entry(
            capsule,
            certificate=certificate,
            entry=entry,
            ordinal=int(entry["chunk_ordinal"]),
        )
        replay_by_particle = {
            str(row["particle_id"]): dict(row) for row in capsule["replay_rows"]
        }
        assignments = {
            str(row["particle_id"]): row for row in result["deposition_assignments"]
        }
        for particle_id, replay in replay_by_particle.items():
            if particle_id not in assignments:
                raise RuntimeError(f"replay particle absent from source deposition assignments: {particle_id}")
            assignment = assignments[particle_id]
            assignment["hydro_realization_id"] = canonical_rid
            assignment["hydro_context_score"] = float(replay["canonical_hydro_context"])

        pools = {
            str(row["deposition_pool_id"]): row for row in result["deposition_pools"]
        }
        for replacement in capsule["pool_replacements"]:
            pool_id = str(replacement["deposition_pool_id"])
            if pool_id not in pools:
                raise RuntimeError(f"replay pool absent from source deposition pools: {pool_id}")
            pools[pool_id].clear()
            pools[pool_id].update(copy.deepcopy(dict(replacement["canonical"])))
        result["deposition_pools"] = [pools[str(row["deposition_pool_id"])] for row in result["deposition_pools"]]

        external = {
            str(row["particle_id"]): row for row in result["external_exchange"]
        }
        for particle_id, replay in replay_by_particle.items():
            replay_action = str(replay["external_action"])
            canonical_row = replay.get("canonical_external_row")
            if replay_action == "UNCHANGED_ABSENT":
                if particle_id in external:
                    raise RuntimeError(f"UNCHANGED_ABSENT replay particle unexpectedly has a source external row: {particle_id}")
            elif replay_action in {"UPDATE", "ADD"}:
                if canonical_row is None:
                    raise RuntimeError(f"{replay_action} replay particle lacks canonical external row: {particle_id}")
                external[particle_id] = copy.deepcopy(dict(canonical_row))
            elif replay_action == "REMOVE":
                external.pop(particle_id, None)
            else:
                raise RuntimeError(f"unsupported replay external action: {replay_action}")
        result["external_exchange"] = [external[key] for key in sorted(external)]

    source_external_count = len(read05["external_exchange"])
    expected_delta = int(entry.get("external_exchange_count_delta", 0))
    if len(result["external_exchange"]) != source_external_count + expected_delta:
        raise RuntimeError(
            "canonical external-exchange count does not match repair certificate delta"
        )

    if repaired:
        if any(
            str(row["hydro_realization_id"]) != canonical_rid
            for row in result["deposition_assignments"]
        ):
            raise RuntimeError("repaired deposition assignment retained minority hydro identity")
        if any(
            str(row["hydro_realization_id"]) != canonical_rid
            for row in result["deposition_pools"]
        ):
            raise RuntimeError("repaired deposition pool retained minority hydro identity")

    return result


def _operation_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "count": 0,
            "localized_fraction": 0.0,
            "operation_types": [],
            "mean_capability": 0.0,
            "mean_operator_skill": 0.0,
            "mean_tool_fit": 0.0,
            "mean_support_fit": 0.0,
            "mean_thermal_fit": 0.0,
            "mean_measurement_fit": 0.0,
            "mean_material_fit": 0.0,
        }
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row["operation_type"])
        counts[key] = counts.get(key, 0) + 1
    return {
        "count": len(rows),
        "localized_fraction": float(sum(bool(row["localized"]) for row in rows) / len(rows)),
        "operation_types": [
            {"operation_type": key, "count": counts[key]} for key in sorted(counts)
        ],
        "mean_capability": _mean(rows, "capability"),
        "mean_operator_skill": _mean(rows, "operator_skill"),
        "mean_tool_fit": _mean(rows, "tool_fit"),
        "mean_support_fit": _mean(rows, "support_fit"),
        "mean_thermal_fit": _mean(rows, "thermal_fit"),
        "mean_measurement_fit": _mean(rows, "measurement_fit"),
        "mean_material_fit": _mean(rows, "material_fit"),
    }


def build_empirical_profiles(
    *,
    world_build_id: str,
    spine: Mapping[str, Any],
    biography: Mapping[str, Any],
    metallurgy: Mapping[str, Any],
    workshop: Mapping[str, Any],
    phase05: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Join all Phase-01..05 evidence into weighted joint profile rows."""
    cells = {int(row["cell_index"]): dict(row) for row in spine["cells"]}
    losses = {
        (int(row["cell_index"]), int(row["cell_loss_index"])): dict(row)
        for row in spine["loss_strata"]
    }
    particles = [dict(row) for row in biography["particles"]]

    ancestry_by_batch: dict[int, list[dict[str, Any]]] = {}
    for row in biography["ancestry"]:
        ancestry_by_batch.setdefault(int(row["batch_index"]), []).append(dict(row))

    chemistry_by_batch_id = {
        str(row["batch_id"]): dict(row) for row in metallurgy["chemistry_batches"]
    }
    elements_by_chemistry: dict[int, list[dict[str, Any]]] = {}
    for row in metallurgy["elements"]:
        elements_by_chemistry.setdefault(int(row["chemistry_batch_index"]), []).append(dict(row))
    pb_source_by_chemistry: dict[int, list[dict[str, Any]]] = {}
    for row in metallurgy["source_pb"]:
        pb_source_by_chemistry.setdefault(int(row["chemistry_batch_index"]), []).append(dict(row))

    operations_by_particle: dict[str, list[dict[str, Any]]] = {}
    for row in workshop["operations"]:
        operations_by_particle.setdefault(str(row["particle_id"]), []).append(dict(row))

    assignments = {
        str(row["particle_id"]): dict(row) for row in phase05["deposition_assignments"]
    }
    archaeology = {
        str(row["particle_id"]): dict(row) for row in phase05["archaeology"]
    }
    external = {
        str(row["particle_id"]): dict(row) for row in phase05["external_exchange"]
    }
    pools = {
        str(row["deposition_pool_id"]): dict(row) for row in phase05["deposition_pools"]
    }

    profiles: list[dict[str, Any]] = []
    for particle in sorted(
        particles,
        key=lambda row: (
            int(row["production_cell_index"]),
            int(row["cell_loss_index"]),
            str(row["particle_id"]),
        ),
    ):
        particle_id = str(particle["particle_id"])
        cell_index = int(particle["production_cell_index"])
        loss_key = (cell_index, int(particle["cell_loss_index"]))
        if cell_index not in cells or loss_key not in losses:
            raise RuntimeError(f"particle {particle_id} cannot join to Phase-01 cell/loss stratum")
        if particle_id not in assignments or particle_id not in archaeology:
            raise RuntimeError(f"particle {particle_id} lacks Phase-05 deposition/archaeology row")

        cell = cells[cell_index]
        loss = losses[loss_key]
        assignment = assignments[particle_id]
        observation = archaeology[particle_id]
        pool_id = str(assignment["deposition_pool_id"])
        if pool_id not in pools:
            raise RuntimeError(f"particle {particle_id} references missing deposition pool {pool_id}")
        pool = pools[pool_id]

        batch_id = str(particle["metal_batch_id"])
        if batch_id not in chemistry_by_batch_id:
            raise RuntimeError(f"particle {particle_id} final metal batch lacks Phase-03 chemistry: {batch_id}")
        chemistry = chemistry_by_batch_id[batch_id]
        chemistry_index = int(chemistry["chemistry_batch_index"])
        elements = sorted(
            elements_by_chemistry.get(chemistry_index, []), key=lambda row: str(row["element"])
        )
        pb_sources = sorted(
            pb_source_by_chemistry.get(chemistry_index, []), key=lambda row: str(row["source_id"])
        )
        ancestry = sorted(
            ancestry_by_batch.get(int(particle["final_batch_index"]), []),
            key=lambda row: str(row["source_id"]),
        )

        source_mix = _tokenized_weights(
            cell["source_mix_json"], world_build_id=world_build_id, kind="source"
        )
        field_mix = _tokenized_weights(
            loss["field_mix_json"], world_build_id=world_build_id, kind="field"
        )
        mode_weights = _json_weights(loss["deposition_mode_weights_json"])

        external_row = external.get(particle_id)
        external_tail = None
        if external_row is not None:
            external_tail = {
                "component": str(external_row["external_component_id"]),
                "trigger": str(external_row["trigger"]),
                "contact_probability": float(external_row["contact_probability"]),
                "contact_intensity": float(external_row["contact_intensity"]),
                "represented_weight": float(external_row["represented_weight"]),
            }

        profile = {
            "profile_id": anonymous_token(world_build_id, "particle", particle_id),
            "cell_index": cell_index,
            "cell": {
                "bundle_token": anonymous_token(world_build_id, "bundle", cell["bundle_id"]),
                "bundle_family": str(cell["bundle_family"]),
                "object_class": str(cell["object_class"]),
                "date_bc": int(cell["date_bc"]),
                "origin_token": anonymous_token(world_build_id, "node", cell["origin"]),
                "destination_token": anonymous_token(world_build_id, "node", cell["destination"]),
                "production_intensity": float(cell["production_intensity"]),
                "circulation_seed_intensity": float(cell["circulation_seed_intensity"]),
                "recycle_mean": float(cell["recycle_mean"]),
                "source_mix": source_mix,
            },
            "loss": {
                "node_token": anonymous_token(world_build_id, "node", loss["node_id"]),
                "step": int(loss["step"]),
                "loss_intensity": float(loss["loss_intensity"]),
                "deposition_mode_weights": mode_weights,
                "expected_recycle_count": float(loss["expected_recycle_count"]),
                "expected_repair_count": float(loss["expected_repair_count"]),
                "expected_source_entropy": float(loss["expected_source_entropy"]),
                "expected_field_crossings": float(loss["expected_field_crossings"]),
                "expected_physical_crossings": float(loss["expected_physical_crossings"]),
                "route_distance_from_origin_km": float(loss["route_distance_from_origin_km"]),
                "field_mix": field_mix,
            },
            "lineage": {
                "represented_weight": float(particle["represented_weight"]),
                "metal_mass_kg": float(particle["metal_mass_kg"]),
                "ore_distance_km": float(particle["ore_distance_km"]),
                "cumulative_metal_distance_km": float(particle["cumulative_metal_distance_km"]),
                "current_object_distance_km": float(particle["current_object_distance_km"]),
                "source_entropy": float(particle["source_entropy"]),
                "remelt_count": int(particle["remelt_count"]),
                "repair_count": int(particle["repair_count"]),
                "source_ancestry": [
                    {
                        "source_token": anonymous_token(world_build_id, "source", row["source_id"]),
                        "fraction": float(row["fraction"]),
                        "mass_kg": float(row["mass_kg"]),
                    }
                    for row in ancestry
                ],
            },
            "chemistry": {
                "metal_mass_kg": float(chemistry["metal_mass_kg"]),
                "pb_mass_kg": float(chemistry["pb_mass_kg"]),
                "Pb206_204": float(chemistry["Pb206_204"]),
                "Pb207_204": float(chemistry["Pb207_204"]),
                "Pb208_204": float(chemistry["Pb208_204"]),
                "elements": [
                    {
                        "element": str(row["element"]),
                        "mass_fraction": float(row["mass_fraction"]),
                    }
                    for row in elements
                ],
                "pb_source_ancestry": [
                    {
                        "source_token": anonymous_token(world_build_id, "source", row["source_id"]),
                        "fraction_of_pb": float(row["fraction_of_pb"]),
                    }
                    for row in pb_sources
                ],
            },
            "operations": _operation_summary(operations_by_particle.get(particle_id, [])),
            "deposition": {
                "pool_token": anonymous_token(world_build_id, "pool", pool_id),
                "mode": str(assignment["mode"]),
                "mode_probability": float(assignment["mode_probability"]),
                "represented_weight": float(assignment["represented_weight"]),
                "expected_field_crossings": float(assignment["expected_field_crossings"]),
                "expected_physical_crossings": float(assignment["expected_physical_crossings"]),
                "hydro_context_score": float(assignment["hydro_context_score"]),
                "pool_member_count": int(pool["member_count"]),
                "pool_represented_weight": float(pool["represented_weight"]),
            },
            "archaeology": {
                "represented_loss_weight": float(observation["represented_loss_weight"]),
                "p_survival": float(observation["p_survival"]),
                "survival_weight": float(observation["survival_weight"]),
                "p_discovery": float(observation["p_discovery"]),
                "discovery_weight": float(observation["discovery_weight"]),
                "p_record": float(observation["p_record"]),
                "recorded_weight": float(observation["recorded_weight"]),
            },
            "external_tail": external_tail,
        }
        profiles.append(profile)

    if len(profiles) != len(losses):
        raise RuntimeError(
            f"Phase-08 profile population mismatch: profiles={len(profiles)} loss_strata={len(losses)}"
        )
    return profiles


def _read_chunk_marker(path: Path) -> dict[str, Any]:
    with Dataset(path, "r") as ds:
        group = ds.groups.get("canonical_chunk")
        if group is None:
            raise RuntimeError("source shard lacks Phase-07 canonical chunk marker")
        return json.loads(str(group.record_json))


def extract_runtime_fragment(
    *,
    shard_path: Path,
    certificate_path: Path,
    ordinal: int,
    out_path: Path,
    capsule_path: Path | None = None,
) -> dict[str, Any]:
    shard_path = Path(shard_path)
    certificate_path = Path(certificate_path)
    out_path = Path(out_path)
    certificate = _read_json(certificate_path)
    validate_certificate(certificate)
    entry = certificate_entry(certificate, ordinal)

    marker = _read_chunk_marker(shard_path)
    if int(marker["chunk_ordinal"]) != int(ordinal):
        raise RuntimeError("source shard ordinal does not match requested Phase-08 ordinal")
    if str(marker["world_build_id"]) != str(certificate["world_build_id"]):
        raise RuntimeError("source shard world-build id does not match Phase-07 repair certificate")

    record, workshop, read05 = phase07._read_existing_shard(
        shard_path,
        expected_world_build_id=str(certificate["world_build_id"]),
        ordinal=int(ordinal),
        start=int(marker["global_cell_start"]),
        stop=int(marker["global_cell_stop"]),
    )
    if str(entry["source_chunk_sha256"]) != str(record["chunk_sha256"]):
        raise RuntimeError("Phase-08 source chunk hash differs from repair certificate")
    if str(entry["source_phase05_sha256"]) != str(record["phase05_sha256"]):
        raise RuntimeError("Phase-08 source Phase-05 hash differs from repair certificate")

    capsule = None
    capsule_sha = ""
    if capsule_path is not None:
        capsule_path = Path(capsule_path)
        capsule = _read_json(capsule_path)
        capsule_sha = _file_sha256(capsule_path)
        expected_capsule_sha = str(entry.get("replay_capsule_sha256", ""))
        if capsule_sha != expected_capsule_sha:
            raise RuntimeError("Phase-08 replay capsule file hash differs from repair certificate")
    elif str(entry.get("replay_capsule_sha256", "")):
        raise RuntimeError("Phase-08 affected shard requires --capsule")

    canonical05 = canonicalize_phase05(
        read05,
        certificate=certificate,
        entry=entry,
        capsule=capsule,
    )
    spine = v3_netcdf.read_spine_master(shard_path)
    biography = v3_biography_netcdf.read_biography(shard_path)
    metallurgy = v3_metallurgy_netcdf.read_metallurgy(shard_path)
    profiles = build_empirical_profiles(
        world_build_id=str(certificate["world_build_id"]),
        spine=spine,
        biography=biography,
        metallurgy=metallurgy,
        workshop=workshop,
        phase05=canonical05,
    )

    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "hash_policy": HASH_POLICY,
        "projection_policy": PROJECTION_POLICY,
        "world_build_id": str(certificate["world_build_id"]),
        "chunk_ordinal": int(ordinal),
        "global_cell_start": int(record["global_cell_start"]),
        "global_cell_stop": int(record["global_cell_stop"]),
        "source": {
            "shard_name": shard_path.name,
            "chunk_sha256": str(record["chunk_sha256"]),
            "phase01_spine_sha256": str(record["phase01_spine_sha256"]),
            "phase02_biography_sha256": str(record["phase02_biography_sha256"]),
            "phase03_metallurgy_sha256": str(record["phase03_metallurgy_sha256"]),
            "phase04_workshop_sha256": str(record["phase04_workshop_sha256"]),
            "phase05_sha256": str(record["phase05_sha256"]),
        },
        "recovery": {
            "certificate_sha256": str(certificate["certificate_sha256"]),
            "action": str(entry["action"]),
            "canonical_hydro_realization_token": anonymous_token(
                str(certificate["world_build_id"]),
                "hydro",
                certificate["canonical_hydro_realization_id"],
            ),
            "external_exchange_count_delta": int(entry.get("external_exchange_count_delta", 0)),
            "replay_capsule_sha256": capsule_sha,
        },
        "profile_count": len(profiles),
        "totals": {
            "represented_weight": float(math.fsum(row["lineage"]["represented_weight"] for row in profiles)),
            "recorded_weight": float(math.fsum(row["archaeology"]["recorded_weight"] for row in profiles)),
            "external_tail_count": sum(row["external_tail"] is not None for row in profiles),
        },
        "profiles": profiles,
    }
    payload["fragment_sha256"] = fragment_hash(payload)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    checked = _read_json(out_path)
    if str(checked["fragment_sha256"]) != fragment_hash(checked):
        raise RuntimeError("Phase-08 runtime fragment roundtrip hash mismatch")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shard", type=Path, required=True)
    parser.add_argument("--certificate", type=Path, required=True)
    parser.add_argument("--ordinal", type=int, required=True)
    parser.add_argument("--capsule", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = extract_runtime_fragment(
        shard_path=args.shard,
        certificate_path=args.certificate,
        ordinal=args.ordinal,
        capsule_path=args.capsule,
        out_path=args.out,
    )
    print(json.dumps({
        "schema": result["schema"],
        "world_build_id": result["world_build_id"],
        "chunk_ordinal": result["chunk_ordinal"],
        "profile_count": result["profile_count"],
        "fragment_sha256": result["fragment_sha256"],
        "totals": result["totals"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
