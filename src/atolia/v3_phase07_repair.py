#!/usr/bin/env python3
from __future__ import annotations

"""Build a provenance-preserving logical mend for the split phase-07 corpus.

The immutable NetCDF shards and their phase hashes are never rewritten.  This
tool projects only the compact manifest data into the chosen observed hydro
realization, and attaches exact replay-capsule lineage for the nine shards where
external-exchange threshold outcomes could change.
"""

import argparse
from collections import Counter
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any, Mapping, Sequence

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import v3_phase07_assemble_fragments as assemble_fragments
import v3_phase07_fragment as fragment_io
import v3_phase07_replay_capsule as replay_capsule


CERTIFICATE_SCHEMA = "atolia-v3-phase07-hydro-repair-certificate-v1"
CERTIFICATE_POLICY = (
    "observed-majority-realization; no-synthetic-topology; immutable-source-artifacts; "
    "capsule-backed-external-threshold-replay"
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _exact_equal(left: Any, right: Any) -> bool:
    return fragment_io._stable_exact_json(left) == fragment_io._stable_exact_json(right)


def _single_realization_id(fragment: Mapping[str, Any]) -> str:
    ids = {str(row["hydro_realization_id"]) for row in fragment.get("deposition_pools", [])}
    if len(ids) != 1:
        raise RuntimeError(
            f"fragment ordinal {fragment['chunk_ordinal']} expected exactly one hydro realization id; "
            f"found {sorted(ids)}"
        )
    return next(iter(ids))


def _affected_contexts(plan: Mapping[str, Any]) -> dict[str, dict[str, float]]:
    return {
        str(row["node_id"]): {
            "minority": float(row["minority"]),
            "canonical": float(row["canonical"]),
        }
        for row in plan["observed_boundary"]["affected_nodes"]
    }


def _validate_capsule(
    capsule: Mapping[str, Any],
    *,
    capsule_path: Path,
    source_fragment: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    ordinal = int(source_fragment["chunk_ordinal"])
    canonical_rid = str(plan["observed_variants"]["canonical_hydro_realization_id"])
    minority_rid = str(plan["observed_variants"]["minority_hydro_realization_id"])
    affected = _affected_contexts(plan)

    if capsule.get("schema") != replay_capsule.SCHEMA:
        raise RuntimeError(f"unsupported replay capsule schema in {capsule_path}")
    for field in ("world_build_id", "chunk_ordinal", "global_cell_start", "global_cell_stop"):
        if str(capsule[field]) != str(source_fragment[field]):
            raise RuntimeError(f"replay capsule/source fragment mismatch for {field} at ordinal {ordinal}")
    if str(capsule["source_shard"]) != str(source_fragment["shard_name"]):
        raise RuntimeError(f"replay capsule source shard mismatch at ordinal {ordinal}")
    if str(capsule["source_chunk_sha256"]) != str(source_fragment["record"]["chunk_sha256"]):
        raise RuntimeError(f"replay capsule source chunk hash mismatch at ordinal {ordinal}")
    if str(capsule["source_phase05_sha256"]) != str(source_fragment["record"]["phase05_sha256"]):
        raise RuntimeError(f"replay capsule source phase-05 hash mismatch at ordinal {ordinal}")
    if str(capsule["source_hydro_realization_id"]) != minority_rid:
        raise RuntimeError(f"replay capsule minority realization mismatch at ordinal {ordinal}")
    if str(capsule["canonical_hydro_realization_id"]) != canonical_rid:
        raise RuntimeError(f"replay capsule canonical realization mismatch at ordinal {ordinal}")
    if capsule.get("minority_context_reconciliation_policy") != (
        replay_capsule.MINORITY_CONTEXT_RECONCILIATION_POLICY
    ):
        raise RuntimeError(f"replay capsule context reconciliation policy mismatch at ordinal {ordinal}")

    source_pools = {
        str(row["deposition_pool_id"]): dict(row)
        for row in source_fragment["deposition_pools"]
    }
    affected_source_ids = {
        pid for pid, row in source_pools.items() if str(row["node_id"]) in affected
    }
    replacements: dict[str, dict[str, Any]] = {}
    for replacement in capsule["pool_replacements"]:
        pid = str(replacement["deposition_pool_id"])
        if pid in replacements:
            raise RuntimeError(f"duplicate replay pool replacement {pid} at ordinal {ordinal}")
        if pid not in source_pools:
            raise RuntimeError(f"replay pool replacement {pid} is absent from source ordinal {ordinal}")
        old = dict(replacement["old"])
        canonical = dict(replacement["canonical"])
        if not _exact_equal(old, source_pools[pid]):
            raise RuntimeError(f"replay pool replacement {pid} does not match immutable source")
        node = str(old["node_id"])
        if node not in affected:
            raise RuntimeError(f"replay pool replacement {pid} lies outside the affected nodes")
        expected = dict(old)
        expected["hydro_realization_id"] = canonical_rid
        expected["hydro_context_score"] = float(affected[node]["canonical"])
        if not _exact_equal(canonical, expected):
            raise RuntimeError(f"replay pool replacement {pid} is not the exact planned canonical row")
        replacements[pid] = canonical
    if set(replacements) != affected_source_ids:
        missing = sorted(affected_source_ids - set(replacements))
        extra = sorted(set(replacements) - affected_source_ids)
        raise RuntimeError(
            f"replay pool coverage mismatch at ordinal {ordinal}: missing={missing} extra={extra}"
        )
    if int(capsule["affected_pool_count"]) != len(replacements):
        raise RuntimeError(f"replay affected-pool count mismatch at ordinal {ordinal}")

    replay_rows = list(capsule["replay_rows"])
    if int(capsule["affected_particle_count"]) != len(replay_rows):
        raise RuntimeError(f"replay affected-particle count mismatch at ordinal {ordinal}")
    actions: Counter[str] = Counter()
    allowed_actions = {"UNCHANGED_ABSENT", "UPDATE", "REMOVE", "ADD"}
    for row in replay_rows:
        action = str(row["external_action"])
        if action not in allowed_actions:
            raise RuntimeError(f"unsupported external replay action {action} at ordinal {ordinal}")
        if str(row["loss_node_id"]) not in affected:
            raise RuntimeError(f"replay particle lies outside affected nodes at ordinal {ordinal}")
        if str(row["old_hydro_realization_id"]) != minority_rid:
            raise RuntimeError(f"replay particle minority identity mismatch at ordinal {ordinal}")
        if str(row["canonical_hydro_realization_id"]) != canonical_rid:
            raise RuntimeError(f"replay particle canonical identity mismatch at ordinal {ordinal}")
        old_row = row.get("old_external_row")
        canonical_row = row.get("canonical_external_row")
        expected_presence = {
            "UNCHANGED_ABSENT": (False, False),
            "UPDATE": (True, True),
            "REMOVE": (True, False),
            "ADD": (False, True),
        }[action]
        if (old_row is not None, canonical_row is not None) != expected_presence:
            raise RuntimeError(f"replay external row presence mismatch at ordinal {ordinal}")
        actions[action] += 1
    supplied_actions = {str(key): int(value) for key, value in capsule["external_actions"].items()}
    if dict(sorted(actions.items())) != dict(sorted(supplied_actions.items())):
        raise RuntimeError(f"replay external action census mismatch at ordinal {ordinal}")
    delta = int(actions["ADD"] - actions["REMOVE"])
    if int(capsule["external_exchange_count_delta"]) != delta:
        raise RuntimeError(f"replay external count delta mismatch at ordinal {ordinal}")
    source_external = int(source_fragment["record"]["external_exchange_tails"])
    if int(capsule["external_exchange_count_old"]) != source_external:
        raise RuntimeError(f"replay source external count mismatch at ordinal {ordinal}")
    if int(capsule["external_exchange_count_canonical"]) != source_external + delta:
        raise RuntimeError(f"replay canonical external count mismatch at ordinal {ordinal}")

    return {
        "capsule_sha256": _file_sha256(capsule_path),
        "pool_replacements": replacements,
        "external_exchange_count_delta": delta,
        "external_actions": dict(sorted(actions.items())),
    }


def _load_capsules(
    capsule_dir: Path,
    *,
    expected_ordinals: Sequence[int],
) -> dict[int, tuple[Path, dict[str, Any]]]:
    paths = sorted(Path(capsule_dir).rglob("replay-*.json"))
    by_ordinal: dict[int, tuple[Path, dict[str, Any]]] = {}
    for path in paths:
        payload = _read_json(path)
        ordinal = int(payload["chunk_ordinal"])
        if ordinal in by_ordinal:
            raise RuntimeError(f"duplicate replay capsule for ordinal {ordinal}")
        by_ordinal[ordinal] = (path, payload)
    expected = {int(value) for value in expected_ordinals}
    if set(by_ordinal) != expected:
        raise RuntimeError(
            f"replay capsule ordinals mismatch: expected={sorted(expected)} found={sorted(by_ordinal)}"
        )
    return by_ordinal


def repair_fragments(
    *,
    fragment_dir: Path,
    capsule_dir: Path,
    plan_path: Path,
    out_dir: Path,
    certificate_path: Path,
    population_cells: int,
    chunk_cells: int,
    source_fragment_run_id: str = "",
    source_shard_run_id: str = "",
    cutoff_plan_run_id: str = "",
    replay_run_id: str = "",
    mend_code_sha: str = "",
) -> dict[str, Any]:
    plan_path = Path(plan_path)
    plan = _read_json(plan_path)
    world_id = str(plan["world_build_id"])
    canonical_rid = str(plan["observed_variants"]["canonical_hydro_realization_id"])
    minority_rid = str(plan["observed_variants"]["minority_hydro_realization_id"])
    fragment_counts = {
        str(key): int(value)
        for key, value in plan["observed_variants"]["fragment_counts"].items()
    }
    expected_affected_ordinals = [
        int(value) for value in plan["selective_replay"]["affected_minority_shard_ordinals"]
    ]
    affected = _affected_contexts(plan)

    ordered = assemble_fragments.preflight_fragments(
        fragment_dir,
        population_cells=int(population_cells),
        chunk_cells=int(chunk_cells),
        expected_world_build_id=world_id,
    )
    realization_counts: Counter[str] = Counter()
    signatures: dict[str, set[str]] = {canonical_rid: set(), minority_rid: set()}
    for _, fragment in ordered:
        if fragment.get("recovery") is not None:
            raise RuntimeError("source fragment set already contains a recovery overlay")
        rid = _single_realization_id(fragment)
        if rid not in signatures:
            raise RuntimeError(f"unplanned source hydro realization {rid}")
        realization_counts[rid] += 1
        signatures[rid].add(str(fragment["hydro_realization_signature"]))
    if dict(sorted(realization_counts.items())) != dict(sorted(fragment_counts.items())):
        raise RuntimeError(
            f"source fragment hydro census differs from cutoff plan: "
            f"source={dict(realization_counts)} plan={fragment_counts}"
        )
    for rid, values in signatures.items():
        if len(values) != 1:
            raise RuntimeError(f"source realization {rid} has {len(values)} hydro signatures")
    canonical_signature = next(iter(signatures[canonical_rid]))
    minority_signature = next(iter(signatures[minority_rid]))

    capsules = _load_capsules(capsule_dir, expected_ordinals=expected_affected_ordinals)
    capsule_validation: dict[int, dict[str, Any]] = {}
    source_by_ordinal = {int(fragment["chunk_ordinal"]): fragment for _, fragment in ordered}
    for ordinal, (path, capsule) in capsules.items():
        source_fragment = source_by_ordinal[ordinal]
        if _single_realization_id(source_fragment) != minority_rid:
            raise RuntimeError(f"replay capsule ordinal {ordinal} is not a minority fragment")
        capsule_validation[ordinal] = _validate_capsule(
            capsule,
            capsule_path=path,
            source_fragment=source_fragment,
            plan=plan,
        )

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if list(out_dir.rglob("*.fragment.json")):
        raise RuntimeError(f"repair output directory is not empty: {out_dir}")

    entries: list[dict[str, Any]] = []
    total_identity_replacements = 0
    total_context_replacements = 0
    total_external_delta = 0
    external_actions: Counter[str] = Counter()
    repaired_count = 0

    for source_path, source_fragment in ordered:
        ordinal = int(source_fragment["chunk_ordinal"])
        source_rid = _single_realization_id(source_fragment)
        out_path = out_dir / source_path.name
        if source_rid == canonical_rid:
            try:
                os.link(source_path, out_path)
            except OSError:
                shutil.copyfile(source_path, out_path)
            logical_fragment = fragment_io.read_fragment(out_path)
            entries.append({
                "chunk_ordinal": ordinal,
                "action": "RETAIN_CANONICAL_SOURCE",
                "source_fragment_sha256": str(source_fragment["fragment_sha256"]),
                "logical_fragment_sha256": str(logical_fragment["fragment_sha256"]),
                "source_hydro_realization_id": source_rid,
                "canonical_hydro_realization_id": canonical_rid,
                "source_chunk_sha256": str(source_fragment["record"]["chunk_sha256"]),
                "source_phase05_sha256": str(source_fragment["record"]["phase05_sha256"]),
            })
            continue

        repaired_count += 1
        logical_fragment = copy.deepcopy(source_fragment)
        source_fragment_sha = str(logical_fragment.pop("fragment_sha256"))
        capsule_info = capsule_validation.get(ordinal)
        source_affected_pool_ids = {
            str(row["deposition_pool_id"])
            for row in source_fragment["deposition_pools"]
            if str(row["node_id"]) in affected
        }
        replacements = capsule_info["pool_replacements"] if capsule_info is not None else {}
        if source_affected_pool_ids != set(replacements):
            raise RuntimeError(
                f"minority fragment {ordinal} affected-pool/capsule mismatch: "
                f"source={len(source_affected_pool_ids)} capsule={len(replacements)}"
            )

        logical_pools: list[dict[str, Any]] = []
        for source_pool in source_fragment["deposition_pools"]:
            pid = str(source_pool["deposition_pool_id"])
            if pid in replacements:
                pool = copy.deepcopy(replacements[pid])
            else:
                pool = copy.deepcopy(source_pool)
                pool["hydro_realization_id"] = canonical_rid
            logical_pools.append(pool)
        logical_fragment["deposition_pools"] = logical_pools
        logical_fragment["hydro_realization_signature"] = canonical_signature

        external_delta = int(
            capsule_info["external_exchange_count_delta"] if capsule_info is not None else 0
        )
        capsule_sha = str(capsule_info["capsule_sha256"] if capsule_info is not None else "")
        source_external = int(source_fragment["record"]["external_exchange_tails"])
        recovery = {
            "schema": fragment_io.RECOVERY_OVERLAY_SCHEMA,
            "policy": fragment_io.RECOVERY_OVERLAY_POLICY,
            "source_fragment_sha256": source_fragment_sha,
            "source_hydro_realization_id": minority_rid,
            "canonical_hydro_realization_id": canonical_rid,
            "source_hydro_realization_signature": minority_signature,
            "canonical_hydro_realization_signature": canonical_signature,
            "source_chunk_sha256": str(source_fragment["record"]["chunk_sha256"]),
            "source_phase05_sha256": str(source_fragment["record"]["phase05_sha256"]),
            "source_external_exchange_tails": source_external,
            "external_exchange_count_delta": external_delta,
            "canonical_external_exchange_tails": source_external + external_delta,
            "hydro_identity_replacement_count": len(logical_pools),
            "hydro_context_replacement_count": len(replacements),
            "replay_capsule_sha256": capsule_sha,
        }
        logical_fragment["recovery"] = recovery
        logical_fragment["fragment_sha256"] = fragment_io._fragment_hash(logical_fragment)
        out_path.write_text(
            json.dumps(logical_fragment, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        checked = fragment_io.read_fragment(out_path)
        if str(checked["fragment_sha256"]) != str(logical_fragment["fragment_sha256"]):
            raise RuntimeError(f"repaired fragment roundtrip hash mismatch at ordinal {ordinal}")

        total_identity_replacements += len(logical_pools)
        total_context_replacements += len(replacements)
        total_external_delta += external_delta
        if capsule_info is not None:
            external_actions.update(capsule_info["external_actions"])
        entries.append({
            "chunk_ordinal": ordinal,
            "action": "PROJECT_MINORITY_TO_CANONICAL",
            "source_fragment_sha256": source_fragment_sha,
            "logical_fragment_sha256": str(checked["fragment_sha256"]),
            "source_hydro_realization_id": minority_rid,
            "canonical_hydro_realization_id": canonical_rid,
            "source_chunk_sha256": str(source_fragment["record"]["chunk_sha256"]),
            "source_phase05_sha256": str(source_fragment["record"]["phase05_sha256"]),
            "hydro_identity_replacement_count": len(logical_pools),
            "hydro_context_replacement_count": len(replacements),
            "external_exchange_count_delta": external_delta,
            "replay_capsule_sha256": capsule_sha,
        })

    logical = assemble_fragments.preflight_fragments(
        out_dir,
        population_cells=int(population_cells),
        chunk_cells=int(chunk_cells),
        expected_world_build_id=world_id,
    )
    logical_ids = {_single_realization_id(fragment) for _, fragment in logical}
    logical_signatures = {str(fragment["hydro_realization_signature"]) for _, fragment in logical}
    if logical_ids != {canonical_rid} or logical_signatures != {canonical_signature}:
        raise RuntimeError("repaired fragment set did not converge to one canonical hydro realization")
    if repaired_count != fragment_counts[minority_rid]:
        raise RuntimeError("repaired minority fragment count differs from cutoff plan")
    if total_context_replacements != int(plan["selective_replay"]["affected_minority_pool_rows"]):
        raise RuntimeError("repaired affected pool count differs from cutoff plan")

    certificate: dict[str, Any] = {
        "schema": CERTIFICATE_SCHEMA,
        "policy": CERTIFICATE_POLICY,
        "world_build_id": world_id,
        "canonical_hydro_realization_id": canonical_rid,
        "canonical_hydro_realization_signature": canonical_signature,
        "minority_hydro_realization_id": minority_rid,
        "minority_hydro_realization_signature": minority_signature,
        "source": {
            "fragment_run_id": str(source_fragment_run_id),
            "shard_run_id": str(source_shard_run_id),
            "cutoff_plan_run_id": str(cutoff_plan_run_id),
            "replay_run_id": str(replay_run_id),
            "mend_code_sha": str(mend_code_sha),
            "cutoff_plan_sha256": _file_sha256(plan_path),
        },
        "counts": {
            "source_fragments": len(ordered),
            "retained_canonical_fragments": fragment_counts[canonical_rid],
            "repaired_minority_fragments": repaired_count,
            "capsule_backed_fragments": len(capsules),
            "hydro_identity_replacement_rows": total_identity_replacements,
            "hydro_context_replacement_rows": total_context_replacements,
            "external_exchange_count_delta": total_external_delta,
        },
        "external_actions": dict(sorted(external_actions.items())),
        "entries": entries,
    }
    certificate["certificate_sha256"] = fragment_io._fragment_hash(certificate)
    certificate_path = Path(certificate_path)
    certificate_path.parent.mkdir(parents=True, exist_ok=True)
    certificate_path.write_text(
        json.dumps(certificate, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    checked_certificate = _read_json(certificate_path)
    supplied = str(checked_certificate.pop("certificate_sha256"))
    if supplied != fragment_io._fragment_hash(checked_certificate):
        raise RuntimeError("phase-07 repair certificate roundtrip hash mismatch")
    certificate["certificate_sha256"] = supplied
    return certificate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fragments-dir", type=Path, required=True)
    parser.add_argument("--capsules-dir", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--out-fragments-dir", type=Path, required=True)
    parser.add_argument("--certificate", type=Path, required=True)
    parser.add_argument("--population-cells", type=int, default=37100)
    parser.add_argument("--chunk-cells", type=int, default=64)
    parser.add_argument("--source-fragment-run-id", default="")
    parser.add_argument("--source-shard-run-id", default="")
    parser.add_argument("--cutoff-plan-run-id", default="")
    parser.add_argument("--replay-run-id", default="")
    parser.add_argument("--mend-code-sha", default="")
    args = parser.parse_args()
    result = repair_fragments(
        fragment_dir=args.fragments_dir,
        capsule_dir=args.capsules_dir,
        plan_path=args.plan,
        out_dir=args.out_fragments_dir,
        certificate_path=args.certificate,
        population_cells=args.population_cells,
        chunk_cells=args.chunk_cells,
        source_fragment_run_id=args.source_fragment_run_id,
        source_shard_run_id=args.source_shard_run_id,
        cutoff_plan_run_id=args.cutoff_plan_run_id,
        replay_run_id=args.replay_run_id,
        mend_code_sha=args.mend_code_sha,
    )
    print(json.dumps({
        "certificate": str(args.certificate),
        "certificate_sha256": result["certificate_sha256"],
        "world_build_id": result["world_build_id"],
        "canonical_hydro_realization_id": result["canonical_hydro_realization_id"],
        "counts": result["counts"],
        "external_actions": result["external_actions"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
