from __future__ import annotations

"""Shared contracts for the frozen Atolia v3 R17 field and private player slice."""

import hashlib
import json
from typing import Any, Mapping, Sequence

from v3_phase08_runtime_fragment import anonymous_token

RUNTIME_SCHEMA = "atolia-v3-r17-frozen-field-v2"
PLAYER_SCHEMA = "dr-corrosion-player-17-netcdf-v1"
GENERATOR_VERSION = "atolia-v3-r17-keyed-acquisition-v2"
CELL_HASH_POLICY = "sha256-canonical-json-float-hex-v1"
PROFILE_HASH_POLICY = "sha256-profile-node-ordered-float-hex-v1"
TARGET_OBJECTS = 300
PROFILE_PHASE01_FIELDS = (
    "expected_recycle_count",
    "expected_repair_count",
    "expected_source_entropy",
    "expected_field_crossings",
    "expected_physical_crossings",
    "route_distance_from_origin_km",
)


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def float_hex(value: Any) -> str:
    return float(value).hex()


def sha256_json(value: Any) -> bytes:
    return hashlib.sha256(stable_json(value).encode("utf-8")).digest()


def cell_identity_payload(
    *,
    world_build_id: str,
    global_cell_index: int,
    bundle_id: str,
    bundle_family: str,
    object_class: str,
    date_bc: int,
    origin: str,
    destination: str,
    production_intensity: float,
    circulation_seed_intensity: float,
    recycle_mean: float,
    source_mix: Mapping[str, float],
    already_tokenized: bool = False,
) -> dict[str, Any]:
    if already_tokenized:
        bundle = str(bundle_id)
        origin_token = str(origin)
        destination_token = str(destination)
        sources = sorted((str(key), float_hex(value)) for key, value in source_mix.items() if float(value) != 0.0)
    else:
        bundle = anonymous_token(world_build_id, "bundle", bundle_id)
        origin_token = anonymous_token(world_build_id, "node", origin)
        destination_token = anonymous_token(world_build_id, "node", destination)
        sources = sorted(
            (anonymous_token(world_build_id, "source", key), float_hex(value))
            for key, value in source_mix.items()
            if float(value) != 0.0
        )
    return {
        "global_cell_index": int(global_cell_index),
        "bundle": bundle,
        "family": str(bundle_family),
        "object_class": str(object_class),
        "date_bc": int(date_bc),
        "origin": origin_token,
        "destination": destination_token,
        "production_intensity": float_hex(production_intensity),
        "circulation_seed_intensity": float_hex(circulation_seed_intensity),
        "recycle_mean": float_hex(recycle_mean),
        "source_mix": sources,
    }


def cell_identity_hash(**kwargs: Any) -> bytes:
    return sha256_json(cell_identity_payload(**kwargs))


def profile_checkpoint_payload(rows: Sequence[Mapping[str, Any]]) -> list[list[Any]]:
    """Canonical Phase-08 checkpoint rows for one production cell or profile set."""
    out: list[list[Any]] = []
    for row in sorted(rows, key=lambda item: str(item["node_token"])):
        values: list[Any] = [
            str(row["node_token"]),
            int(row["lineage_count"]),
            float_hex(row["loss_intensity"]),
            float_hex(row["recorded_weight"]),
            int(row["step_min"]),
            int(row["step_max"]),
        ]
        for name in PROFILE_PHASE01_FIELDS:
            values.extend((float_hex(row[f"{name}_mean"]), float_hex(row[f"{name}_variance"])))
        out.append(values)
    return out


def profile_checkpoint_hash(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return sha256_json(profile_checkpoint_payload(rows))


def bytes_to_hex_rows(values: Any) -> list[str]:
    return [bytes(row).hex() for row in values]
