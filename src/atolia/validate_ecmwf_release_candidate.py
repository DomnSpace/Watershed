#!/usr/bin/env python3
from __future__ import annotations

"""Validate the compact Atolia ECMWF runtime and, optionally, full player careers.

This is a release-candidate validation command, not another converter.  It never
reads the giant JSON developer cache and never reruns latent circulation.

Default mode checks the shipping NetCDF product structurally and scientifically:

* exact release counts / master provenance;
* no exact ``state_*`` arrays leaked into the installer runtime;
* CSR pointer monotonicity and terminal counts;
* profile/cell/node index bounds;
* source-mixture pointer integrity;
* sampled deposition/transport-field normalization;
* endpoint conservation semantics where recycle/transfer are internal throughput.

``--careers`` additionally generates player A twice and player B once and checks:

* same player key is bit-for-bit deterministic at JSON level;
* another player key produces a different career over the same hidden world;
* exactly 300 objects and the canonical 50/20/30/30/60/60/40/10 regime schedule;
* normal generation really used the ECMWF runtime;
* zero Python ``LossStratum`` objects were materialized during preparation.

No POARI p-measure is changed or approximated by this validator.
"""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable

import numpy as np
from netCDF4 import Dataset

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import acquisition_campaign as campaign
import ecmwf_acquisition_campaign as ecmwf
import player_game_package as package


EXPECTED_MASTER_SHA256 = "e98fca327394f1a98dc0cdfb0db4b6a93e44386933b61c2ac8d5c0ebe1e1f24c"
EXPECTED_MASTER_STATES = 23_711_916
EXPECTED_RUNTIME_PROFILES = 1_711_008
EXPECTED_PRODUCTION_CELLS = 35_560
EXPECTED_REGIME_COUNTS = {
    "stray_tail": 50,
    "context_followup": 20,
    "random_hoard": 30,
    "post_hoard_comparison": 30,
    "exploratory_dig": 60,
    "discriminating_dig": 60,
    "network_reconstruction": 40,
    "falsification_probe": 10,
}


def _sha256_file(path: Path, block_size: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(block_size)
            if not block:
                return h.hexdigest()
            h.update(block)


def _json_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def _as_i64(var: Any) -> np.ndarray:
    return np.asarray(var[:], dtype=np.int64)


def _check_pointer(
    ds: Dataset,
    *,
    ptr_name: str,
    index_name: str,
    target_count: int,
    errors: list[str],
) -> dict[str, int]:
    if ptr_name not in ds.variables or index_name not in ds.variables:
        errors.append(f"missing pointer pair {ptr_name}/{index_name}")
        return {"ptr_entries": 0, "index_entries": 0}
    ptr = _as_i64(ds.variables[ptr_name])
    index = _as_i64(ds.variables[index_name])
    _require(ptr.size >= 1, f"{ptr_name} is empty", errors)
    if ptr.size:
        _require(int(ptr[0]) == 0, f"{ptr_name}[0] != 0", errors)
        _require(np.all(ptr[1:] >= ptr[:-1]), f"{ptr_name} is not monotone", errors)
        _require(int(ptr[-1]) == int(index.size), f"{ptr_name} terminal != len({index_name})", errors)
    if index.size:
        _require(int(index.min()) >= 0, f"{index_name} contains negative ids", errors)
        _require(int(index.max()) < target_count, f"{index_name} contains out-of-range ids", errors)
    return {"ptr_entries": int(ptr.size), "index_entries": int(index.size)}


def _sample_ids(count: int, n: int = 2048) -> np.ndarray:
    if count <= n:
        return np.arange(count, dtype=np.int64)
    # Deterministic coverage of the whole field without a random dependency.
    return np.unique(np.linspace(0, count - 1, num=n, dtype=np.int64))


def validate_runtime(runtime_path: Path) -> dict[str, Any]:
    runtime_path = Path(runtime_path)
    errors: list[str] = []
    warnings: list[str] = []
    if not runtime_path.exists():
        return {
            "ok": False,
            "runtime": str(runtime_path),
            "errors": [f"runtime not found: {runtime_path}"],
            "warnings": [],
        }

    runtime_sha = _sha256_file(runtime_path)
    with Dataset(runtime_path, "r") as ds:
        schema = str(getattr(ds, "schema", ""))
        product_kind = str(getattr(ds, "product_kind", ""))
        master_sha = str(getattr(ds, "master_sha256", ""))
        master_states = int(getattr(ds, "master_state_count", -1))
        profile_count = len(ds.dimensions.get("profile", ()))
        cell_count = len(ds.dimensions.get("production_cell", ()))

        _require(schema == ecmwf.RUNTIME_SCHEMA, f"schema={schema!r}", errors)
        _require(product_kind == "installer_runtime", f"product_kind={product_kind!r}", errors)
        _require(master_sha == EXPECTED_MASTER_SHA256, f"unexpected master_sha256={master_sha}", errors)
        _require(master_states == EXPECTED_MASTER_STATES, f"master_state_count={master_states}", errors)
        _require(profile_count == EXPECTED_RUNTIME_PROFILES, f"profile_count={profile_count}", errors)
        _require(cell_count == EXPECTED_PRODUCTION_CELLS, f"production_cell_count={cell_count}", errors)

        leaked = sorted(
            name
            for name, var in ds.variables.items()
            if name.startswith("state_") or "state" in var.dimensions
        )
        _require(not leaked, f"exact state variables leaked into runtime: {leaked[:12]}", errors)
        if "state" in ds.dimensions:
            warnings.append("runtime retains an unused state dimension; no state variables reference it")

        required = ecmwf._REQUIRED_VARIABLES
        missing = sorted(required - set(ds.variables))
        _require(not missing, f"missing runtime variables: {missing}", errors)

        if "profile_cell" in ds.variables:
            profile_cell = _as_i64(ds.variables["profile_cell"])
            _require(profile_cell.size == profile_count, "profile_cell length mismatch", errors)
            if profile_cell.size:
                _require(int(profile_cell.min()) >= 0, "profile_cell contains negative ids", errors)
                _require(int(profile_cell.max()) < cell_count, "profile_cell contains out-of-range ids", errors)
        else:
            profile_cell = np.empty(0, dtype=np.int64)

        node_count = len(ds.dimensions.get("node", ()))
        class_count = len(ds.dimensions.get("object_class", ()))
        bundle_count = len(ds.dimensions.get("bundle", ()))
        source_count = len(ds.dimensions.get("source", ()))
        if "profile_node" in ds.variables:
            profile_node = _as_i64(ds.variables["profile_node"])
            _require(profile_node.size == profile_count, "profile_node length mismatch", errors)
            if profile_node.size:
                _require(int(profile_node.min()) >= 0, "profile_node contains negative ids", errors)
                _require(int(profile_node.max()) < node_count, "profile_node contains out-of-range ids", errors)

        pointer_report = {
            "site": _check_pointer(
                ds, ptr_name="site_ptr", index_name="site_profile_index",
                target_count=profile_count, errors=errors,
            ),
            "class": _check_pointer(
                ds, ptr_name="class_ptr", index_name="class_profile_index",
                target_count=profile_count, errors=errors,
            ),
            "bundle": _check_pointer(
                ds, ptr_name="bundle_ptr", index_name="bundle_profile_index",
                target_count=profile_count, errors=errors,
            ),
        }
        if "site_ptr" in ds.variables:
            _require(len(ds.variables["site_ptr"]) == node_count + 1, "site_ptr length != node_count+1", errors)
        if "class_ptr" in ds.variables:
            _require(len(ds.variables["class_ptr"]) == class_count + 1, "class_ptr length != class_count+1", errors)
        if "bundle_ptr" in ds.variables:
            _require(len(ds.variables["bundle_ptr"]) == bundle_count + 1, "bundle_ptr length != bundle_count+1", errors)

        if "cell_source_ptr" in ds.variables:
            source_ptr = _as_i64(ds.variables["cell_source_ptr"])
            source_ids = _as_i64(ds.variables["cell_source_id"])
            source_weights = np.asarray(ds.variables["cell_source_weight"][:], dtype=np.float64)
            _require(source_ptr.size == cell_count + 1, "cell_source_ptr length != cell_count+1", errors)
            if source_ptr.size:
                _require(int(source_ptr[0]) == 0, "cell_source_ptr[0] != 0", errors)
                _require(np.all(source_ptr[1:] >= source_ptr[:-1]), "cell_source_ptr is not monotone", errors)
                _require(int(source_ptr[-1]) == int(source_ids.size), "cell_source_ptr terminal mismatch", errors)
            _require(source_ids.size == source_weights.size, "source id/weight length mismatch", errors)
            if source_ids.size:
                _require(int(source_ids.min()) >= 0, "cell_source_id contains negative ids", errors)
                _require(int(source_ids.max()) < source_count, "cell_source_id contains out-of-range ids", errors)
                _require(np.all(np.isfinite(source_weights)), "cell_source_weight has non-finite values", errors)
                _require(np.all(source_weights >= 0.0), "cell_source_weight has negative values", errors)

            cell_sample = _sample_ids(cell_count, 2048)
            bad_mix = 0
            for cid in cell_sample:
                a, z = int(source_ptr[cid]), int(source_ptr[cid + 1])
                total = float(source_weights[a:z].sum())
                if not np.isclose(total, 1.0, rtol=0.0, atol=1e-10):
                    bad_mix += 1
            _require(bad_mix == 0, f"{bad_mix} sampled source mixtures do not sum to 1", errors)

        profile_sample = _sample_ids(profile_count, 4096)
        dep_bad = field_bad = 0
        if profile_sample.size and "profile_deposition_weight" in ds.variables:
            dep = np.asarray(ds.variables["profile_deposition_weight"][profile_sample, :], dtype=np.float64)
            dep_sum = dep.sum(axis=1)
            dep_bad = int(np.count_nonzero(~np.isclose(dep_sum, 1.0, rtol=0.0, atol=1e-10)))
            _require(np.all(dep >= 0.0), "sampled deposition weights contain negatives", errors)
            _require(dep_bad == 0, f"{dep_bad} sampled deposition vectors do not sum to 1", errors)

        if profile_cell.size and "cell_transport_field_mix" in ds.variables:
            sampled_cells = np.unique(profile_cell[profile_sample])
            mix = np.asarray(ds.variables["cell_transport_field_mix"][sampled_cells, :], dtype=np.float64)
            mix_sum = mix.sum(axis=1)
            field_bad = int(np.count_nonzero(~np.isclose(mix_sum, 1.0, rtol=0.0, atol=1e-10)))
            _require(np.all(mix >= 0.0), "sampled transport-field weights contain negatives", errors)
            _require(field_bad == 0, f"{field_bad} sampled transport-field vectors do not sum to 1", errors)

        if "profile_archaeological_intensity" in ds.variables:
            arch = np.asarray(ds.variables["profile_archaeological_intensity"][profile_sample], dtype=np.float64)
            _require(np.all(np.isfinite(arch)), "sampled archaeological intensity contains non-finite values", errors)
            _require(np.all(arch >= 0.0), "sampled archaeological intensity contains negatives", errors)

        flow_raw = str(getattr(ds, "flow_summary_json", "{}"))
        try:
            flow = dict(json.loads(flow_raw))
        except (TypeError, json.JSONDecodeError):
            flow = {}
            errors.append("flow_summary_json is not valid JSON")
        seed = float(flow.get("circulation_seed", 0.0))
        endpoint_rhs = sum(float(flow.get(k, 0.0)) for k in (
            "return_flux", "loss_flux", "retire_flux", "residual_active"
        ))
        endpoint_error = seed - endpoint_rhs
        stored_endpoint_error = float(getattr(ds, "endpoint_conservation_error", float("nan")))
        stored_relative = float(getattr(ds, "endpoint_relative_conservation_error", float("nan")))
        _require(np.isfinite(stored_endpoint_error), "missing/non-finite endpoint_conservation_error", errors)
        _require(np.isclose(stored_endpoint_error, endpoint_error, rtol=0.0, atol=1e-6),
                 "stored endpoint conservation error does not match endpoint closure", errors)
        expected_relative = endpoint_error / max(1.0, seed)
        _require(np.isclose(stored_relative, expected_relative, rtol=0.0, atol=1e-12),
                 "stored endpoint relative conservation error does not match", errors)
        _require(abs(expected_relative) < 1e-6,
                 f"endpoint relative conservation error too large: {expected_relative:.6g}", errors)

        report = {
            "ok": not errors,
            "runtime": str(runtime_path),
            "runtime_bytes": runtime_path.stat().st_size,
            "runtime_sha256": runtime_sha,
            "schema": schema,
            "product_kind": product_kind,
            "master_sha256": master_sha,
            "exact_master_states": master_states,
            "runtime_profiles": profile_count,
            "production_cells": cell_count,
            "node_count": node_count,
            "class_count": class_count,
            "bundle_count": bundle_count,
            "source_count": source_count,
            "runtime_variable_count": len(ds.variables),
            "exact_state_variables_in_runtime": leaked,
            "pointer_report": pointer_report,
            "sampled_profiles": int(profile_sample.size),
            "sampled_deposition_normalization_failures": dep_bad,
            "sampled_transport_field_normalization_failures": field_bad,
            "endpoint_conservation_error": endpoint_error,
            "endpoint_relative_conservation_error": expected_relative,
            "recycle_flux_internal_throughput": float(flow.get("recycle_flux", 0.0)),
            "transfer_flux_internal_throughput": float(flow.get("transfer_flux", 0.0)),
            "errors": errors,
            "warnings": warnings,
        }
    return report


def _regime_counts(payload: dict[str, Any]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for obj in payload.get("objects", []):
        acquisition = obj.get("acquisition") if isinstance(obj, dict) else None
        if isinstance(acquisition, dict):
            counts[str(acquisition.get("regime"))] += 1
    return counts


def _career_signature(payload: dict[str, Any]) -> list[tuple[Any, ...]]:
    signature: list[tuple[Any, ...]] = []
    for obj in payload.get("objects", []):
        acquisition = obj.get("acquisition") or {}
        findspot = obj.get("findspot") or {}
        signature.append((
            obj.get("object_id"),
            obj.get("class"),
            obj.get("date_center_bc"),
            findspot.get("node_label"),
            acquisition.get("regime"),
            acquisition.get("action_id"),
        ))
    return signature


def validate_careers(runtime_path: Path, hypothesis_path: Path, player_a: str, player_b: str) -> dict[str, Any]:
    errors: list[str] = []

    def build(key: str) -> dict[str, Any]:
        return package.build_player_package(
            player_key=key,
            hypothesis_path=hypothesis_path,
            runtime_path=runtime_path,
            include_debug=True,
        )

    a1 = build(player_a)
    a2 = build(player_a)
    b = build(player_b)

    a1_hash = _json_hash(a1)
    a2_hash = _json_hash(a2)
    b_hash = _json_hash(b)
    _require(a1_hash == a2_hash, "same player key produced different package JSON", errors)
    _require(a1_hash != b_hash, "different player key produced identical package JSON", errors)
    _require(_career_signature(a1) != _career_signature(b), "different player key produced identical career signature", errors)

    shared_world = a1["meta"].get("canonical_world_seed_fingerprint")
    _require(shared_world == b["meta"].get("canonical_world_seed_fingerprint"),
             "player A/B do not share canonical hidden world", errors)

    for label, payload in (("A1", a1), ("A2", a2), ("B", b)):
        meta = payload.get("meta", {})
        _require(meta.get("schema") == package.PACKAGE_SCHEMA, f"{label}: wrong package schema", errors)
        _require(meta.get("generator_version") == package.GENERATOR_VERSION, f"{label}: wrong generator version", errors)
        _require(meta.get("campaign_substrate_source") == "ecmwf_netcdf_runtime",
                 f"{label}: did not use ECMWF runtime", errors)
        _require(meta.get("runtime_materialization") == "selected profile only",
                 f"{label}: unexpected runtime materialization", errors)
        _require(int(meta.get("object_count", -1)) == 300, f"{label}: object_count != 300", errors)
        _require(len(payload.get("objects", [])) == 300, f"{label}: len(objects) != 300", errors)
        counts = _regime_counts(payload)
        _require(dict(counts) == EXPECTED_REGIME_COUNTS,
                 f"{label}: regime counts {dict(counts)} != {EXPECTED_REGIME_COUNTS}", errors)
        debug_substrate = ((payload.get("debug") or {}).get("campaign_substrate") or {})
        _require(int(debug_substrate.get("python_loss_strata_at_prepare", -1)) == 0,
                 f"{label}: Python loss strata materialized during prepare", errors)
        _require(int(debug_substrate.get("runtime_profiles", -1)) == EXPECTED_RUNTIME_PROFILES,
                 f"{label}: runtime profile count mismatch in debug", errors)
        _require(int(debug_substrate.get("production_cells", -1)) == EXPECTED_PRODUCTION_CELLS,
                 f"{label}: production cell count mismatch in debug", errors)

    return {
        "ok": not errors,
        "player_a": player_a,
        "player_b": player_b,
        "same_key_package_sha256": a1_hash,
        "same_key_repeat_sha256": a2_hash,
        "different_key_package_sha256": b_hash,
        "same_key_deterministic": a1_hash == a2_hash,
        "different_key_diverges": a1_hash != b_hash,
        "shared_world_fingerprint": shared_world,
        "player_a_regime_counts": dict(_regime_counts(a1)),
        "player_b_regime_counts": dict(_regime_counts(b)),
        "player_a_package_id": a1["meta"].get("package_id"),
        "player_b_package_id": b["meta"].get("package_id"),
        "errors": errors,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate the Atolia ECMWF release-candidate runtime and careers.")
    ap.add_argument("--runtime", type=Path, default=ecmwf.DEFAULT_RUNTIME)
    ap.add_argument("--hypothesis", type=Path, default=REPO_ROOT / "hypotheses" / "atolia_atesis_1800_1000_v0.json")
    ap.add_argument("--careers", action="store_true", help="Generate A/A/B full 300-object careers after structural checks.")
    ap.add_argument("--player-a", default="release-check-01")
    ap.add_argument("--player-b", default="release-check-02")
    args = ap.parse_args()

    runtime_path = args.runtime if args.runtime.is_absolute() else REPO_ROOT / args.runtime
    hypothesis_path = args.hypothesis if args.hypothesis.is_absolute() else REPO_ROOT / args.hypothesis
    structural = validate_runtime(runtime_path)
    result: dict[str, Any] = {
        "schema": "atolia.ecmwf-release-validation.v1",
        "structural": structural,
        "careers": None,
    }
    if structural["ok"] and args.careers:
        result["careers"] = validate_careers(
            runtime_path,
            hypothesis_path,
            args.player_a,
            args.player_b,
        )
    result["ok"] = bool(structural["ok"] and (result["careers"] is None or result["careers"]["ok"]))
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
