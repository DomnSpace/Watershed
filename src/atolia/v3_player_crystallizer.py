from __future__ import annotations

"""Keyed 300-object crystallizer reading the frozen R17 field directly.

R17 is authoritative.  Player startup does not rebuild the world or regenerate
37,100 production cells.  Each player slot independently selects a profile from
the stored archaeological field, propagates only that profile's production
cell, verifies the exact Phase-08 checkpoint, and materializes one physical
lineage through the existing Phase-02..05 machinery.
"""

from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np
from netCDF4 import Dataset

import intensity_circulation as intensity
import v3_frozen_world
import v3_hydro_exchange_deposition as phase05
import v3_metal_biography as biography
import v3_phase08_compact_fragment as compact
import v3_phase08_runtime_fragment as phase08
import v3_runtime_v3 as runtime_v3
import v3_source_metallurgy as metallurgy
import v3_workshop_ecology as workshop


Progress = Callable[[int, str], None]


def _progress(callback: Progress | None, percent: int, stage: str) -> None:
    if callback is not None:
        callback(max(0, min(100, int(percent))), str(stage))


def _strings(var: Any) -> list[str]:
    values = var[:]
    return [x.decode("utf-8") if isinstance(x, bytes) else str(x) for x in values]


def _float_same(left: float, right: float) -> bool:
    return float(left).hex() == float(right).hex()


def _slot_uniform(
    player_key: str,
    runtime_fingerprint: str,
    slot: int,
    attempt: int,
    purpose: str,
    ordinal: int = 0,
) -> float:
    """Independent PRF draw; retries in one slot cannot perturb later slots."""
    raw = (
        runtime_v3.GENERATOR_VERSION
        + "\0" + runtime_fingerprint
        + "\0" + str(player_key).strip()
        + "\0object\0" + str(int(slot))
        + "\0attempt\0" + str(int(attempt))
        + "\0" + str(purpose)
        + "\0" + str(int(ordinal))
    ).encode("utf-8")
    value = int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")
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
    return int(np.searchsorted(np.asarray(cdf, dtype=np.float64), target, side="right"))


def _ordered_cdf(weights: Sequence[float]) -> np.ndarray:
    """Sequential binary64 CDF, deliberately independent of vector reduction order."""
    out = np.empty(len(weights), dtype=np.float64)
    running = 0.0
    for i, raw in enumerate(weights):
        weight = float(raw)
        if not math.isfinite(weight) or weight < 0.0:
            raise ValueError("R17 profile weights must be finite and nonnegative")
        running += weight
        out[i] = running
    if not len(out) or running <= 0.0:
        raise ValueError("R17 contains no positive archaeological profile mass")
    return out


def _cdf_index(cdf: np.ndarray, draw: float) -> int:
    total = float(cdf[-1])
    target = min(math.nextafter(total, 0.0), max(0.0, float(draw)) * total)
    return min(int(np.searchsorted(cdf, target, side="right")), len(cdf) - 1)


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
    runtime_profile_index: int
    candidate: PreparedCandidate
    measurement_seed: int


@dataclass
class PreparedProfile:
    profile_index: int
    global_cell_index: int
    node_id: str
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
                raise ValueError("not an Atolia v3 frozen-field R17 runtime")
            if str(getattr(self.ds, "world_table_schema", "")) != v3_frozen_world.WORLD_TABLE_SCHEMA:
                raise ValueError("R17 lacks the frozen world tables")
            self.world_build_id = str(self.ds.world_build_id)
            self.world_seed = int(self.ds.world_seed)
            self.intensity_steps = int(self.ds.intensity_steps)
            self.population_cells = int(self.ds.population_cells)
            self.target_objects = int(self.ds.target_player_objects)
            self.runtime_fingerprint = str(self.ds.runtime_fingerprint)
            self.canonical_hydro_id = str(self.ds.canonical_hydro_realization_id)
            self.world = v3_frozen_world.FrozenWorld(self.ds)
            self.cells = v3_frozen_world.load_production_cells(self.ds)

            gp = self.ds.groups["profiles"]
            self.profile_count = int(gp.profile_count)
            self.profile_cell = np.asarray(gp.variables["cell_index"][:], dtype=np.int64)
            self.profile_node = np.asarray(gp.variables["node_index"][:], dtype=np.int64)
            self.profile_lineages = np.asarray(gp.variables["lineage_count"][:], dtype=np.int64)
            self.profile_loss = np.asarray(gp.variables["loss_intensity"][:], dtype=np.float64)
            self.profile_represented = np.asarray(gp.variables["represented_weight"][:], dtype=np.float64)
            self.profile_recorded = np.asarray(gp.variables["recorded_weight"][:], dtype=np.float64)
            self.profile_step_min = np.asarray(gp.variables["step_min"][:], dtype=np.int64)
            self.profile_step_max = np.asarray(gp.variables["step_max"][:], dtype=np.int64)
            self.profile_hash = np.asarray(gp.variables["checkpoint_sha256"][:], dtype=np.uint8)
            self.profile_cdf = _ordered_cdf(self.profile_recorded)

            gi = self.ds.groups["integrity"]
            self.cell_identity_hash = np.asarray(gi.variables["cell_identity_sha256"][:], dtype=np.uint8)

            gh = self.ds.groups["canonical_hydro"]
            hydro_nodes = _strings(gh.variables["node_id"])
            hydro_values = np.asarray(gh.variables["context"][:], dtype=np.float64)
            self.canonical_hydro_context = {node: float(value) for node, value in zip(hydro_nodes, hydro_values)}
            self.node_ids = list(self.world.nodes)
        except Exception:
            self.ds.close()
            raise
        if len(self.cells) != self.population_cells:
            self.close(); raise ValueError("R17 frozen production-cell count mismatch")
        if len(self.profile_cell) != self.profile_count or len(self.profile_hash) != self.profile_count:
            self.close(); raise ValueError("R17 profile field is incomplete")
        if self.target_objects != runtime_v3.TARGET_OBJECTS:
            self.close(); raise ValueError("R17 target object count is not 300")

    def close(self) -> None:
        if getattr(self, "ds", None) is not None:
            self.ds.close(); self.ds = None

    def expected_profile_row(self, profile_index: int) -> dict[str, Any]:
        gp = self.ds.groups["profiles"]
        p = int(profile_index)
        node_id = self.node_ids[int(self.profile_node[p])]
        row: dict[str, Any] = {
            "node_token": phase08.anonymous_token(self.world_build_id, "node", node_id),
            "lineage_count": int(self.profile_lineages[p]),
            "loss_intensity": float(self.profile_loss[p]),
            "recorded_weight": float(self.profile_recorded[p]),
            "step_min": int(self.profile_step_min[p]),
            "step_max": int(self.profile_step_max[p]),
        }
        for field in runtime_v3.PROFILE_PHASE01_FIELDS:
            row[f"{field}_mean"] = float(gp.variables[f"mean_{field}"][p])
            row[f"{field}_variance"] = float(gp.variables[f"variance_{field}"][p])
        return row


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


def _assignment_for(
    store: RuntimeV3,
    lineage: biography.MetalLineage,
    stratum: intensity.LossStratum,
) -> tuple[phase05.DepositionAssignment, phase05.ArchaeologyObservation]:
    weights = phase05._normalize_weights(stratum.deposition_mode_weights)
    mode, mode_probability = phase05._weighted_choice(
        weights, phase05._uniform01(store.world_seed, lineage.particle_id, "deposition-mode")
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
        hydro_context_score=float(store.canonical_hydro_context.get(lineage.loss_node_id, 0.0)),
    )
    return assignment, phase05.materialize_archaeology([lineage], [assignment])[0]


def _prepare_profile(
    store: RuntimeV3,
    profile_index: int,
    report_cache: dict[int, intensity.CellFlowReport],
) -> PreparedProfile:
    p = int(profile_index)
    global_cell = int(store.profile_cell[p])
    node_id = store.node_ids[int(store.profile_node[p])]
    cell = store.cells[global_cell]
    expected_cell = bytes(np.asarray(store.cell_identity_hash[global_cell], dtype=np.uint8).tolist())
    if _cell_identity(store, global_cell, cell) != expected_cell:
        raise RuntimeError(f"R17 frozen production cell {global_cell} failed identity checkpoint")

    report = report_cache.get(global_cell)
    if report is None:
        report = intensity.propagate_cell(store.world, cell, max_steps=store.intensity_steps)
        report_cache[global_cell] = report

    candidates: list[PreparedCandidate] = []
    moments = compact.WeightedMoments()
    loss_total = 0.0
    represented_total = 0.0
    recorded_total = 0.0
    step_min = 2**31 - 1
    step_max = -1
    for loss_index, stratum in enumerate(report.loss_strata):
        if str(stratum.node_id) != node_id:
            continue
        lineage = biography.materialize_loss_lineage(
            store.world,
            stratum,
            world_seed=store.world_seed,
            production_cell_index=global_cell,
            cell_loss_index=loss_index,
        )
        assignment, observation = _assignment_for(store, lineage, stratum)
        candidates.append(PreparedCandidate(global_cell, loss_index, stratum, lineage, assignment, observation))
        loss_total += float(stratum.loss_intensity)
        represented_total += float(lineage.represented_weight)
        recorded_total += float(observation.recorded_weight)
        step_min = min(step_min, int(stratum.step)); step_max = max(step_max, int(stratum.step))
        moments.add(
            float(stratum.loss_intensity),
            **{field: float(getattr(stratum, field)) for field in runtime_v3.PROFILE_PHASE01_FIELDS},
        )
    if not candidates:
        raise RuntimeError(f"R17 selected profile {p} has no regenerated loss strata")

    row: dict[str, Any] = {
        "node_token": phase08.anonymous_token(store.world_build_id, "node", node_id),
        "lineage_count": len(candidates),
        "loss_intensity": float(loss_total),
        "recorded_weight": float(recorded_total),
        "step_min": int(step_min),
        "step_max": int(step_max),
    }
    for field in runtime_v3.PROFILE_PHASE01_FIELDS:
        mean, variance = moments.pair(field)
        row[f"{field}_mean"] = float(mean); row[f"{field}_variance"] = float(variance)

    expected = store.expected_profile_row(p)
    for key in ("lineage_count", "step_min", "step_max"):
        if int(row[key]) != int(expected[key]):
            raise RuntimeError(f"R17 profile {p} {key} failed exact checkpoint")
    for key in ("loss_intensity", "recorded_weight"):
        if not _float_same(float(row[key]), float(expected[key])):
            raise RuntimeError(
                f"R17 profile {p} {key} drifted: {float(row[key]).hex()} != {float(expected[key]).hex()}"
            )
    if not _float_same(represented_total, float(store.profile_represented[p])):
        raise RuntimeError(f"R17 profile {p} represented weight failed exact checkpoint")
    expected_hash = bytes(np.asarray(store.profile_hash[p], dtype=np.uint8).tolist())
    if runtime_v3.profile_checkpoint_hash([row]) != expected_hash:
        raise RuntimeError(f"R17 profile {p} Phase-01 field hash failed")
    if recorded_total <= 0.0:
        raise RuntimeError(f"R17 profile {p} has no positive archaeological mass")
    return PreparedProfile(p, global_cell, node_id, candidates, recorded_total)


class _SparseReports(Sequence[Any]):
    def __init__(self, length: int, reports: Mapping[int, intensity.CellFlowReport]) -> None:
        self.length = int(length); self.reports = dict(reports)

    def __len__(self) -> int: return self.length

    def __getitem__(self, index: int) -> Any:
        i = int(index)
        if i < 0: i += self.length
        if i < 0 or i >= self.length: raise IndexError(i)
        found = self.reports.get(i)
        if found is not None: return found
        return intensity.CellFlowReport(intensity.ProductionCell(
            bundle_id="", bundle_family="", object_class="scrap", date_bc=0,
            origin="", destination="", production_intensity=0.0,
            circulation_seed_intensity=0.0, source_mix={"none": 1.0}, recycle_mean=0.0,
        ))


def _measurement_seed(player_key: str, runtime_fingerprint: str, slot: int, particle_id: str) -> int:
    raw = (
        "dr-corrosion-measurement-v4\0" + runtime_fingerprint + "\0" + player_key
        + "\0" + str(int(slot)) + "\0" + particle_id
    ).encode("utf-8")
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")


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
        _progress(progress_callback, 10, "FROZEN RIVER FIELD READY")
        report_cache: dict[int, intensity.CellFlowReport] = {}
        profile_cache: dict[int, PreparedProfile] = {}
        selected: list[SelectedObject] = []
        selected_particles: set[str] = set()

        for slot in range(target_objects):
            accepted = False
            for attempt in range(10000):
                profile_index = _cdf_index(
                    store.profile_cdf,
                    _slot_uniform(player_key, store.runtime_fingerprint, slot, attempt, "profile"),
                )
                prepared = profile_cache.get(profile_index)
                if prepared is None:
                    prepared = _prepare_profile(store, profile_index, report_cache)
                    profile_cache[profile_index] = prepared
                candidate_index = _weighted_index(
                    [row.recorded_weight for row in prepared.candidates],
                    _slot_uniform(player_key, store.runtime_fingerprint, slot, attempt, "lineage"),
                )
                candidate = prepared.candidates[candidate_index]
                particle_id = candidate.lineage.particle_id
                if particle_id in selected_particles:
                    continue
                selected_particles.add(particle_id)
                selected.append(SelectedObject(
                    selection_index=slot,
                    runtime_profile_index=profile_index,
                    candidate=candidate,
                    measurement_seed=_measurement_seed(player_key, store.runtime_fingerprint, slot, particle_id),
                ))
                accepted = True
                break
            if not accepted:
                raise RuntimeError(f"could not crystallize unique object for slot {slot}")
            if slot == 0 or (slot + 1) % 10 == 0:
                _progress(progress_callback, 10 + round(60 * (slot + 1) / target_objects), f"CRYSTALLIZING {slot + 1}/{target_objects}")

        lineages = [row.candidate.lineage for row in selected]
        _progress(progress_callback, 73, "MATERIALIZING METALLURGY")
        chemistry = metallurgy.materialize_metallurgy(store.world, lineages)
        _progress(progress_callback, 80, "MATERIALIZING WORKSHOPS")
        workshop_layer = workshop.materialize_workshop_layer(
            store.world, lineages, chemistry, world_seed=store.world_seed
        )
        _progress(progress_callback, 88, "MATERIALIZING EXCHANGE TAILS")
        external = phase05.materialize_external_exchange(
            _SparseReports(store.population_cells, report_cache),
            lineages,
            store.canonical_hydro_context,
            world_seed=store.world_seed,
        )
        _progress(progress_callback, 92, "300 OBJECTS MATERIALIZED")
        return CrystallizedWorld(
            runtime_path=Path(runtime_path),
            runtime_fingerprint=store.runtime_fingerprint,
            world_build_id=store.world_build_id,
            player_key_hash=hashlib.sha256(player_key.strip().encode("utf-8")).hexdigest(),
            world=store.world,
            cells=list(store.cells),
            selected=selected,
            chemistry=chemistry,
            workshop_layer=workshop_layer,
            external_exchange=external,
            canonical_hydro_context=dict(store.canonical_hydro_context),
            canonical_hydro_realization_id=store.canonical_hydro_id,
        )
    finally:
        store.close()
