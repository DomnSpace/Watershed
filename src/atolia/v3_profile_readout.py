from __future__ import annotations

"""Joint-representative-conditioned R17 player materialization.

R17 is the authoritative result of Phase-01 propagation. Player creation reads a
stored empirical profile and one of its retained real Phase-08 joint
representatives directly from the NetCDF; it never replays the platform-sensitive
Phase-01 active/loss threshold.

The representative is not copied into player_17 as a finished object. Its joint
state conditions a fresh coherent Phase-02 -> Phase-03 -> Phase-04 -> Phase-05
expansion: actual represented loss mass, realized remelt/repair counts, route
extent, retained source mixture/entropy and deposition mode enter the downstream
model together.
"""

import hashlib
from typing import Any, Mapping

import numpy as np

import intensity_circulation as intensity
import v3_hydro_exchange_deposition as phase05
import v3_runtime_v3 as runtime_v3


READOUT_VERSION = "atolia-v3-r17-joint-representative-conditioned-v3"
_REPRESENTATIVE_SELECTION_MASS: dict[int, float] = {}


def _strings(var: Any) -> list[str]:
    values = var[:]
    return [x.decode("utf-8") if isinstance(x, bytes) else str(x) for x in values]


def _profile_step(runtime_fingerprint: str, profile_index: int, representative_index: int, lo: int, hi: int) -> int:
    lo = int(lo)
    hi = int(hi)
    if hi < lo:
        raise RuntimeError(f"R17 profile {profile_index} has inverted step range {lo}:{hi}")
    if hi == lo:
        return lo
    raw = (
        READOUT_VERSION + "\0" + str(runtime_fingerprint) + "\0"
        + str(int(profile_index)) + "\0" + str(int(representative_index)) + "\0loss-step"
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


def _conditioned_cell(store: Any, rg: Any, representative: int, base_cell: Any) -> Any:
    """Use the retained representative's joint final source ancestry as latent source mix.

    This does not modify the canonical R17 production cell. It creates the
    private conditioned input used for one player's downstream materialization.
    Because every recycle addition sees the same conditioned source mixture, the
    final Phase-02 ancestry preserves the representative's source support and
    entropy while the canonical cell identity remains separately auditable.
    """
    if "source_ptr" not in rg.variables:
        raise RuntimeError("R17 representative source CSR is missing")
    rep = int(representative)
    ptr = rg.variables["source_ptr"]
    a, z = int(ptr[rep]), int(ptr[rep + 1])
    source_ids = list(store.world.sources)
    indices = np.asarray(rg.variables["source_index"][a:z], dtype=np.int64)
    fractions = np.asarray(rg.variables["source_fraction"][a:z], dtype=np.float64)
    if not len(indices):
        return base_cell
    if np.any(indices < 0) or np.any(indices >= len(source_ids)) or np.any(~np.isfinite(fractions)) or np.any(fractions < 0.0):
        raise RuntimeError(f"R17 representative {rep} has invalid source conditioning rows")
    mix = {source_ids[int(i)]: float(v) for i, v in zip(indices, fractions) if float(v) > 0.0}
    total = float(sum(mix.values()))
    if not mix or abs(total - 1.0) > 2e-12:
        raise RuntimeError(f"R17 representative {rep} source fractions do not close to one: {total!r}")
    return intensity.ProductionCell(
        bundle_id=base_cell.bundle_id,
        bundle_family=base_cell.bundle_family,
        object_class=base_cell.object_class,
        date_bc=base_cell.date_bc,
        origin=base_cell.origin,
        destination=base_cell.destination,
        production_intensity=base_cell.production_intensity,
        circulation_seed_intensity=base_cell.circulation_seed_intensity,
        source_mix=mix,
        recycle_mean=base_cell.recycle_mean,
    )


def _forced_assignment(store: Any, lineage: Any, stratum: Any, mode: str) -> tuple[Any, Any]:
    weights = phase05._normalize_weights(stratum.deposition_mode_weights)
    if mode not in weights or float(weights[mode]) <= 0.0:
        raise RuntimeError(f"R17 representative deposition mode {mode!r} is incompatible with its cell grammar")
    pool_id = phase05._stable_id("dep", lineage.loss_node_id, lineage.date_bc, mode)
    assignment = phase05.DepositionAssignment(
        particle_id=lineage.particle_id,
        loss_site_id=lineage.loss_site_id,
        deposition_pool_id=pool_id,
        hydro_realization_id=store.canonical_hydro_id,
        node_id=lineage.loss_node_id,
        date_bc=lineage.date_bc,
        mode=mode,
        mode_probability=float(weights[mode]),
        mode_weights=weights,
        represented_weight=float(lineage.represented_weight),
        expected_field_crossings=float(stratum.expected_field_crossings),
        expected_physical_crossings=float(stratum.expected_physical_crossings),
        hydro_context_score=float(store.canonical_hydro_context.get(lineage.loss_node_id, 0.0)),
    )
    observation = phase05.materialize_archaeology([lineage], [assignment])[0]
    return assignment, observation


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

        row: Mapping[str, Any] = store.expected_profile_row(p)
        expected_hash = bytes(np.asarray(store.profile_hash[p], dtype=np.uint8).tolist())
        if runtime_v3.profile_checkpoint_hash([row]) != expected_hash:
            raise RuntimeError(f"R17 profile {p} failed its stored Phase-01 checkpoint")
        recorded_total = float(store.profile_recorded[p])
        if not np.isfinite(recorded_total) or recorded_total <= 0.0:
            raise RuntimeError(f"R17 profile {p} has invalid archaeological weight")

        rg = store.ds.groups.get("representatives")
        if rg is None:
            raise RuntimeError("R17 lacks joint empirical representatives")
        ptr = rg.variables["profile_ptr"]
        start = int(ptr[p])
        stop = int(ptr[p + 1])
        if stop <= start or stop - start > 2:
            raise RuntimeError(f"R17 profile {p} has invalid representative interval {start}:{stop}")
        mode_names = _strings(rg.variables["mode_name"])
        deposition, field_mix = _cell_vectors(store, global_cell)

        candidates: list[Any] = []
        empirical_mass = 0.0
        for rep in range(start, stop):
            if int(rg.variables["profile_index"][rep]) != p:
                raise RuntimeError(f"R17 representative {rep} points to the wrong profile")
            representative_mass = float(rg.variables["representative_recorded_mass"][rep])
            represented_weight = float(rg.variables["source_represented_weight"][rep])
            if not np.isfinite(representative_mass) or representative_mass <= 0.0:
                raise RuntimeError(f"R17 representative {rep} has invalid empirical sampling mass")
            if not np.isfinite(represented_weight) or represented_weight <= 0.0:
                raise RuntimeError(f"R17 representative {rep} has invalid represented loss mass")
            empirical_mass += representative_mass
            _REPRESENTATIVE_SELECTION_MASS[int(rep)] = representative_mass

            remelts_raw = float(rg.variables["remelt_count"][rep])
            repairs_raw = float(rg.variables["repair_count"][rep])
            remelts = int(round(remelts_raw))
            repairs = int(round(repairs_raw))
            if remelts < 0 or repairs < 0 or remelts_raw != float(remelts) or repairs_raw != float(repairs):
                raise RuntimeError(f"R17 representative {rep} has non-integral event counts")
            route_distance = float(rg.variables["cumulative_metal_distance_km"][rep])
            source_entropy = float(rg.variables["source_entropy"][rep])
            if not np.isfinite(route_distance) or route_distance < 0.0:
                raise RuntimeError(f"R17 representative {rep} has invalid route extent")
            if not np.isfinite(source_entropy) or not 0.0 <= source_entropy <= 1.0 + 1e-12:
                raise RuntimeError(f"R17 representative {rep} has invalid source entropy")

            mode_index = int(rg.variables["mode_index"][rep])
            if mode_index < 0 or mode_index >= len(mode_names):
                raise RuntimeError(f"R17 representative {rep} has invalid deposition-mode pointer")
            mode = mode_names[mode_index]
            step = _profile_step(
                store.runtime_fingerprint,
                p,
                rep,
                int(row["step_min"]),
                int(row["step_max"]),
            )
            conditioned_cell = _conditioned_cell(store, rg, rep, cell)

            # Integer expected counts force the Phase-02 stochastic rounding to
            # the actual representative remelt/repair counts. The joint retained
            # source mixture, entropy and route extent then propagate through the
            # ordinary Phase-02/03 machinery rather than being copied as outputs.
            stratum = intensity.LossStratum(
                production_cell=conditioned_cell,
                node_id=str(node_id),
                step=int(step),
                loss_intensity=represented_weight,
                deposition_mode_weights=deposition,
                expected_recycle_count=float(remelts),
                expected_repair_count=float(repairs),
                expected_source_entropy=source_entropy,
                expected_field_crossings=float(row["expected_field_crossings_mean"]),
                expected_physical_crossings=float(row["expected_physical_crossings_mean"]),
                route_distance_from_origin_km=route_distance,
                field_mix=field_mix,
            )
            lineage = crystallizer.biography.materialize_loss_lineage(
                store.world,
                stratum,
                world_seed=store.world_seed,
                production_cell_index=global_cell,
                # The global representative coordinate is an intentional private
                # identity salt. It distinguishes the retained joint states
                # without pretending to recover the discarded original loss-row index.
                cell_loss_index=int(rep),
            )
            if lineage.remelt_count != remelts or lineage.repair_count != repairs:
                raise RuntimeError(f"R17 representative {rep} event conditioning did not survive Phase-02")
            if float(lineage.cumulative_metal_distance_km).hex() != float(route_distance).hex():
                raise RuntimeError(f"R17 representative {rep} route conditioning did not survive Phase-02")
            expected_mass = float(rg.variables["metal_mass_kg"][rep])
            if float(lineage.batches[-1].metal_mass_kg).hex() != expected_mass.hex():
                raise RuntimeError(f"R17 representative {rep} object mass differs from the empirical anchor")

            assignment, observation = _forced_assignment(store, lineage, stratum, mode)
            candidates.append(crystallizer.PreparedCandidate(
                global_cell,
                int(rep),
                stratum,
                lineage,
                assignment,
                observation,
            ))

        # Phase-08 assigns the profile's exact recorded mass across its retained
        # representatives. This is an exact compression identity independent of
        # the downstream private rematerialization.
        if empirical_mass.hex() != recorded_total.hex():
            raise RuntimeError(
                f"R17 profile {p} representative mass does not close: {empirical_mass.hex()} != {recorded_total.hex()}"
            )

        if global_cell not in report_cache:
            report_cache[global_cell] = intensity.CellFlowReport(production_cell=cell)
        return crystallizer.PreparedProfile(
            p,
            global_cell,
            str(node_id),
            candidates,
            recorded_total,
        )

    return _prepare_profile


def install(crystallizer: Any) -> str:
    """Install direct joint-representative materialization into the crystallizer."""
    # Candidate selection uses the exact representative mass allocated by
    # Phase-08, not the newly rematerialized Phase-05 observation weight.
    crystallizer.PreparedCandidate.recorded_weight = property(
        lambda self: float(_REPRESENTATIVE_SELECTION_MASS.get(
            int(self.cell_loss_index), float(self.observation.recorded_weight)
        ))
    )
    crystallizer._prepare_profile = _install_prepare_profile(crystallizer)
    return READOUT_VERSION
