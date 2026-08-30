#!/usr/bin/env python3
from __future__ import annotations

"""Build the Atolia v3 phase-07 canonical full world as bounded NetCDF shards.

This stage adds no new hidden-world mechanism.  It executes the existing v1
propagation and phases 02--05 for every production cell while keeping peak memory
bounded by one contiguous production-cell shard.

Scientific identity is independent of storage chunk size.  Phase-02 particle IDs
use global production-cell indices, and the canonical manifest globally merges
shared deposition pools and tool-use summaries that are only partial inside an
individual shard.
"""

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any, Iterator, Mapping, Sequence

import netCDF4  # noqa: F401
from netCDF4 import Dataset


def _bootstrap_atolia_path() -> Path:
    candidates = [Path.cwd() / "src" / "atolia", Path.cwd()]
    for root in (Path("/home/pyodide/arcade_project"), Path("/home/pyodide/dvx_project")):
        candidates.extend((root / "src" / "atolia", root))
    for entry in list(sys.path):
        if entry:
            root = Path(entry)
            candidates.extend((root / "src" / "atolia", root))
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if (candidate / "archaeology_temporal_world.py").is_file():
            if key not in sys.path:
                sys.path.insert(0, key)
            return candidate
    raise ModuleNotFoundError("Could not locate Watershed src/atolia")


ATOLIA_DIR = _bootstrap_atolia_path()
PROJECT_ROOT = ATOLIA_DIR.parent.parent if ATOLIA_DIR.name == "atolia" else Path.cwd()

import archaeology_temporal_world as archaeology
import build_v3_master
import campaign_substrate_cache as campaign_cache
import intensity_circulation as intensity
import release_candidate_invariants as release_invariants
import v3_biography_netcdf
import v3_hydro_exchange_deposition as phase05
import v3_metal_biography as biography
import v3_metallurgy_netcdf
import v3_netcdf
import v3_phase05_netcdf
import v3_phase07_manifest as manifest
import v3_source_metallurgy
import v3_workshop_ecology
import v3_workshop_netcdf


CANONICAL_WORLD_SEED = campaign_cache.DEFAULT_CANONICAL_WORLD_SEED
CANONICAL_WORKSHOPS = campaign_cache.DEFAULT_WORKSHOPS
CANONICAL_STEPS = campaign_cache.DEFAULT_STEPS
CANONICAL_NODES = 1000
DEFAULT_CHUNK_CELLS = 512
DEFAULT_OUT_DIR = Path("cache/atolia_v3_canonical_full")


class SparseReportSequence(Sequence[Any]):
    """Global-index report view without allocating 37k placeholder objects per shard."""

    def __init__(self, population: int, reports: Sequence[Any], global_indices: Sequence[int]):
        if len(reports) != len(global_indices):
            raise ValueError("report/global index length mismatch")
        self._population = int(population)
        self._by_index = {int(i): report for i, report in zip(global_indices, reports)}
        self._empty = SimpleNamespace(loss_strata=())

    def __len__(self) -> int:
        return self._population

    def __getitem__(self, index: int | slice) -> Any:
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(self._population))]
        i = int(index)
        if i < 0:
            i += self._population
        if i < 0 or i >= self._population:
            raise IndexError(i)
        return self._by_index.get(i, self._empty)


def _hypothesis_sha(hypothesis: Mapping[str, Any]) -> str:
    return build_v3_master.canonical_hypothesis_sha256(hypothesis)


def _config(
    hypothesis: Mapping[str, Any],
    *,
    world_seed: int,
    workshops: int,
    steps: int,
    nodes: int,
    population_cells: int,
    materialized_cells: int,
    chunk_cells: int,
) -> dict[str, Any]:
    canonical_settings = (
        int(world_seed) == CANONICAL_WORLD_SEED
        and int(workshops) == CANONICAL_WORKSHOPS
        and int(steps) == CANONICAL_STEPS
        and int(nodes) == CANONICAL_NODES
    )
    if materialized_cells < population_cells:
        scope = "verification-prefix"
    elif canonical_settings:
        scope = "canonical-full"
    else:
        scope = "full-world-noncanonical-config"
    return {
        "product_scope": scope,
        "world_seed": int(world_seed),
        "workshop_count": int(workshops),
        "intensity_steps": int(steps),
        "target_geography_nodes": int(nodes),
        "hypothesis_sha256": _hypothesis_sha(hypothesis),
        "population_cells": int(population_cells),
        "materialized_cells": int(materialized_cells),
        "chunk_cells": int(chunk_cells),
        "intensity_model_version": intensity.INTENSITY_MODEL_VERSION,
        "biography_model_version": biography.BIOGRAPHY_MODEL_VERSION,
        "metallurgy_model_version": v3_source_metallurgy.SOURCE_METALLURGY_VERSION,
        "workshop_model_version": v3_workshop_ecology.WORKSHOP_MODEL_VERSION,
        "phase05_model_version": phase05.PHASE05_MODEL_VERSION,
    }


def _flow_summary(reports: Sequence[Any], population_cells: int) -> dict[str, Any]:
    totals = defaultdict(float)
    strata = 0
    max_nodes = 0
    for report in reports:
        for key in (
            "produced", "circulation_seed", "transfer_flux", "return_flux",
            "recycle_flux", "loss_flux", "retire_flux", "residual_active",
        ):
            totals[key] += float(getattr(report, key))
        strata += len(report.loss_strata)
        max_nodes = max(max_nodes, int(report.max_active_nodes))
    conservation = totals["circulation_seed"] - (
        totals["return_flux"] + totals["loss_flux"] + totals["retire_flux"] + totals["residual_active"]
    )
    return {
        "model_version": intensity.INTENSITY_MODEL_VERSION,
        "production_cells": len(reports),
        "available_production_cells": int(population_cells),
        "loss_strata": int(strata),
        **{key: float(value) for key, value in totals.items()},
        "conservation_error": float(conservation),
        "relative_conservation_error": float(conservation / max(1.0, totals["circulation_seed"])),
        "max_active_nodes": int(max_nodes),
        "transfer_flux_semantics": "internal_throughput",
        "recycle_flux_semantics": "internal_throughput",
        "canonical_shard": True,
    }


def _lineages_with_global_indices(
    world: Any,
    reports: Sequence[Any],
    global_indices: Sequence[int],
    *,
    world_seed: int,
) -> list[biography.MetalLineage]:
    if len(reports) != len(global_indices):
        raise ValueError("report/global production index length mismatch")
    out: list[biography.MetalLineage] = []
    for report, global_index in zip(reports, global_indices):
        for loss_index, stratum in enumerate(report.loss_strata):
            out.append(biography.materialize_loss_lineage(
                world,
                stratum,
                world_seed=int(world_seed),
                production_cell_index=int(global_index),
                cell_loss_index=int(loss_index),
            ))
    return out


def _write_global_spine_shard(
    path: Path,
    *,
    reports: Sequence[Any],
    global_indices: Sequence[int],
    flow_summary: Mapping[str, Any],
    config: Mapping[str, Any],
    release_version: str,
    production_mass_error_kg: float,
) -> dict[str, Any]:
    summary = v3_netcdf.write_spine_master(
        path,
        reports=reports,
        flow_summary=flow_summary,
        world_seed=int(config["world_seed"]),
        workshop_count=int(config["workshop_count"]),
        intensity_steps=int(config["intensity_steps"]),
        hypothesis_sha256=str(config["hypothesis_sha256"]),
        release_invariants_version=str(release_version),
        production_mass_error_kg=float(production_mass_error_kg),
        target_geography_nodes=int(config["target_geography_nodes"]),
    )
    cells = v3_netcdf.cell_rows_from_reports(reports)
    losses = v3_netcdf.loss_rows_from_reports(reports)
    local_to_global = {local: int(global_indices[local]) for local in range(len(global_indices))}
    for row in cells:
        row["cell_index"] = local_to_global[int(row["cell_index"])]
    for row in losses:
        row["cell_index"] = local_to_global[int(row["cell_index"])]
    digest = v3_netcdf.spine_hash(cells, losses, flow_summary)
    with Dataset(path, "r+") as ds:
        ds.groups["cells"].variables["cell_index"][:] = [int(row["cell_index"]) for row in cells]
        ds.groups["loss_strata"].variables["cell_index"][:] = [int(row["cell_index"]) for row in losses]
        ds.spine_sha256 = digest
        ds.product_kind = "canonical_full_shard"
        ds.phase01_cell_index_scope = "global-production-cell-index"
    summary["spine_sha256"] = digest
    return summary


def _static_workshop_signature(read04: Mapping[str, Any]) -> str:
    names = ("workshops", "guilds", "memberships", "tool_archetypes", "archetype_operations", "tools")
    payload = {name: read04[name] for name in names}
    return hashlib.sha256(manifest.stable_json(payload).encode("utf-8")).hexdigest()


def _hydro_signature(read05: Mapping[str, Any]) -> str:
    payload = {
        "hydro_evidence": read05["hydro_evidence"],
        "hydro_ensemble": read05["hydro_ensemble"],
        "hydro_realization": read05["hydro_realization"],
    }
    return hashlib.sha256(manifest.stable_json(payload).encode("utf-8")).hexdigest()


def _write_chunk_marker(
    path: Path,
    *,
    record: Mapping[str, Any],
    flow_summary: Mapping[str, Any],
) -> None:
    with Dataset(path, "a") as ds:
        if "canonical_chunk" in ds.groups:
            raise RuntimeError("canonical chunk marker already exists")
        group = ds.createGroup("canonical_chunk")
        group.world_build_id = str(record["world_build_id"])
        group.chunk_sha256 = str(record["chunk_sha256"])
        group.chunk_ordinal = int(record["chunk_ordinal"])
        group.global_cell_start = int(record["global_cell_start"])
        group.global_cell_stop = int(record["global_cell_stop"])
        group.cell_count = int(record["cell_count"])
        group.record_json = manifest.stable_json({k: v for k, v in record.items() if not k.startswith("_")})
        group.flow_summary_json = manifest.stable_json(flow_summary)
        group.pool_scope = "shard-partial; canonical aggregate stored in phase07 manifest"
        group.tool_use_scope = "shard-partial; canonical aggregate stored in phase07 manifest"
        ds.phase07_world_build_id = str(record["world_build_id"])
        ds.phase07_chunk_sha256 = str(record["chunk_sha256"])
        ds.phase07_chunk_ordinal = int(record["chunk_ordinal"])


def _read_existing_shard(
    path: Path,
    *,
    expected_world_build_id: str,
    ordinal: int,
    start: int,
    stop: int,
) -> tuple[dict[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    spine = v3_netcdf.read_spine_master(path)
    bio = v3_biography_netcdf.read_biography(path)
    metal = v3_metallurgy_netcdf.read_metallurgy(path)
    read04 = v3_workshop_netcdf.read_workshop_layer(path)
    read05 = v3_phase05_netcdf.read_phase05(path)
    with Dataset(path, "r") as ds:
        if "canonical_chunk" not in ds.groups:
            raise RuntimeError("existing shard lacks phase-07 chunk marker")
        group = ds.groups["canonical_chunk"]
        record = json.loads(str(group.record_json))
        flow = json.loads(str(group.flow_summary_json))
    if str(record["world_build_id"]) != str(expected_world_build_id):
        raise RuntimeError("existing shard belongs to a different canonical world")
    if (int(record["chunk_ordinal"]), int(record["global_cell_start"]), int(record["global_cell_stop"])) != (int(ordinal), int(start), int(stop)):
        raise RuntimeError("existing shard chunk coordinates do not match requested build")
    if record["phase01_spine_sha256"] != spine["spine_sha256"]:
        raise RuntimeError("existing shard phase-01 marker mismatch")
    if record["phase02_biography_sha256"] != bio["biography_sha256"]:
        raise RuntimeError("existing shard phase-02 marker mismatch")
    if record["phase03_metallurgy_sha256"] != metal["metallurgy_sha256"]:
        raise RuntimeError("existing shard phase-03 marker mismatch")
    if record["phase04_workshop_sha256"] != read04["workshop_sha256"]:
        raise RuntimeError("existing shard phase-04 marker mismatch")
    if record["phase05_sha256"] != read05["phase05_sha256"]:
        raise RuntimeError("existing shard phase-05 marker mismatch")
    expected_chunk_hash = manifest.chunk_hash(record)
    if expected_chunk_hash != str(record["chunk_sha256"]):
        raise RuntimeError("existing shard phase-07 chunk hash mismatch")
    record["_flow_summary"] = flow
    record["_static_workshop_signature"] = _static_workshop_signature(read04)
    record["_hydro_signature"] = _hydro_signature(read05)
    return record, read04, read05


def _build_shard(
    world: Any,
    all_cells: Sequence[Any],
    *,
    out_path: Path,
    global_indices: Sequence[int],
    ordinal: int,
    config: Mapping[str, Any],
    release_version: str,
    production_mass_error_kg: float,
) -> tuple[dict[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    reports = [
        intensity.propagate_cell(world, all_cells[int(index)], max_steps=int(config["intensity_steps"]))
        for index in global_indices
    ]
    flow = _flow_summary(reports, int(config["population_cells"]))
    spine = _write_global_spine_shard(
        out_path,
        reports=reports,
        global_indices=global_indices,
        flow_summary=flow,
        config=config,
        release_version=release_version,
        production_mass_error_kg=production_mass_error_kg,
    )

    lineages = _lineages_with_global_indices(
        world,
        reports,
        global_indices,
        world_seed=int(config["world_seed"]),
    )
    bio = v3_biography_netcdf.append_biography(
        out_path,
        lineages=lineages,
        world_seed=int(config["world_seed"]),
        phase01_spine_sha256=str(spine["spine_sha256"]),
    )
    chemistry = v3_source_metallurgy.materialize_metallurgy(world, lineages)
    metal = v3_metallurgy_netcdf.append_metallurgy(
        out_path,
        world=world,
        lineages=lineages,
        chemistry=chemistry,
        world_seed=int(config["world_seed"]),
        phase01_spine_sha256=str(spine["spine_sha256"]),
        phase02_biography_sha256=str(bio["biography_sha256"]),
    )
    layer04 = v3_workshop_ecology.materialize_workshop_layer(
        world,
        lineages,
        chemistry,
        world_seed=int(config["world_seed"]),
    )
    work = v3_workshop_netcdf.append_workshop_layer(
        out_path,
        layer=layer04,
        world_seed=int(config["world_seed"]),
        phase01_spine_sha256=str(spine["spine_sha256"]),
        phase02_biography_sha256=str(bio["biography_sha256"]),
        phase03_metallurgy_sha256=str(metal["metallurgy_sha256"]),
    )
    sparse = SparseReportSequence(int(config["population_cells"]), reports, global_indices)
    layer05 = phase05.materialize_phase05(
        world,
        sparse,
        lineages,
        world_seed=int(config["world_seed"]),
    )
    env = v3_phase05_netcdf.append_phase05(
        out_path,
        layer=layer05,
        world_seed=int(config["world_seed"]),
        phase01_spine_sha256=str(spine["spine_sha256"]),
        phase02_biography_sha256=str(bio["biography_sha256"]),
        phase03_metallurgy_sha256=str(metal["metallurgy_sha256"]),
        phase04_workshop_sha256=str(work["workshop_sha256"]),
    )

    tables04 = v3_workshop_ecology.flatten_workshop_layer(layer04)
    record: dict[str, Any] = {
        "world_build_id": manifest.world_build_id(config),
        "shard_name": out_path.name,
        "chunk_ordinal": int(ordinal),
        "global_cell_start": int(global_indices[0]),
        "global_cell_stop": int(global_indices[-1]) + 1,
        "cell_count": len(global_indices),
        "loss_strata": int(flow["loss_strata"]),
        "particles": len(lineages),
        "batches": int(bio["batches"]),
        "operations": len(tables04["operations"]),
        "external_exchange_tails": len(layer05.external_exchange),
        "deposition_assignments": len(layer05.deposition_assignments),
        "archaeology_rows": len(layer05.archaeology),
        "phase01_spine_sha256": str(spine["spine_sha256"]),
        "phase02_biography_sha256": str(bio["biography_sha256"]),
        "phase03_metallurgy_sha256": str(metal["metallurgy_sha256"]),
        "phase04_workshop_sha256": str(work["workshop_sha256"]),
        "phase05_sha256": str(env["phase05_sha256"]),
    }
    record["chunk_sha256"] = manifest.chunk_hash(record)
    _write_chunk_marker(out_path, record=record, flow_summary=flow)
    read04 = v3_workshop_netcdf.read_workshop_layer(out_path)
    read05 = v3_phase05_netcdf.read_phase05(out_path)
    record["_flow_summary"] = flow
    record["_static_workshop_signature"] = _static_workshop_signature(read04)
    record["_hydro_signature"] = _hydro_signature(read05)
    return record, read04, read05


def _merge_pool(aggregate: dict[str, dict[str, Any]], row: Mapping[str, Any]) -> None:
    pid = str(row["deposition_pool_id"])
    weight = float(row["represented_weight"])
    if pid not in aggregate:
        aggregate[pid] = {
            "deposition_pool_id": pid,
            "node_id": str(row["node_id"]),
            "date_bc": int(row["date_bc"]),
            "mode": str(row["mode"]),
            "member_count": int(row["member_count"]),
            "represented_weight": weight,
            "hydro_realization_id": str(row["hydro_realization_id"]),
            "_hydro_weighted_sum": weight * float(row["hydro_context_score"]),
        }
        return
    dst = aggregate[pid]
    for field in ("node_id", "date_bc", "mode", "hydro_realization_id"):
        if str(dst[field]) != str(row[field]):
            raise RuntimeError(f"global deposition pool identity collision for {pid}")
    dst["member_count"] += int(row["member_count"])
    dst["represented_weight"] += weight
    dst["_hydro_weighted_sum"] += weight * float(row["hydro_context_score"])


def _final_pools(aggregate: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for pid in sorted(aggregate):
        row = dict(aggregate[pid])
        weight = float(row["represented_weight"])
        hydro = float(row.pop("_hydro_weighted_sum")) / max(1e-30, weight)
        row["hydro_context_score"] = hydro
        out.append(row)
    return out


def _merge_tool_use(aggregate: dict[str, dict[str, Any]], row: Mapping[str, Any]) -> None:
    tid = str(row["tool_id"])
    if tid not in aggregate:
        aggregate[tid] = {
            "tool_id": tid,
            "localized_operation_count": 0,
            "represented_operation_weight": 0.0,
            "represented_mass_kg": 0.0,
        }
    dst = aggregate[tid]
    dst["localized_operation_count"] += int(row["localized_operation_count"])
    dst["represented_operation_weight"] += float(row["represented_operation_weight"])
    dst["represented_mass_kg"] += float(row["represented_mass_kg"])


def _aggregate_flow(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    totals = defaultdict(float)
    for record in records:
        flow = record["_flow_summary"]
        for key in (
            "produced", "circulation_seed", "transfer_flux", "return_flux",
            "recycle_flux", "loss_flux", "retire_flux", "residual_active",
        ):
            totals[key] += float(flow[key])
    conservation = totals["circulation_seed"] - (
        totals["return_flux"] + totals["loss_flux"] + totals["retire_flux"] + totals["residual_active"]
    )
    return {
        **{key: float(value) for key, value in totals.items()},
        "conservation_error": float(conservation),
        "relative_conservation_error": float(conservation / max(1.0, totals["circulation_seed"])),
    }


def build_canonical(
    hypothesis: Mapping[str, Any],
    *,
    out_dir: Path,
    world_seed: int = CANONICAL_WORLD_SEED,
    workshops: int = CANONICAL_WORKSHOPS,
    steps: int = CANONICAL_STEPS,
    nodes: int = CANONICAL_NODES,
    chunk_cells: int = DEFAULT_CHUNK_CELLS,
    max_cells: int | None = None,
    resume: bool = True,
) -> dict[str, Any]:
    if chunk_cells <= 0:
        raise ValueError("chunk_cells must be positive")
    release_version = release_invariants.install()
    world = archaeology.TemporalFieldArchaeologicalWorld(
        hypothesis,
        seed=int(world_seed),
        target_geography_nodes=int(nodes),
    )
    world.build(workshop_count=int(workshops))
    mass_error = float(release_invariants.production_mass_error(world))
    tolerance = build_v3_master._production_mass_tolerance_kg(world)
    if abs(mass_error) > tolerance:
        raise RuntimeError("phase-07 production mass invariant failed")

    all_cells = intensity.production_cells(world)
    population = len(all_cells)
    materialized = population if max_cells is None else min(population, max(0, int(max_cells)))
    if materialized <= 0:
        raise ValueError("phase-07 must materialize at least one production cell")
    config = _config(
        hypothesis,
        world_seed=world_seed,
        workshops=workshops,
        steps=steps,
        nodes=nodes,
        population_cells=population,
        materialized_cells=materialized,
        chunk_cells=chunk_cells,
    )
    build_id = manifest.world_build_id(config)

    out_dir = Path(out_dir)
    shard_dir = out_dir / "shards"
    shard_dir.mkdir(parents=True, exist_ok=True)
    shard_records: list[dict[str, Any]] = []
    pool_aggregate: dict[str, dict[str, Any]] = {}
    tool_aggregate: dict[str, dict[str, Any]] = {}
    workshop_signatures: set[str] = set()
    hydro_signatures: set[str] = set()

    ordinal = 0
    for start in range(0, materialized, int(chunk_cells)):
        stop = min(materialized, start + int(chunk_cells))
        indices = list(range(start, stop))
        name = f"atolia_v3_canonical_{start:06d}_{stop:06d}.nc"
        path = shard_dir / name
        print(f"phase07 shard {ordinal}: cells {start}:{stop}", file=sys.stderr, flush=True)
        if resume and path.exists():
            record, read04, read05 = _read_existing_shard(
                path,
                expected_world_build_id=build_id,
                ordinal=ordinal,
                start=start,
                stop=stop,
            )
        else:
            if path.exists():
                path.unlink()
            record, read04, read05 = _build_shard(
                world,
                all_cells,
                out_path=path,
                global_indices=indices,
                ordinal=ordinal,
                config=config,
                release_version=str(release_version),
                production_mass_error_kg=mass_error,
            )
        workshop_signatures.add(str(record["_static_workshop_signature"]))
        hydro_signatures.add(str(record["_hydro_signature"]))
        for row in read05["deposition_pools"]:
            _merge_pool(pool_aggregate, row)
        for row in read04["tool_use"]:
            _merge_tool_use(tool_aggregate, row)
        shard_records.append(record)
        ordinal += 1

    if len(workshop_signatures) != 1:
        raise RuntimeError("phase-07 workshop static truth differs across shards")
    if len(hydro_signatures) != 1:
        raise RuntimeError("phase-07 hydro realization differs across shards")

    pools = _final_pools(pool_aggregate)
    tool_use = [tool_aggregate[key] for key in sorted(tool_aggregate)]
    flow = _aggregate_flow(shard_records)
    public_shards = [{k: v for k, v in row.items() if not k.startswith("_")} for row in shard_records]
    totals = {
        "loss_strata": sum(int(row["loss_strata"]) for row in shard_records),
        "particles": sum(int(row["particles"]) for row in shard_records),
        "batches": sum(int(row["batches"]) for row in shard_records),
        "operations": sum(int(row["operations"]) for row in shard_records),
        "external_exchange_tails": sum(int(row["external_exchange_tails"]) for row in shard_records),
        "deposition_assignments": sum(int(row["deposition_assignments"]) for row in shard_records),
        "archaeology_rows": sum(int(row["archaeology_rows"]) for row in shard_records),
        "global_shared_deposition_pools": sum(int(row["member_count"]) > 1 for row in pools),
        "static_workshop_signature": next(iter(workshop_signatures)),
        "hydro_realization_signature": next(iter(hydro_signatures)),
        **flow,
    }
    manifest_path = out_dir / "manifest.nc"
    summary = manifest.write_manifest(
        manifest_path,
        config=config,
        shards=public_shards,
        deposition_pools=pools,
        tool_use=tool_use,
        totals=totals,
    )
    read = manifest.read_manifest(manifest_path)
    if read["phase07_manifest_sha256"] != summary["phase07_manifest_sha256"]:
        raise RuntimeError("phase-07 manifest roundtrip hash mismatch")
    if read["world_build_id"] != build_id:
        raise RuntimeError("phase-07 manifest world identity mismatch")
    return {
        "latest_phase": manifest.V3_PHASE07_PHASE,
        "canonical_full": summary,
        "roundtrip": {
            "manifest_hash_equal": True,
            "world_build_id_equal": True,
            "global_cell_coverage_closed": sum(int(row["cell_count"]) for row in public_shards) == materialized,
            "workshop_static_equal_across_shards": True,
            "hydro_realization_equal_across_shards": True,
            "global_deposition_pools_merged": True,
            "global_tool_use_merged": True,
        },
        "flow_summary": flow,
        "release_invariants_version": str(release_version),
        "production_mass_error_kg": mass_error,
        "runner": {
            "population_cells": population,
            "materialized_cells": materialized,
            "chunk_cells": int(chunk_cells),
            "shards": len(public_shards),
            "resume": bool(resume),
            "platform": sys.platform,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Build Atolia v3 phase-07 canonical full sharded master")
    ap.add_argument("--hypothesis", type=Path, default=Path("hypotheses/atolia_atesis_1800_1000_v0.json"))
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--world-seed", type=int, default=CANONICAL_WORLD_SEED)
    ap.add_argument("--workshops", type=int, default=CANONICAL_WORKSHOPS)
    ap.add_argument("--steps", type=int, default=CANONICAL_STEPS)
    ap.add_argument("--nodes", type=int, default=CANONICAL_NODES)
    ap.add_argument("--chunk-cells", type=int, default=DEFAULT_CHUNK_CELLS)
    ap.add_argument("--max-cells", type=int, default=None, help="verification prefix only; omit for full population")
    ap.add_argument("--no-resume", action="store_true")
    args = ap.parse_args()

    if sys.platform == "emscripten" and args.max_cells is None:
        raise RuntimeError("canonical full phase-07 build is native-only; use --max-cells for a WASM verification prefix")
    hypothesis_path = args.hypothesis if args.hypothesis.is_absolute() else PROJECT_ROOT / args.hypothesis
    out_dir = args.out_dir if args.out_dir.is_absolute() else PROJECT_ROOT / args.out_dir
    hypothesis = json.loads(hypothesis_path.read_text(encoding="utf-8"))
    result = build_canonical(
        hypothesis,
        out_dir=out_dir,
        world_seed=args.world_seed,
        workshops=args.workshops,
        steps=args.steps,
        nodes=args.nodes,
        chunk_cells=args.chunk_cells,
        max_cells=args.max_cells,
        resume=not args.no_resume,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    host_emit = globals().get("emit")
    if callable(host_emit):
        host_emit(result)


if __name__ == "__main__":
    main()
