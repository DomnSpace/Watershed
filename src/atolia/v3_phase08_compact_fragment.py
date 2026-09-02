#!/usr/bin/env python3
from __future__ import annotations

"""Compact one mended Phase-07 shard for the Dr. Corrosion player substrate.

This is the real Phase-08 extraction boundary.  It does not dump every Phase-02
lineage.  Instead it:

* validates the immutable Phase-01..05 shard once through the Phase-07 marker;
* applies the successful Phase-07 hydro mend only in memory;
* groups the loss population back into empirical (production-cell, loss-node)
  profiles, preserving exact population / recorded weights;
* stores weighted moments and sparse categorical/source/operation tables;
* retains a small deterministic weighted set of *actual* joint lineage rows per
  profile rather than synthesising Gaussian pseudo-objects;
* keeps sparse external-exchange tails exactly;
* tokenises developer identities before writing the fragment;
* emits deterministic gzip JSON small enough for distributed extraction and a
  later browser-native global packer.

The fragment is an intermediate sampling product, not a player-visible dossier.
"""

import argparse
from collections import defaultdict
import copy
import gzip
import hashlib
import heapq
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import v3_phase08_extract_shard as source_reader
import v3_phase08_runtime_fragment as phase08


SCHEMA = "atolia-v3-phase08-compact-sampler-fragment-v1"
COMPRESSION_POLICY = (
    "cell-lossnode-profile; exact-profile-weights; weighted-joint-real-lineage-representatives; "
    "exact-external-tail; sparse-source-operation-categorical-tables; no-synthetic-object"
)
REPRESENTATIVES_PER_PROFILE = 2

PROFILE_PHASE01_FIELDS = (
    "expected_recycle_count",
    "expected_repair_count",
    "expected_source_entropy",
    "expected_field_crossings",
    "expected_physical_crossings",
    "route_distance_from_origin_km",
)
REP_NUMERIC_FIELDS = (
    "metal_mass_kg",
    "ore_distance_km",
    "cumulative_metal_distance_km",
    "current_object_distance_km",
    "source_entropy",
)
OP_METRIC_FIELDS = (
    "capability",
    "operator_skill",
    "tool_fit",
    "support_fit",
    "thermal_fit",
    "measurement_fit",
    "material_fit",
)


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def logical_hash(payload: Mapping[str, Any]) -> str:
    clean = copy.deepcopy(dict(payload))
    clean.pop("fragment_sha256", None)
    return hashlib.sha256(_stable_json(clean).encode("utf-8")).hexdigest()


def _dict_index(values: Sequence[str]) -> tuple[list[str], dict[str, int]]:
    rows = sorted({str(value) for value in values})
    return rows, {value: index for index, value in enumerate(rows)}


def _weighted_priority(identity: str, weight: float) -> float:
    """Deterministic exponential-race score; smaller is better."""
    digest = hashlib.sha256(("phase08-representative|" + identity).encode("utf-8")).digest()
    seed = int.from_bytes(digest[:8], "big")
    u = (seed + 0.5) / 2**64
    return -math.log(max(1e-300, u)) / max(1e-300, float(weight))


class WeightedMoments:
    __slots__ = ("weight", "wx", "wx2")

    def __init__(self) -> None:
        self.weight = 0.0
        self.wx: dict[str, float] = defaultdict(float)
        self.wx2: dict[str, float] = defaultdict(float)

    def add(self, weight: float, **values: float) -> None:
        w = max(0.0, float(weight))
        if w <= 0.0:
            return
        self.weight += w
        for key, raw in values.items():
            x = float(raw)
            self.wx[key] += w * x
            self.wx2[key] += w * x * x

    def pair(self, key: str) -> list[float]:
        if self.weight <= 0.0:
            return [0.0, 0.0]
        mean = self.wx.get(key, 0.0) / self.weight
        second = self.wx2.get(key, 0.0) / self.weight
        return [float(mean), float(max(0.0, second - mean * mean))]


class ProfileAccumulator:
    def __init__(self, cell_index: int, node_token: str) -> None:
        self.cell_index = int(cell_index)
        self.node_token = str(node_token)
        self.lineages = 0
        self.loss_intensity = 0.0
        self.represented_weight = 0.0
        self.recorded_weight = 0.0
        self.step_min = 2**31 - 1
        self.step_max = -1
        self.phase01 = WeightedMoments()
        self.physical = WeightedMoments()
        self.mode_recorded: dict[str, float] = defaultdict(float)
        self.element_recorded: dict[str, float] = defaultdict(float)
        self.source_recorded: dict[str, float] = defaultdict(float)
        self.pb_source_recorded: dict[str, float] = defaultdict(float)
        self.operation_recorded: dict[str, float] = defaultdict(float)
        self.op_metrics = WeightedMoments()
        self.rep_heap: list[tuple[float, str, dict[str, Any]]] = []

    def add_rep(self, identity: str, weight: float, row: dict[str, Any], limit: int) -> None:
        # heap keeps the worst (largest score) as the most negative first key.
        score = _weighted_priority(identity, weight)
        item = (-score, str(identity), row)
        if len(self.rep_heap) < limit:
            heapq.heappush(self.rep_heap, item)
            return
        worst_score = -self.rep_heap[0][0]
        worst_identity = self.rep_heap[0][1]
        if (score, str(identity)) < (worst_score, worst_identity):
            heapq.heapreplace(self.rep_heap, item)

    def representatives(self) -> list[dict[str, Any]]:
        rows = [(-neg_score, identity, row) for neg_score, identity, row in self.rep_heap]
        rows.sort(key=lambda item: (item[0], item[1]))
        return [row for _, _, row in rows]


def _chemistry_maps(metallurgy: Mapping[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[int, list[dict[str, Any]]], dict[int, list[dict[str, Any]]]]:
    batch = {str(row["batch_id"]): dict(row) for row in metallurgy["chemistry_batches"]}
    elements: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in metallurgy["elements"]:
        elements[int(row["chemistry_batch_index"])].append(dict(row))
    pb_sources: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in metallurgy["source_pb"]:
        pb_sources[int(row["chemistry_batch_index"])].append(dict(row))
    return batch, elements, pb_sources


def _lineage_ancestry(biography: Mapping[str, Any]) -> dict[int, list[dict[str, Any]]]:
    result: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in biography["ancestry"]:
        result[int(row["batch_index"])].append(dict(row))
    return result


def build_compact_payload(
    *,
    world_build_id: str,
    ordinal: int,
    record: Mapping[str, Any],
    recovery: Mapping[str, Any],
    spine: Mapping[str, Any],
    biography: Mapping[str, Any],
    metallurgy: Mapping[str, Any],
    workshop: Mapping[str, Any],
    phase05: Mapping[str, Any],
    representatives_per_profile: int = REPRESENTATIVES_PER_PROFILE,
) -> dict[str, Any]:
    if representatives_per_profile <= 0:
        raise ValueError("representatives_per_profile must be positive")

    cells_by_index = {int(row["cell_index"]): dict(row) for row in spine["cells"]}
    losses = {
        (int(row["cell_index"]), int(row["cell_loss_index"])): dict(row)
        for row in spine["loss_strata"]
    }
    particles = [dict(row) for row in biography["particles"]]
    if len(particles) != len(losses):
        raise RuntimeError(
            f"Phase-08 compact population mismatch before aggregation: particles={len(particles)} losses={len(losses)}"
        )

    ancestry = _lineage_ancestry(biography)
    chemistry_by_id, elements_by_chem, pb_sources_by_chem = _chemistry_maps(metallurgy)

    operations_by_particle: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in workshop["operations"]:
        operations_by_particle[str(row["particle_id"])].append(dict(row))

    assignments = {str(row["particle_id"]): dict(row) for row in phase05["deposition_assignments"]}
    observations = {str(row["particle_id"]): dict(row) for row in phase05["archaeology"]}
    external = {str(row["particle_id"]): dict(row) for row in phase05["external_exchange"]}

    profiles: dict[tuple[int, str], ProfileAccumulator] = {}
    exact_tails: list[dict[str, Any]] = []

    for particle in particles:
        pid = str(particle["particle_id"])
        cell_index = int(particle["production_cell_index"])
        loss_key = (cell_index, int(particle["cell_loss_index"]))
        loss = losses.get(loss_key)
        if loss is None:
            raise RuntimeError(f"Phase-08 compact lineage cannot join Phase-01 loss: {pid}")
        assignment = assignments.get(pid)
        observation = observations.get(pid)
        if assignment is None or observation is None:
            raise RuntimeError(f"Phase-08 compact lineage lacks Phase-05 row: {pid}")

        node_token = phase08.anonymous_token(world_build_id, "node", loss["node_id"])
        key = (cell_index, node_token)
        acc = profiles.get(key)
        if acc is None:
            acc = ProfileAccumulator(cell_index, node_token)
            profiles[key] = acc

        loss_weight = float(loss["loss_intensity"])
        represented = float(particle["represented_weight"])
        recorded = float(observation["recorded_weight"])
        acc.lineages += 1
        acc.loss_intensity += loss_weight
        acc.represented_weight += represented
        acc.recorded_weight += recorded
        acc.step_min = min(acc.step_min, int(loss["step"]))
        acc.step_max = max(acc.step_max, int(loss["step"]))
        acc.phase01.add(
            loss_weight,
            **{name: float(loss[name]) for name in PROFILE_PHASE01_FIELDS},
        )

        batch_id = str(particle["metal_batch_id"])
        chemistry = chemistry_by_id.get(batch_id)
        if chemistry is None:
            raise RuntimeError(f"Phase-08 compact lineage lacks Phase-03 chemistry: {pid} / {batch_id}")
        chem_index = int(chemistry["chemistry_batch_index"])
        physical_values = {name: float(particle[name]) for name in REP_NUMERIC_FIELDS}
        physical_values.update({
            "remelt_count": float(particle["remelt_count"]),
            "repair_count": float(particle["repair_count"]),
            "Pb206_204": float(chemistry["Pb206_204"]),
            "Pb207_204": float(chemistry["Pb207_204"]),
            "Pb208_204": float(chemistry["Pb208_204"]),
            "hydro_context_score": float(assignment["hydro_context_score"]),
            "p_survival": float(observation["p_survival"]),
            "p_discovery": float(observation["p_discovery"]),
            "p_record": float(observation["p_record"]),
        })
        acc.physical.add(recorded, **physical_values)
        mode = str(assignment["mode"])
        acc.mode_recorded[mode] += recorded

        for row in elements_by_chem.get(chem_index, ()):  # weighted observed chemistry composition
            acc.element_recorded[str(row["element"])] += recorded * float(row["mass_fraction"])
        for row in ancestry.get(int(particle["final_batch_index"]), ()):
            source_token = phase08.anonymous_token(world_build_id, "source", row["source_id"])
            acc.source_recorded[source_token] += recorded * float(row["fraction"])
        for row in pb_sources_by_chem.get(chem_index, ()):
            source_token = phase08.anonymous_token(world_build_id, "source", row["source_id"])
            acc.pb_source_recorded[source_token] += recorded * float(row["fraction_of_pb"])

        lineage_ops = operations_by_particle.get(pid, ())
        op_counts: dict[str, int] = defaultdict(int)
        for op in lineage_ops:
            op_type = str(op["operation_type"])
            op_counts[op_type] += 1
            acc.operation_recorded[op_type] += recorded
            acc.op_metrics.add(recorded, **{name: float(op[name]) for name in OP_METRIC_FIELDS})

        rep = {
            "represented_weight": represented,
            "recorded_weight": recorded,
            "numeric": [
                physical_values[name]
                for name in (*REP_NUMERIC_FIELDS, "remelt_count", "repair_count", "Pb206_204", "Pb207_204", "Pb208_204", "hydro_context_score", "p_survival", "p_discovery", "p_record")
            ],
            "mode": mode,
            "elements": [
                [str(row["element"]), float(row["mass_fraction"])]
                for row in sorted(elements_by_chem.get(chem_index, ()), key=lambda item: str(item["element"]))
                if float(row["mass_fraction"]) != 0.0
            ],
            "sources": [
                [phase08.anonymous_token(world_build_id, "source", row["source_id"]), float(row["fraction"])]
                for row in sorted(ancestry.get(int(particle["final_batch_index"]), ()), key=lambda item: str(item["source_id"]))
                if float(row["fraction"]) != 0.0
            ],
            "pb_sources": [
                [phase08.anonymous_token(world_build_id, "source", row["source_id"]), float(row["fraction_of_pb"])]
                for row in sorted(pb_sources_by_chem.get(chem_index, ()), key=lambda item: str(item["source_id"]))
                if float(row["fraction_of_pb"]) != 0.0
            ],
            "operations": [[name, int(op_counts[name])] for name in sorted(op_counts)],
        }
        acc.add_rep(pid, max(recorded, 1e-30), rep, representatives_per_profile)

        tail = external.get(pid)
        if tail is not None:
            exact_tails.append({
                "profile_key": key,
                "component": str(tail["external_component_id"]),
                "trigger": str(tail["trigger"]),
                "contact_probability": float(tail["contact_probability"]),
                "contact_intensity": float(tail["contact_intensity"]),
                "represented_weight": float(tail["represented_weight"]),
                "recorded_weight": recorded,
            })

    profile_keys = sorted(profiles)
    profile_index = {key: index for index, key in enumerate(profile_keys)}

    node_values, node_idx = _dict_index([key[1] for key in profile_keys] + [
        phase08.anonymous_token(world_build_id, "node", row["origin"])
        for row in cells_by_index.values()
    ] + [
        phase08.anonymous_token(world_build_id, "node", row["destination"])
        for row in cells_by_index.values()
    ])
    bundle_values, bundle_idx = _dict_index([
        phase08.anonymous_token(world_build_id, "bundle", row["bundle_id"])
        for row in cells_by_index.values()
    ])
    family_values, family_idx = _dict_index([str(row["bundle_family"]) for row in cells_by_index.values()])
    class_values, class_idx = _dict_index([str(row["object_class"]) for row in cells_by_index.values()])
    mode_values, mode_idx = _dict_index([
        mode for acc in profiles.values() for mode in acc.mode_recorded
    ] + [rep["mode"] for acc in profiles.values() for rep in acc.representatives()])
    element_values, element_idx = _dict_index([
        name for acc in profiles.values() for name in acc.element_recorded
    ] + [name for acc in profiles.values() for rep in acc.representatives() for name, _ in rep["elements"]])
    source_values, source_idx = _dict_index([
        name for acc in profiles.values() for name in acc.source_recorded
    ] + [name for acc in profiles.values() for name in acc.pb_source_recorded]
      + [name for acc in profiles.values() for rep in acc.representatives() for name, _ in rep["sources"]]
      + [name for acc in profiles.values() for rep in acc.representatives() for name, _ in rep["pb_sources"]]
      + [phase08.anonymous_token(world_build_id, "source", raw)
         for row in cells_by_index.values()
         for raw in phase08._json_weights(row["source_mix_json"])]
    )
    op_values, op_idx = _dict_index([
        name for acc in profiles.values() for name in acc.operation_recorded
    ] + [name for acc in profiles.values() for rep in acc.representatives() for name, _ in rep["operations"]])
    component_values, component_idx = _dict_index([row["component"] for row in exact_tails])
    trigger_values, trigger_idx = _dict_index([row["trigger"] for row in exact_tails])

    cell_indices = sorted(cells_by_index)
    cell_local = {global_index: local for local, global_index in enumerate(cell_indices)}
    cell_rows: list[list[Any]] = []
    cell_sources: list[list[Any]] = []
    for global_index in cell_indices:
        row = cells_by_index[global_index]
        local = cell_local[global_index]
        cell_rows.append([
            int(global_index),
            bundle_idx[phase08.anonymous_token(world_build_id, "bundle", row["bundle_id"])],
            family_idx[str(row["bundle_family"])],
            class_idx[str(row["object_class"])],
            int(row["date_bc"]),
            node_idx[phase08.anonymous_token(world_build_id, "node", row["origin"])],
            node_idx[phase08.anonymous_token(world_build_id, "node", row["destination"])],
            float(row["production_intensity"]),
            float(row["circulation_seed_intensity"]),
            float(row["recycle_mean"]),
        ])
        for source, weight in sorted(phase08._json_weights(row["source_mix_json"]).items()):
            if float(weight) == 0.0:
                continue
            token = phase08.anonymous_token(world_build_id, "source", source)
            cell_sources.append([local, source_idx[token], float(weight)])

    profile_rows: list[list[Any]] = []
    profile_modes: list[list[Any]] = []
    profile_elements: list[list[Any]] = []
    profile_sources: list[list[Any]] = []
    profile_pb_sources: list[list[Any]] = []
    profile_operations: list[list[Any]] = []
    representatives: list[list[Any]] = []
    rep_elements: list[list[Any]] = []
    rep_sources: list[list[Any]] = []
    rep_pb_sources: list[list[Any]] = []
    rep_operations: list[list[Any]] = []

    physical_order = [
        *REP_NUMERIC_FIELDS,
        "remelt_count", "repair_count",
        "Pb206_204", "Pb207_204", "Pb208_204",
        "hydro_context_score", "p_survival", "p_discovery", "p_record",
    ]
    for pidx, key in enumerate(profile_keys):
        acc = profiles[key]
        profile_rows.append([
            cell_local[acc.cell_index],
            node_idx[acc.node_token],
            int(acc.lineages),
            float(acc.loss_intensity),
            float(acc.represented_weight),
            float(acc.recorded_weight),
            int(acc.step_min),
            int(acc.step_max),
            *[value for name in PROFILE_PHASE01_FIELDS for value in acc.phase01.pair(name)],
            *[value for name in physical_order for value in acc.physical.pair(name)],
            *[value for name in OP_METRIC_FIELDS for value in acc.op_metrics.pair(name)],
        ])
        denom = max(1e-300, acc.recorded_weight)
        for name in sorted(acc.mode_recorded):
            profile_modes.append([pidx, mode_idx[name], float(acc.mode_recorded[name] / denom)])
        for name in sorted(acc.element_recorded):
            profile_elements.append([pidx, element_idx[name], float(acc.element_recorded[name] / denom)])
        for name in sorted(acc.source_recorded):
            profile_sources.append([pidx, source_idx[name], float(acc.source_recorded[name] / denom)])
        for name in sorted(acc.pb_source_recorded):
            profile_pb_sources.append([pidx, source_idx[name], float(acc.pb_source_recorded[name] / denom)])
        for name in sorted(acc.operation_recorded):
            profile_operations.append([pidx, op_idx[name], float(acc.operation_recorded[name] / denom)])

        reps = acc.representatives()
        rep_mass = float(acc.recorded_weight / max(1, len(reps)))
        for rep in reps:
            ridx = len(representatives)
            representatives.append([
                pidx,
                rep_mass,
                float(rep["represented_weight"]),
                float(rep["recorded_weight"]),
                mode_idx[rep["mode"]],
                *[float(value) for value in rep["numeric"]],
            ])
            for name, value in rep["elements"]:
                rep_elements.append([ridx, element_idx[name], float(value)])
            for name, value in rep["sources"]:
                rep_sources.append([ridx, source_idx[name], float(value)])
            for name, value in rep["pb_sources"]:
                rep_pb_sources.append([ridx, source_idx[name], float(value)])
            for name, count in rep["operations"]:
                rep_operations.append([ridx, op_idx[name], int(count)])

    tail_rows = [
        [
            profile_index[row["profile_key"]],
            component_idx[row["component"]],
            trigger_idx[row["trigger"]],
            float(row["contact_probability"]),
            float(row["contact_intensity"]),
            float(row["represented_weight"]),
            float(row["recorded_weight"]),
        ]
        for row in sorted(
            exact_tails,
            key=lambda item: (
                profile_index[item["profile_key"]], item["component"], item["trigger"],
                item["contact_probability"], item["contact_intensity"], item["represented_weight"],
            ),
        )
    ]

    total_recorded = math.fsum(float(row["recorded_weight"]) for row in observations.values())
    total_represented = math.fsum(float(row["represented_weight"]) for row in particles)
    total_loss = math.fsum(float(row["loss_intensity"]) for row in losses.values())
    if not math.isclose(
        total_recorded,
        math.fsum(float(row[5]) for row in profile_rows),
        rel_tol=2e-13,
        abs_tol=1e-14,
    ):
        raise RuntimeError("Phase-08 compact recorded-weight conservation failed")
    if not math.isclose(
        total_represented,
        math.fsum(float(row[4]) for row in profile_rows),
        rel_tol=2e-13,
        abs_tol=1e-14,
    ):
        raise RuntimeError("Phase-08 compact represented-weight conservation failed")
    if not math.isclose(
        total_loss,
        math.fsum(float(row[3]) for row in profile_rows),
        rel_tol=2e-13,
        abs_tol=1e-14,
    ):
        raise RuntimeError("Phase-08 compact loss-intensity conservation failed")
    if len(tail_rows) != len(external):
        raise RuntimeError("Phase-08 compact exact external-tail population changed")

    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "compression_policy": COMPRESSION_POLICY,
        "representatives_per_profile": int(representatives_per_profile),
        "world_build_id": str(world_build_id),
        "chunk_ordinal": int(ordinal),
        "global_cell_start": int(record["global_cell_start"]),
        "global_cell_stop": int(record["global_cell_stop"]),
        "source": {
            "chunk_sha256": str(record["chunk_sha256"]),
            "phase01_spine_sha256": str(record["phase01_spine_sha256"]),
            "phase02_biography_sha256": str(record["phase02_biography_sha256"]),
            "phase03_metallurgy_sha256": str(record["phase03_metallurgy_sha256"]),
            "phase04_workshop_sha256": str(record["phase04_workshop_sha256"]),
            "phase05_sha256": str(record["phase05_sha256"]),
        },
        "recovery": dict(recovery),
        "columns": {
            "cell": ["global_cell_index", "bundle", "family", "object_class", "date_bc", "origin_node", "destination_node", "production_intensity", "circulation_seed_intensity", "recycle_mean"],
            "cell_source": ["cell", "source", "weight"],
            "profile": [
                "cell", "loss_node", "lineage_count", "loss_intensity", "represented_weight", "recorded_weight", "step_min", "step_max",
                *[f"{name}_{suffix}" for name in PROFILE_PHASE01_FIELDS for suffix in ("mean", "variance")],
                *[f"{name}_{suffix}" for name in physical_order for suffix in ("mean", "variance")],
                *[f"operation_{name}_{suffix}" for name in OP_METRIC_FIELDS for suffix in ("mean", "variance")],
            ],
            "profile_mode": ["profile", "mode", "recorded_fraction"],
            "profile_element": ["profile", "element", "recorded_mean_mass_fraction"],
            "profile_source": ["profile", "source", "recorded_mean_fraction"],
            "profile_pb_source": ["profile", "source", "recorded_mean_fraction_of_pb"],
            "profile_operation": ["profile", "operation_type", "recorded_mean_count"],
            "representative": [
                "profile", "representative_recorded_mass", "source_represented_weight", "source_recorded_weight", "mode",
                *physical_order,
            ],
            "representative_element": ["representative", "element", "mass_fraction"],
            "representative_source": ["representative", "source", "fraction"],
            "representative_pb_source": ["representative", "source", "fraction_of_pb"],
            "representative_operation": ["representative", "operation_type", "count"],
            "external_tail": ["profile", "component", "trigger", "contact_probability", "contact_intensity", "represented_weight", "recorded_weight"],
        },
        "dictionary": {
            "node": node_values,
            "bundle": bundle_values,
            "family": family_values,
            "object_class": class_values,
            "mode": mode_values,
            "element": element_values,
            "source": source_values,
            "operation_type": op_values,
            "external_component": component_values,
            "external_trigger": trigger_values,
        },
        "cells": cell_rows,
        "cell_sources": cell_sources,
        "profiles": profile_rows,
        "profile_modes": profile_modes,
        "profile_elements": profile_elements,
        "profile_sources": profile_sources,
        "profile_pb_sources": profile_pb_sources,
        "profile_operations": profile_operations,
        "representatives": representatives,
        "representative_elements": rep_elements,
        "representative_sources": rep_sources,
        "representative_pb_sources": rep_pb_sources,
        "representative_operations": rep_operations,
        "external_tails": tail_rows,
        "counts": {
            "cells": len(cell_rows),
            "lineages": len(particles),
            "profiles": len(profile_rows),
            "representatives": len(representatives),
            "external_tails": len(tail_rows),
        },
        "totals": {
            "loss_intensity": float(total_loss),
            "represented_weight": float(total_represented),
            "recorded_weight": float(total_recorded),
        },
    }
    payload["fragment_sha256"] = logical_hash(payload)
    return payload


def extract_compact_fragment(
    *,
    shard_path: Path,
    certificate_path: Path,
    ordinal: int,
    out_path: Path,
    capsule_path: Path | None = None,
    representatives_per_profile: int = REPRESENTATIVES_PER_PROFILE,
) -> dict[str, Any]:
    certificate = phase08._read_json(Path(certificate_path))
    phase08.validate_certificate(certificate)
    entry = phase08.certificate_entry(certificate, ordinal)
    record, spine, biography, metallurgy, workshop, source05 = source_reader.read_validated_source_shard(
        Path(shard_path), certificate=certificate, ordinal=ordinal
    )
    if str(record["chunk_sha256"]) != str(entry["source_chunk_sha256"]):
        raise RuntimeError("Phase-08 compact source chunk differs from repair certificate")
    if str(record["phase05_sha256"]) != str(entry["source_phase05_sha256"]):
        raise RuntimeError("Phase-08 compact source Phase-05 differs from repair certificate")

    capsule = None
    capsule_sha = ""
    if capsule_path is not None:
        capsule_path = Path(capsule_path)
        capsule = phase08._read_json(capsule_path)
        capsule_sha = phase08._file_sha256(capsule_path)
        if capsule_sha != str(entry.get("replay_capsule_sha256", "")):
            raise RuntimeError("Phase-08 compact replay capsule hash differs from repair certificate")
    elif str(entry.get("replay_capsule_sha256", "")):
        raise RuntimeError("Phase-08 compact affected shard requires --capsule")

    canonical05 = phase08.canonicalize_phase05(
        source05, certificate=certificate, entry=entry, capsule=capsule
    )
    recovery = {
        "certificate_sha256": str(certificate["certificate_sha256"]),
        "action": str(entry["action"]),
        "external_exchange_count_delta": int(entry.get("external_exchange_count_delta", 0)),
        "replay_capsule_sha256": capsule_sha,
    }
    payload = build_compact_payload(
        world_build_id=str(certificate["world_build_id"]),
        ordinal=ordinal,
        record=record,
        recovery=recovery,
        spine=spine,
        biography=biography,
        metallurgy=metallurgy,
        workshop=workshop,
        phase05=canonical05,
        representatives_per_profile=representatives_per_profile,
    )
    raw = (_stable_json(payload) + "\n").encode("utf-8")
    compressed = gzip.compress(raw, compresslevel=9, mtime=0)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(compressed)
    checked = json.loads(gzip.decompress(out_path.read_bytes()).decode("utf-8"))
    if str(checked["fragment_sha256"]) != logical_hash(checked):
        raise RuntimeError("Phase-08 compact gzip roundtrip hash mismatch")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shard", type=Path, required=True)
    parser.add_argument("--certificate", type=Path, required=True)
    parser.add_argument("--ordinal", type=int, required=True)
    parser.add_argument("--capsule", type=Path)
    parser.add_argument("--representatives-per-profile", type=int, default=REPRESENTATIVES_PER_PROFILE)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = extract_compact_fragment(
        shard_path=args.shard,
        certificate_path=args.certificate,
        ordinal=args.ordinal,
        capsule_path=args.capsule,
        representatives_per_profile=args.representatives_per_profile,
        out_path=args.out,
    )
    print(json.dumps({
        "schema": result["schema"],
        "world_build_id": result["world_build_id"],
        "chunk_ordinal": result["chunk_ordinal"],
        "counts": result["counts"],
        "totals": result["totals"],
        "fragment_sha256": result["fragment_sha256"],
        "output": str(args.out),
        "output_bytes": args.out.stat().st_size,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
