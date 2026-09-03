from __future__ import annotations

"""Exact lazy crystallizer from the small Atolia v3 R17 runtime.

The R17 NetCDF stores global archaeological mass plus exact cell/profile
checkpoints. This module rebuilds only cells actually visited by the player's
300 weighted draws. Every selected cell must reproduce its canonical checkpoint
before any object can enter the private player NetCDF.
"""

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np
from netCDF4 import Dataset

import archaeology_temporal_world as archaeology
import build_v3_master
import intensity_circulation as intensity
import release_candidate_invariants as release_invariants
import v3_hydro_exchange_deposition as phase05
import v3_metal_biography as biography
import v3_phase07_canonical as canonical
import v3_phase07_manifest as phase07_manifest
import v3_phase08_compact_fragment as compact
import v3_phase08_runtime_fragment as phase08
import v3_runtime_v3 as runtime_v3
import v3_source_metallurgy as metallurgy
import v3_workshop_ecology as workshop


Progress = Callable[[int, str], None]


def _progress(callback: Progress | None, percent: int, stage: str) -> None:
    if callback is not None:
        callback(max(0, min(100, int(percent))), str(stage))


def _decode_token_rows(matrix: Any) -> list[str]:
    values = np.asarray(matrix, dtype=np.uint8)
    out: list[str] = []
    for row in values:
        raw = bytes(int(x) for x in row if int(x) != 0)
        out.append(raw.decode("ascii"))
    return out


def _float_same(left: float, right: float) -> bool:
    return float(left).hex() == float(right).hex()


class PlayerStream:
    """Small counter-mode deterministic draw stream independent of NumPy RNG."""

    def __init__(self, player_key: str) -> None:
        clean = str(player_key).strip()
        if not clean:
            raise ValueError("player_key must not be empty")
        self.key = hashlib.sha256(
            (runtime_v3.GENERATOR_VERSION + "|" + clean).encode("utf-8")
        ).digest()
        self.counter = 0

    def uniform(self, purpose: str) -> float:
        counter = self.counter
        self.counter += 1
        digest = hashlib.sha256(
            self.key + counter.to_bytes(8, "big") + str(purpose).encode("utf-8")
        ).digest()
        value = int.from_bytes(digest[:8], "big")
        return (value + 0.5) / 2**64


def _weighted_index(weights: Sequence[float], draw: float) -> int:
    total = 0.0
    cdf: list[float] = []
    for raw in weights:
        weight = float(raw)
        if not math.isfinite(weight) or weight < 0.0:
            raise ValueError("sampling weights must be finite and nonnegative")
        total += weight
        cdf.append(total)
    if total <= 0.0:
        raise ValueError("sampling weights have no positive mass")
    target = min(math.nextafter(total, 0.0), max(0.0, float(draw)) * total)
    lo, hi = 0, len(cdf)
    while lo < hi:
        mid = (lo + hi) // 2
        if target < cdf[mid]:
            hi = mid
        else:
            lo = mid + 1
    return min(lo, len(cdf) - 1)


@dataclass(frozen=True)
class PreparedCandidate:
    global_cell_index: int
    cell_loss_index: int
    stratum: intensity.LossStratum
    lineage: biography.MetalLineage
    assignment: phase05.DepositionAssignment
    observation: phase05.ArchaeologyObservation

    @property
    def recorded_weight(self) -> float:
        return float(self.observation.recorded_weight)


@dataclass(frozen=True)
class SelectedObject:
    selection_index: int
    candidate: PreparedCandidate
    measurement_seed: int


@dataclass
class PreparedCell:
    global_cell_index: int
    report: intensity.CellFlowReport
    candidates: list[PreparedCandidate]
    recorded_weight: float


@dataclass
class CrystallizedWorld:
    runtime_path: Path
    runtime_fingerprint: str
    world_build_id: str
    player_key_hash: str
    world: Any
    cells: list[intensity.ProductionCell]
    selected: list[SelectedObject]
    chemistry: list[metallurgy.MetallurgyLineage]
    workshop_layer: workshop.WorkshopLayer
    external_exchange: tuple[phase05.ExternalExchangeRecord, ...]
    canonical_hydro_context: dict[str, float]
    canonical_hydro_realization_id: str


class RuntimeV3:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.ds = Dataset(self.path, "r")
        try:
            if str(getattr(self.ds, "schema", "")) != runtime_v3.RUNTIME_SCHEMA:
                raise ValueError("not an Atolia v3 R17 runtime")
            self.world_build_id = str(self.ds.world_build_id)
            self.world_seed = int(self.ds.world_seed)
            self.workshop_count = int(self.ds.workshop_count)
            self.intensity_steps = int(self.ds.intensity_steps)
            self.target_nodes = int(self.ds.target_geography_nodes)
            self.population_cells = int(self.ds.population_cells)
            self.target_objects = int(self.ds.target_player_objects)
            self.runtime_fingerprint = str(self.ds.runtime_fingerprint)
            self.canonical_hydro_id = str(self.ds.canonical_hydro_realization_id)
            self.minority_hydro_id = str(self.ds.minority_hydro_realization_id)
            self.hypothesis_sha256 = str(self.ds.hypothesis_sha256)
            self.cell_recorded = np.asarray(self.ds.variables["cell_recorded_weight"][:], dtype=np.float64)
            self.cell_loss = np.asarray(self.ds.variables["cell_loss_intensity"][:], dtype=np.float64)
            self.cell_lineages = np.asarray(self.ds.variables["cell_lineage_count"][:], dtype=np.int64)
            self.cell_profiles = np.asarray(self.ds.variables["cell_profile_count"][:], dtype=np.int64)
            self.cell_identity_hash = np.asarray(self.ds.variables["cell_identity_sha256"][:], dtype=np.uint8)
            self.cell_profile_hash = np.asarray(self.ds.variables["cell_profile_sha256"][:], dtype=np.uint8)
            raw_hypothesis = bytes(np.asarray(self.ds.variables["hypothesis_bytes"][:], dtype=np.uint8).tolist())
            self.hypothesis = json.loads(raw_hypothesis.decode("utf-8"))
            self.override_tokens = _decode_token_rows(self.ds.variables["hydro_override_node_token"][:])
            self.override_values = np.asarray(self.ds.variables["hydro_override_context"][:], dtype=np.float64)
        except Exception:
            self.ds.close()
            raise
        if len(self.cell_recorded) != self.population_cells:
            self.close()
            raise ValueError("R17 cell dimension differs from population_cells")
        if self.target_objects != runtime_v3.TARGET_OBJECTS:
            self.close()
            raise ValueError("R17 target object count is not 300")

    def close(self) -> None:
        if getattr(self, "ds", None) is not None:
            self.ds.close()
            self.ds = None


def _build_world(store: RuntimeV3) -> tuple[Any, list[intensity.ProductionCell]]:
    release_invariants.install()
    if build_v3_master.canonical_hypothesis_sha256(store.hypothesis) != store.hypothesis_sha256:
        raise RuntimeError("R17 embedded hypothesis hash mismatch")
    config = canonical._config(
        store.hypothesis,
        world_seed=store.world_seed,
        workshops=store.workshop_count,
        steps=store.intensity_steps,
        nodes=store.target_nodes,
        population_cells=store.population_cells,
        materialized_cells=store.population_cells,
        chunk_cells=64,
    )
    if phase07_manifest.world_build_id(config) != store.world_build_id:
        raise RuntimeError("R17 canonical configuration does not reproduce world_build_id")
    world = archaeology.TemporalFieldArchaeologicalWorld(
        store.hypothesis,
        seed=store.world_seed,
        target_geography_nodes=store.target_nodes,
    )
    world.build(workshop_count=store.workshop_count)
    cells = intensity.production_cells(world)
    if len(cells) != store.population_cells:
        raise RuntimeError(
            f"R17 production-cell population changed: {len(cells)} != {store.population_cells}"
        )
    return world, cells


def _canonical_hydro_context(store: RuntimeV3, world: Any) -> dict[str, float]:
    _status, _evidence, ensemble = phase05.build_hydro_ensemble(world)
    realization = phase05.realize_hydro(ensemble, world_seed=store.world_seed)
    ids = {row.realization_id for row in realization}
    if len(ids) != 1:
        raise RuntimeError("fresh hydro rebuild did not produce one realization id")
    fresh_id = next(iter(ids))
    if fresh_id not in {store.canonical_hydro_id, store.minority_hydro_id}:
        raise RuntimeError(f"fresh hydro rebuild produced unrecognized topology {fresh_id}")
    context = phase05._hydro_context(realization)
    token_to_node = {
        phase08.anonymous_token(store.world_build_id, "node", node_id): str(node_id)
        for node_id in world.nodes
    }
    if len(store.override_tokens) != len(store.override_values):
        raise RuntimeError("R17 hydro override table is malformed")
    for token, value in zip(store.override_tokens, store.override_values):
        node_id = token_to_node.get(token)
        if node_id is None:
            raise RuntimeError(f"R17 hydro override token does not resolve: {token}")
        context[node_id] = float(value)
    return context


def _cell_identity(store: RuntimeV3, index: int, cell: intensity.ProductionCell) -> bytes:
    return runtime_v3.cell_identity_hash(
        world_build_id=store.world_build_id,
        global_cell_index=index,
        bundle_id=cell.bundle_id,
        bundle_family=cell.bundle_family,
        object_class=cell.object_class,
        date_bc=cell.date_bc,
        origin=cell.origin,
        destination=cell.destination,
        production_intensity=cell.production_intensity,
        circulation_seed_intensity=cell.circulation_seed_intensity,
        recycle_mean=cell.recycle_mean,
        source_mix=cell.source_mix,
    )


def _prepare_cell(
    store: RuntimeV3,
    world: Any,
    cells: Sequence[intensity.ProductionCell],
    canonical_context: Mapping[str, float],
    global_index: int,
) -> PreparedCell:
    cell = cells[global_index]
    expected_identity = bytes(np.asarray(store.cell_identity_hash[global_index], dtype=np.uint8).tolist())
    if _cell_identity(store, global_index, cell) != expected_identity:
        raise RuntimeError(f"R17 production cell {global_index} failed exact identity checkpoint")

    report = intensity.propagate_cell(world, cell, max_steps=store.intensity_steps)
    profiles: dict[str, dict[str, Any]] = {}
    candidates: list[PreparedCandidate] = []

    for loss_index, stratum in enumerate(report.loss_strata):
        lineage = biography.materialize_loss_lineage(
            world,
            stratum,
            world_seed=store.world_seed,
            production_cell_index=global_index,
            cell_loss_index=loss_index,
        )
        weights = phase05._normalize_weights(stratum.deposition_mode_weights)
        mode, mode_probability = phase05._weighted_choice(
            weights,
            phase05._uniform01(store.world_seed, lineage.particle_id, "deposition-mode"),
        )
        pool_id = phase05._stable_id("dep", lineage.loss_node_id, lineage.date_bc, mode)
        assignment = phase05.DepositionAssignment(
            particle_id=lineage.particle_id,
            loss_site_id=lineage.loss_site_id,
            deposition_pool_id=pool_id,
            hydro_realization_id=store.canonical_hydro_id,
            node_id=lineage.loss_node_id,
            date_bc=lineage.date_bc,
            mode=mode,
            mode_probability=float(mode_probability),
            mode_weights=weights,
            represented_weight=float(lineage.represented_weight),
            expected_field_crossings=float(stratum.expected_field_crossings),
            expected_physical_crossings=float(stratum.expected_physical_crossings),
            hydro_context_score=float(canonical_context.get(lineage.loss_node_id, 0.0)),
        )
        observation = phase05.materialize_archaeology([lineage], [assignment])[0]
        candidates.append(PreparedCandidate(
            global_cell_index=global_index,
            cell_loss_index=loss_index,
            stratum=stratum,
            lineage=lineage,
            assignment=assignment,
            observation=observation,
        ))

        node_token = phase08.anonymous_token(store.world_build_id, "node", stratum.node_id)
        acc = profiles.get(node_token)
        if acc is None:
            acc = {
                "node_token": node_token,
                "lineage_count": 0,
                "loss_intensity": 0.0,
                "recorded_weight": 0.0,
                "step_min": 2**31 - 1,
                "step_max": -1,
                "moments": compact.WeightedMoments(),
            }
            profiles[node_token] = acc
        acc["lineage_count"] += 1
        acc["loss_intensity"] += float(stratum.loss_intensity)
        acc["recorded_weight"] += float(observation.recorded_weight)
        acc["step_min"] = min(int(acc["step_min"]), int(stratum.step))
        acc["step_max"] = max(int(acc["step_max"]), int(stratum.step))
        acc["moments"].add(
            float(stratum.loss_intensity),
            **{name: float(getattr(stratum, name)) for name in runtime_v3.PROFILE_PHASE01_FIELDS},
        )

    profile_rows: list[dict[str, Any]] = []
    for token in sorted(profiles):
        acc = profiles[token]
        row: dict[str, Any] = {
            "node_token": token,
            "lineage_count": int(acc["lineage_count"]),
            "loss_intensity": float(acc["loss_intensity"]),
            "recorded_weight": float(acc["recorded_weight"]),
            "step_min": int(acc["step_min"]),
            "step_max": int(acc["step_max"]),
        }
        moments = acc["moments"]
        for name in runtime_v3.PROFILE_PHASE01_FIELDS:
            mean, variance = moments.pair(name)
            row[f"{name}_mean"] = float(mean)
            row[f"{name}_variance"] = float(variance)
        profile_rows.append(row)

    recorded_total = math.fsum(float(row["recorded_weight"]) for row in profile_rows)
    loss_total = math.fsum(float(row["loss_intensity"]) for row in profile_rows)
    if not _float_same(recorded_total, float(store.cell_recorded[global_index])):
        raise RuntimeError(
            f"R17 cell {global_index} recorded mass drifted: "
            f"{recorded_total.hex()} != {float(store.cell_recorded[global_index]).hex()}"
        )
    if not _float_same(loss_total, float(store.cell_loss[global_index])):
        raise RuntimeError(f"R17 cell {global_index} loss mass failed exact checkpoint")
    if len(candidates) != int(store.cell_lineages[global_index]):
        raise RuntimeError(f"R17 cell {global_index} lineage count failed checkpoint")
    if len(profile_rows) != int(store.cell_profiles[global_index]):
        raise RuntimeError(f"R17 cell {global_index} profile count failed checkpoint")
    expected_profile_hash = bytes(np.asarray(store.cell_profile_hash[global_index], dtype=np.uint8).tolist())
    if runtime_v3.profile_checkpoint_hash(profile_rows) != expected_profile_hash:
        raise RuntimeError(f"R17 cell {global_index} profile field failed SHA-256 checkpoint")
    if not candidates or recorded_total <= 0.0:
        raise RuntimeError(f"R17 cell {global_index} has no positive candidate mass")
    return PreparedCell(global_index, report, candidates, recorded_total)


class _SparseReports(Sequence[Any]):
    def __init__(self, length: int, prepared: Mapping[int, PreparedCell]) -> None:
        self.length = int(length)
        self.prepared = dict(prepared)

    def __len__(self) -> int:
        return self.length

    def __getitem__(self, index: int) -> Any:
        if index < 0:
            index += self.length
        if index < 0 or index >= self.length:
            raise IndexError(index)
        found = self.prepared.get(index)
        if found is not None:
            return found.report
        return intensity.CellFlowReport(
            production_cell=intensity.ProductionCell(
                bundle_id="", bundle_family="", object_class="scrap", date_bc=0,
                origin="", destination="", production_intensity=0.0,
                circulation_seed_intensity=0.0, source_mix={"none": 1.0}, recycle_mean=0.0,
            )
        )


def _measurement_seed(player_key: str, particle_id: str) -> int:
    digest = hashlib.sha256(
        ("dr-corrosion-measurement-v3|" + player_key + "|" + particle_id).encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], "big")


def crystallize(
    player_key: str,
    *,
    runtime_path: Path,
    target_objects: int = runtime_v3.TARGET_OBJECTS,
    progress_callback: Progress | None = None,
) -> CrystallizedWorld:
    store = RuntimeV3(Path(runtime_path))
    try:
        if int(target_objects) != store.target_objects:
            raise ValueError(f"R17 requires exactly {store.target_objects} player objects")
        _progress(progress_callback, 2, "OPENING R17")
        world, cells = _build_world(store)
        _progress(progress_callback, 12, "REBUILDING RIVER MAP")
        canonical_context = _canonical_hydro_context(store, world)
        _progress(progress_callback, 18, "CANONICAL HYDRO READY")

        stream = PlayerStream(player_key)
        cell_weights = [float(x) for x in store.cell_recorded]
        prepared: dict[int, PreparedCell] = {}
        selected: list[SelectedObject] = []
        selected_particles: set[str] = set()
        attempts = 0
        max_attempts = max(20_000, target_objects * 200)

        while len(selected) < target_objects:
            attempts += 1
            if attempts > max_attempts:
                raise RuntimeError("could not crystallize 300 unique objects within deterministic safety bound")
            cell_index = _weighted_index(cell_weights, stream.uniform("cell"))
            cell_state = prepared.get(cell_index)
            if cell_state is None:
                cell_state = _prepare_cell(store, world, cells, canonical_context, cell_index)
                prepared[cell_index] = cell_state
            candidate_index = _weighted_index(
                [row.recorded_weight for row in cell_state.candidates],
                stream.uniform("lineage"),
            )
            candidate = cell_state.candidates[candidate_index]
            pid = candidate.lineage.particle_id
            if pid in selected_particles:
                continue
            selected_particles.add(pid)
            selected.append(SelectedObject(
                selection_index=len(selected),
                candidate=candidate,
                measurement_seed=_measurement_seed(player_key, pid),
            ))
            if len(selected) == 1 or len(selected) % 10 == 0:
                pct = 18 + round(52 * len(selected) / target_objects)
                _progress(progress_callback, pct, f"CRYSTALLIZING {len(selected)}/{target_objects}")

        lineages = [row.candidate.lineage for row in selected]
        _progress(progress_callback, 73, "MATERIALIZING METALLURGY")
        chemistry = metallurgy.materialize_metallurgy(world, lineages)
        _progress(progress_callback, 80, "MATERIALIZING WORKSHOPS")
        workshop_layer = workshop.materialize_workshop_layer(
            world,
            lineages,
            chemistry,
            world_seed=store.world_seed,
        )
        _progress(progress_callback, 88, "MATERIALIZING EXCHANGE TAILS")
        sparse_reports = _SparseReports(store.population_cells, prepared)
        external = phase05.materialize_external_exchange(
            sparse_reports,
            lineages,
            canonical_context,
            world_seed=store.world_seed,
        )
        _progress(progress_callback, 92, "300 OBJECTS MATERIALIZED")
        return CrystallizedWorld(
            runtime_path=Path(runtime_path),
            runtime_fingerprint=store.runtime_fingerprint,
            world_build_id=store.world_build_id,
            player_key_hash=hashlib.sha256(player_key.strip().encode("utf-8")).hexdigest(),
            world=world,
            cells=list(cells),
            selected=selected,
            chemistry=chemistry,
            workshop_layer=workshop_layer,
            external_exchange=external,
            canonical_hydro_context=canonical_context,
            canonical_hydro_realization_id=store.canonical_hydro_id,
        )
    finally:
        store.close()
