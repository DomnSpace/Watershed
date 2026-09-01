#!/usr/bin/env python3
from __future__ import annotations

"""Forensic probe for the Phase-07 hydro candidate cutoff bifurcation.

This does not repair, canonicalize, or alter the hydro topology.  It rebuilds only
canonical geography + the Phase-05 hydro candidate ranking and records exact
binary64 values around the selection boundary, together with runner/NumPy CPU
metadata.  The purpose is to explain why nominally deterministic canonical shard
workers produced two hydro signatures.
"""

import argparse
from contextlib import redirect_stdout
import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import struct
import subprocess
import sys
from typing import Any, Mapping

import numpy as np

import archaeology_temporal_world as archaeology
import campaign_substrate_cache as campaign_cache
import v3_hydro_exchange_deposition as phase05


SCHEMA = "atolia-v3-phase07-hydro-cutoff-forensics-v1"
DEFAULT_HYPOTHESIS = Path("hypotheses/atolia_atesis_1800_1000_v0.json")
TARGET_GEOGRAPHY_NODES = 1000
CUTOFF_WINDOW = 64
LEVANT_NILE_PREFIX = "dg_045_levant_north_nile_delta_"


def _stable(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha(value: Any) -> str:
    return hashlib.sha256(_stable(value).encode("utf-8")).hexdigest()


def _bits(value: float) -> int:
    return struct.unpack(">Q", struct.pack(">d", float(value)))[0]


def _float_record(value: float) -> dict[str, Any]:
    value = float(value)
    return {
        "value": value,
        "hex": value.hex(),
        "bits": f"0x{_bits(value):016x}",
        "ulp": float(math.ulp(value)),
    }


def _command_text(argv: list[str]) -> str:
    try:
        proc = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=8)
    except Exception as exc:  # pragma: no cover - diagnostic only
        return f"{type(exc).__name__}: {exc}"
    text = (proc.stdout or "") + (proc.stderr or "")
    return text.strip()


def _numpy_text(fn_name: str) -> str:
    fn = getattr(np, fn_name, None)
    if fn is None:
        return "unavailable"
    stream = io.StringIO()
    try:
        with redirect_stdout(stream):
            fn()
    except Exception as exc:  # pragma: no cover - diagnostic only
        return f"{type(exc).__name__}: {exc}"
    return stream.getvalue().strip()


def _cpuinfo() -> dict[str, Any]:
    model = None
    flags: list[str] = []
    path = Path("/proc/cpuinfo")
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if model is None and line.lower().startswith("model name"):
                model = line.split(":", 1)[-1].strip()
            if not flags and (line.lower().startswith("flags") or line.lower().startswith("features")):
                flags = line.split(":", 1)[-1].strip().split()
            if model is not None and flags:
                break
    return {
        "model": model,
        "flags": flags,
        "lscpu": _command_text(["lscpu"]),
    }


def _environment(replica: int) -> dict[str, Any]:
    return {
        "replica": int(replica),
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "numpy_version": np.__version__,
        "numpy_show_config": _numpy_text("show_config"),
        "numpy_show_runtime": _numpy_text("show_runtime"),
        "runner_name": os.environ.get("RUNNER_NAME"),
        "runner_os": os.environ.get("RUNNER_OS"),
        "runner_arch": os.environ.get("RUNNER_ARCH"),
        "image_os": os.environ.get("ImageOS"),
        "image_version": os.environ.get("ImageVersion"),
        "cpu": _cpuinfo(),
    }


def _node_record(world: Any, node_id: str) -> dict[str, Any]:
    node = world.nodes[node_id]
    return {
        "id": str(node_id),
        "kind": str(node.kind),
        "lon": _float_record(float(node.lon)),
        "lat": _float_record(float(node.lat)),
    }


def _rank_candidates(world: Any) -> tuple[list[tuple[float, str, str, float, float, float]], int, int]:
    evidence = phase05._structural_hydro_evidence(world)
    by_pair: dict[tuple[str, str], list[Any]] = {}
    for row in evidence:
        by_pair.setdefault(phase05._edge_key(row.a, row.b), []).append(row)
    structural_pairs = {
        phase05._edge_key(row.a, row.b)
        for row in evidence
        if row.evidence_kind == "model_graph_edge"
    }

    candidates: list[tuple[float, str, str, float, float, float]] = []
    water_nodes = [str(node.id) for node in world.nodes.values() if phase05._water_node(node.kind)]
    water_nodes.sort()
    for i, a in enumerate(water_nodes):
        for b in water_nodes[i + 1:]:
            key = phase05._edge_key(a, b)
            if key in structural_pairs:
                continue
            km = phase05._edge_km(world, a, b)
            if km > phase05.MAX_CANDIDATE_CONNECTOR_KM:
                continue
            p, nav, score = phase05._candidate_prior(world, a, b)
            candidates.append((score, a, b, p, nav, km))
    candidates.sort(key=lambda row: (-row[0], row[1], row[2]))

    target_extra = max(
        len([key for key in by_pair if key not in structural_pairs]),
        int(round(max(0.0, phase05.CANDIDATE_DENSITY_MULTIPLIER - 1.0) * max(1, len(structural_pairs)))),
    )
    return candidates, int(target_extra), len(structural_pairs)


def _candidate_record(
    world: Any,
    row: tuple[float, str, str, float, float, float],
    *,
    rank: int,
    target_extra: int,
    cutoff_score: float,
) -> dict[str, Any]:
    score, a, b, probability, navigability, km = row
    return {
        "rank": int(rank),
        "selected": bool(rank <= target_extra),
        "a": a,
        "b": b,
        "distance_km": _float_record(km),
        "probability": _float_record(probability),
        "navigability": _float_record(navigability),
        "score": _float_record(score),
        "score_bit_delta_from_cutoff": int(_bits(score) - _bits(cutoff_score)),
        "a_node": _node_record(world, a),
        "b_node": _node_record(world, b),
    }


def build_report(hypothesis: Mapping[str, Any], *, replica: int) -> dict[str, Any]:
    world_seed = int(campaign_cache.DEFAULT_CANONICAL_WORLD_SEED)
    workshops = int(campaign_cache.DEFAULT_WORKSHOPS)
    world = archaeology.TemporalFieldArchaeologicalWorld(
        hypothesis,
        seed=world_seed,
        target_geography_nodes=TARGET_GEOGRAPHY_NODES,
    )
    world.build(workshop_count=workshops)

    candidates, target_extra, structural_pair_count = _rank_candidates(world)
    if target_extra <= 0 or target_extra > len(candidates):
        raise RuntimeError(f"invalid hydro candidate cutoff: {target_extra}/{len(candidates)}")
    cutoff_score = float(candidates[target_extra - 1][0])

    lo = max(0, target_extra - CUTOFF_WINDOW - 1)
    hi = min(len(candidates), target_extra + CUTOFF_WINDOW)
    cutoff_window = [
        _candidate_record(
            world,
            row,
            rank=index + 1,
            target_extra=target_extra,
            cutoff_score=cutoff_score,
        )
        for index, row in enumerate(candidates[lo:hi], start=lo)
    ]

    corridor_rows = []
    for index, row in enumerate(candidates):
        _, a, b, _, _, _ = row
        if a.startswith(LEVANT_NILE_PREFIX) and b.startswith(LEVANT_NILE_PREFIX):
            corridor_rows.append(_candidate_record(
                world,
                row,
                rank=index + 1,
                target_extra=target_extra,
                cutoff_score=cutoff_score,
            ))

    selected_pairs = sorted((a, b) for _, a, b, _, _, _ in candidates[:target_extra])
    status, evidence, ensemble = phase05.build_hydro_ensemble(world)
    realization = phase05.realize_hydro(ensemble, world_seed=world_seed)
    provisional_pairs = sorted((row.a, row.b) for row in ensemble if not row.structural)
    if selected_pairs != provisional_pairs:
        raise RuntimeError("forensic reconstruction disagrees with build_hydro_ensemble selection")

    corridor_ensemble = [
        {
            "edge_id": row.edge_id,
            "a": row.a,
            "b": row.b,
            "probability": _float_record(row.probability),
            "navigability": _float_record(row.navigability),
            "probability_basis": row.probability_basis,
        }
        for row in ensemble
        if (not row.structural)
        and row.a.startswith(LEVANT_NILE_PREFIX)
        and row.b.startswith(LEVANT_NILE_PREFIX)
    ]
    realization_by_id = {row.edge_id: row for row in realization}
    for row in corridor_ensemble:
        rr = realization_by_id[row["edge_id"]]
        row["draw"] = _float_record(rr.draw)
        row["realized"] = bool(rr.realized)

    return {
        "schema": SCHEMA,
        "environment": _environment(replica),
        "world": {
            "seed": world_seed,
            "workshops": workshops,
            "target_geography_nodes": TARGET_GEOGRAPHY_NODES,
            "actual_nodes": len(world.nodes),
            "actual_edges": len(world.edges),
        },
        "hydro": {
            "status": status,
            "evidence_count": len(evidence),
            "structural_pair_count": structural_pair_count,
            "candidate_count": len(candidates),
            "target_extra": target_extra,
            "cutoff_rank_selected": target_extra,
            "first_excluded_rank": target_extra + 1,
            "cutoff_score": _float_record(cutoff_score),
            "selected_provisional_pair_sha256": _sha(selected_pairs),
            "selected_provisional_pairs": selected_pairs,
            "cutoff_window": cutoff_window,
            "levant_nile_corridor_candidates": corridor_rows,
            "levant_nile_corridor_ensemble": corridor_ensemble,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Probe Phase-07 hydro cutoff binary64 behavior")
    ap.add_argument("--hypothesis", type=Path, default=DEFAULT_HYPOTHESIS)
    ap.add_argument("--replica", type=int, default=0)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    hypothesis = json.loads(args.hypothesis.read_text(encoding="utf-8"))
    report = build_report(hypothesis, replica=args.replica)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "schema": report["schema"],
        "replica": report["environment"]["replica"],
        "numpy": report["environment"]["numpy_version"],
        "cpu": report["environment"]["cpu"]["model"],
        "target_extra": report["hydro"]["target_extra"],
        "pair_sha256": report["hydro"]["selected_provisional_pair_sha256"],
        "cutoff_score_hex": report["hydro"]["cutoff_score"]["hex"],
        "corridor_selected": [
            [row["a"], row["b"]]
            for row in report["hydro"]["levant_nile_corridor_ensemble"]
        ],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
