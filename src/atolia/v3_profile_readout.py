from __future__ import annotations

"""Profile-conditioned R17 player materialization.

The shipped R17 profile field is authoritative.  Player creation must not replay
``intensity.propagate_cell`` on the client: the canonical Phase-07 corpus was
produced on a different numerical platform and its 1e-5 active/loss threshold
can change the *count* of tiny strata after only a few ULPs of arithmetic drift.

Instead one selected empirical (production-cell, loss-node) profile is converted
straight into one deterministic LossStratum using the exact profile moments
stored in R17.  Phase-02..05 then materialize the private detailed biography from
that frozen latent state.  This is the old weather-readout boundary: query one
stored latent profile, expand only that profile.
"""

import hashlib
from typing import Any, Mapping

import numpy as np

import intensity_circulation as intensity
import v3_runtime_v3 as runtime_v3


READOUT_VERSION = "atolia-v3-r17-profile-conditioned-materialization-v1"


def _strings(var: Any) -> list[str]:
    values = var[:]
    return [x.decode("utf-8") if isinstance(x, bytes) else str(x) for x in values]


def _profile_step(runtime_fingerprint: str, profile_index: int, lo: int, hi: int) -> int:
    lo = int(lo)
    hi = int(hi)
    if hi < lo:
        raise RuntimeError(f"R17 profile {profile_index} has inverted step range {lo}:{hi}")
    if hi == lo:
        return lo
    raw = (
        READOUT_VERSION + "\0" + str(runtime_fingerprint) + "\0"
        + str(int(profile_index)) + "\0loss-step"
    ).encode("utf-8")
    draw = int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")
    return lo + (draw % (hi - lo + 1))


def _cell_vectors(store: Any, global_cell: int) -> tuple[dict[str, float], dict[str, float]]:
    g = store.ds.groups["production_cells"]
    mode_names = _strings(g.variables["deposition_mode_name"])
    mode_values = np.asarray(g.variables["deposition_weight"][int(global_cell), :], dtype=np.float64)
    deposition = {
        name: float(value)
        for name, value in zip(mode_names, mode_values)
        if float(value) > 0.0
    }
    if not deposition or not np.isfinite(mode_values).all():
        raise RuntimeError(f"R17 production cell {global_cell} has invalid deposition readout")

    field_names = _strings(g.variables["transport_field_name"])
    field_values = np.asarray(g.variables["transport_field_mix"][int(global_cell), :], dtype=np.float64)
    field_mix = {
        name: float(value)
        for name, value in zip(field_names, field_values)
        if float(value) > 0.0
    }
    if not field_mix or not np.isfinite(field_values).all():
        raise RuntimeError(f"R17 production cell {global_cell} has invalid transport-field readout")
    return deposition, field_mix


def _profile_local_index(store: Any, profile_index: int, global_cell: int) -> int:
    gp = store.ds.groups["profiles"]
    ptr = gp.variables["cell_ptr"]
    start = int(ptr[int(global_cell)])
    stop = int(ptr[int(global_cell) + 1])
    p = int(profile_index)
    if p < start or p >= stop:
        raise RuntimeError(
            f"R17 profile {p} is outside its cell CSR interval {start}:{stop} for cell {global_cell}"
        )
    return p - start


def _install_prepare_profile(crystallizer: Any):
    def _prepare_profile(
        store: Any,
        profile_index: int,
        report_cache: dict[int, intensity.CellFlowReport],
    ) -> Any:
        p = int(profile_index)
        global_cell = int(store.profile_cell[p])
        node_id = store.node_ids[int(store.profile_node[p])]
        cell = store.cells[global_cell]

        expected_cell = bytes(np.asarray(store.cell_identity_hash[global_cell], dtype=np.uint8).tolist())
        if crystallizer._cell_identity(store, global_cell, cell) != expected_cell:
            raise RuntimeError(f"R17 frozen production cell {global_cell} failed identity checkpoint")

        # Validate the stored canonical profile itself.  We deliberately do not
        # regenerate Phase-01 and compare against it; that would reintroduce the
        # platform-sensitive threshold boundary this readout exists to remove.
        row: Mapping[str, Any] = store.expected_profile_row(p)
        expected_hash = bytes(np.asarray(store.profile_hash[p], dtype=np.uint8).tolist())
        if runtime_v3.profile_checkpoint_hash([row]) != expected_hash:
            raise RuntimeError(f"R17 profile {p} failed its stored Phase-01 checkpoint")

        lineage_count = int(row["lineage_count"])
        if lineage_count <= 0:
            raise RuntimeError(f"R17 profile {p} has non-positive lineage_count")
        loss_total = float(store.profile_loss[p])
        represented_total = float(store.profile_represented[p])
        recorded_total = float(store.profile_recorded[p])
        if not all(np.isfinite(x) and x > 0.0 for x in (loss_total, represented_total, recorded_total)):
            raise RuntimeError(f"R17 profile {p} has invalid empirical weights")

        deposition, field_mix = _cell_vectors(store, global_cell)
        step = _profile_step(
            store.runtime_fingerprint,
            p,
            int(row["step_min"]),
            int(row["step_max"]),
        )
        local_profile = _profile_local_index(store, p, global_cell)

        # One deterministic materialized lineage represents this empirical
        # profile.  Its statistical weight is the canonical mean lineage loss
        # mass; profile selection itself remains weighted by the exact stored
        # archaeological recorded mass.
        per_lineage_loss = loss_total / float(lineage_count)
        stratum = intensity.LossStratum(
            production_cell=cell,
            node_id=str(node_id),
            step=int(step),
            loss_intensity=float(per_lineage_loss),
            deposition_mode_weights=deposition,
            expected_recycle_count=float(row["expected_recycle_count_mean"]),
            expected_repair_count=float(row["expected_repair_count_mean"]),
            expected_source_entropy=float(row["expected_source_entropy_mean"]),
            expected_field_crossings=float(row["expected_field_crossings_mean"]),
            expected_physical_crossings=float(row["expected_physical_crossings_mean"]),
            route_distance_from_origin_km=float(row["route_distance_from_origin_km_mean"]),
            field_mix=field_mix,
        )

        lineage = crystallizer.biography.materialize_loss_lineage(
            store.world,
            stratum,
            world_seed=store.world_seed,
            production_cell_index=global_cell,
            cell_loss_index=local_profile,
        )
        assignment, observation = crystallizer._assignment_for(store, lineage, stratum)
        candidate = crystallizer.PreparedCandidate(
            global_cell,
            local_profile,
            stratum,
            lineage,
            assignment,
            observation,
        )

        # External-exchange materialization only needs the production cell from
        # the sparse report lookup.  Never populate this with replayed strata.
        if global_cell not in report_cache:
            report_cache[global_cell] = intensity.CellFlowReport(production_cell=cell)

        return crystallizer.PreparedProfile(
            p,
            global_cell,
            str(node_id),
            [candidate],
            recorded_total,
        )

    return _prepare_profile


def install(crystallizer: Any) -> str:
    """Install the frozen-profile materializer into the existing crystallizer."""
    crystallizer._prepare_profile = _install_prepare_profile(crystallizer)
    return READOUT_VERSION
