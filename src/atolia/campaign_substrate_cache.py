from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence

import intensity_circulation as intensity


CACHE_SCHEMA = "atolia.campaign-substrate.v1"
DEFAULT_CACHE_PATH = Path("cache/atolia_campaign_substrate_v1.json.gz")
# The calibrated hidden world is shared by players. Player keys vary acquisition,
# individual physical draws and measurements, not the underlying Bronze Age world.
DEFAULT_CANONICAL_WORLD_SEED = 20260824
DEFAULT_WORKSHOPS = 3200
DEFAULT_STEPS = 28


def hypothesis_digest(hypothesis: Mapping[str, Any]) -> str:
    raw = json.dumps(hypothesis, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _cell_to_dict(cell: intensity.ProductionCell) -> Dict[str, Any]:
    return {
        "bundle_id": cell.bundle_id,
        "bundle_family": cell.bundle_family,
        "object_class": cell.object_class,
        "date_bc": int(cell.date_bc),
        "origin": cell.origin,
        "destination": cell.destination,
        "production_intensity": float(cell.production_intensity),
        "circulation_seed_intensity": float(cell.circulation_seed_intensity),
        "source_mix": {str(k): float(v) for k, v in cell.source_mix.items()},
        "recycle_mean": float(cell.recycle_mean),
    }


def _cell_from_dict(row: Mapping[str, Any]) -> intensity.ProductionCell:
    return intensity.ProductionCell(
        bundle_id=str(row["bundle_id"]),
        bundle_family=str(row["bundle_family"]),
        object_class=str(row["object_class"]),
        date_bc=int(row["date_bc"]),
        origin=str(row["origin"]),
        destination=str(row["destination"]),
        production_intensity=float(row["production_intensity"]),
        circulation_seed_intensity=float(row["circulation_seed_intensity"]),
        source_mix={str(k): float(v) for k, v in row["source_mix"].items()},
        recycle_mean=float(row["recycle_mean"]),
    )


def stratum_to_dict(s: intensity.LossStratum) -> Dict[str, Any]:
    return {
        "production_cell": _cell_to_dict(s.production_cell),
        "node_id": s.node_id,
        "step": int(s.step),
        "loss_intensity": float(s.loss_intensity),
        "deposition_mode_weights": {str(k): float(v) for k, v in s.deposition_mode_weights.items()},
        "expected_recycle_count": float(s.expected_recycle_count),
        "expected_repair_count": float(s.expected_repair_count),
        "expected_source_entropy": float(s.expected_source_entropy),
        "expected_field_crossings": float(s.expected_field_crossings),
        "expected_physical_crossings": float(s.expected_physical_crossings),
        "route_distance_from_origin_km": float(s.route_distance_from_origin_km),
        "field_mix": {str(k): float(v) for k, v in s.field_mix.items()},
    }


def stratum_from_dict(row: Mapping[str, Any]) -> intensity.LossStratum:
    return intensity.LossStratum(
        production_cell=_cell_from_dict(row["production_cell"]),
        node_id=str(row["node_id"]),
        step=int(row["step"]),
        loss_intensity=float(row["loss_intensity"]),
        deposition_mode_weights={str(k): float(v) for k, v in row["deposition_mode_weights"].items()},
        expected_recycle_count=float(row["expected_recycle_count"]),
        expected_repair_count=float(row["expected_repair_count"]),
        expected_source_entropy=float(row["expected_source_entropy"]),
        expected_field_crossings=float(row["expected_field_crossings"]),
        expected_physical_crossings=float(row["expected_physical_crossings"]),
        route_distance_from_origin_km=float(row["route_distance_from_origin_km"]),
        field_mix={str(k): float(v) for k, v in row["field_mix"].items()},
    )


def build_payload(
    *,
    hypothesis: Mapping[str, Any],
    world_seed: int,
    workshop_count: int,
    intensity_steps: int,
    flow_summary: Mapping[str, Any],
    loss_strata: Sequence[intensity.LossStratum],
    geography_report: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "schema": CACHE_SCHEMA,
        "world_seed": int(world_seed),
        "workshop_count": int(workshop_count),
        "intensity_steps": int(intensity_steps),
        "hypothesis_sha256": hypothesis_digest(hypothesis),
        "intensity_model_version": intensity.INTENSITY_MODEL_VERSION,
        "flow_summary": dict(flow_summary),
        "geography_report": dict(geography_report or {}),
        "loss_strata": [stratum_to_dict(s) for s in loss_strata],
    }


def payload_fingerprint(payload: Mapping[str, Any]) -> str:
    meta = {
        "schema": payload.get("schema"),
        "world_seed": payload.get("world_seed"),
        "workshop_count": payload.get("workshop_count"),
        "intensity_steps": payload.get("intensity_steps"),
        "hypothesis_sha256": payload.get("hypothesis_sha256"),
        "intensity_model_version": payload.get("intensity_model_version"),
        "loss_strata": len(payload.get("loss_strata", [])),
    }
    raw = json.dumps(meta, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def save_payload(payload: Mapping[str, Any], path: Path | str = DEFAULT_CACHE_PATH) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if path.suffix == ".gz":
        with gzip.open(path, "wb", compresslevel=6) as fh:
            fh.write(raw)
    else:
        path.write_bytes(raw)
    return path


def load_payload(path: Path | str = DEFAULT_CACHE_PATH) -> Dict[str, Any]:
    path = Path(path)
    if path.suffix == ".gz":
        with gzip.open(path, "rb") as fh:
            payload = json.loads(fh.read().decode("utf-8"))
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != CACHE_SCHEMA:
        raise ValueError(f"unsupported campaign substrate schema: {payload.get('schema')!r}")
    return payload


def validate_payload(payload: Mapping[str, Any], hypothesis: Mapping[str, Any] | None = None) -> None:
    if payload.get("schema") != CACHE_SCHEMA:
        raise ValueError("campaign substrate schema mismatch")
    if int(payload.get("world_seed", -1)) < 0:
        raise ValueError("campaign substrate has invalid world_seed")
    if int(payload.get("workshop_count", 0)) <= 0:
        raise ValueError("campaign substrate has invalid workshop_count")
    if int(payload.get("intensity_steps", 0)) <= 0:
        raise ValueError("campaign substrate has invalid intensity_steps")
    if not payload.get("loss_strata"):
        raise ValueError("campaign substrate contains no loss strata")
    if hypothesis is not None and payload.get("hypothesis_sha256") != hypothesis_digest(hypothesis):
        raise ValueError("campaign substrate was built from a different hypothesis")


def deserialize_loss_strata(payload: Mapping[str, Any]) -> list[intensity.LossStratum]:
    validate_payload(payload)
    return [stratum_from_dict(row) for row in payload["loss_strata"]]
