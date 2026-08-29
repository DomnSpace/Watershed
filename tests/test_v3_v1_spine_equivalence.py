from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
ATOLIA = ROOT / "src" / "atolia"
if str(ATOLIA) not in sys.path:
    sys.path.insert(0, str(ATOLIA))

import archaeology_temporal_world as archaeology
import build_v3_master
import intensity_circulation as intensity
import release_candidate_invariants as release_invariants
import v3_netcdf


HYPOTHESIS = ROOT / "hypotheses" / "atolia_atesis_1800_1000_v0.json"
WORLD_SEED = 1300
WORKSHOPS = 24
STEPS = 2
TARGET_GEOGRAPHY_NODES = 80


def _stable_json(value: Mapping[str, Any]) -> str:
    plain = {str(k): float(v) for k, v in value.items()}
    return json.dumps(plain, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _expected_v1_rows(reports):
    cells = []
    losses = []
    loss_index = 0
    for cell_index, report in enumerate(reports):
        cell = report.production_cell
        cells.append({
            "cell_index": int(cell_index),
            "bundle_id": str(cell.bundle_id),
            "bundle_family": str(cell.bundle_family),
            "object_class": str(cell.object_class),
            "date_bc": int(cell.date_bc),
            "origin": str(cell.origin),
            "destination": str(cell.destination),
            "production_intensity": float(cell.production_intensity),
            "circulation_seed_intensity": float(cell.circulation_seed_intensity),
            "source_mix_json": _stable_json(dict(cell.source_mix)),
            "recycle_mean": float(cell.recycle_mean),
            "produced": float(report.produced),
            "circulation_seed": float(report.circulation_seed),
            "transfer_flux": float(report.transfer_flux),
            "return_flux": float(report.return_flux),
            "recycle_flux": float(report.recycle_flux),
            "loss_flux": float(report.loss_flux),
            "retire_flux": float(report.retire_flux),
            "residual_active": float(report.residual_active),
            "max_active_nodes": int(report.max_active_nodes),
            "loss_strata_count": int(len(report.loss_strata)),
            "conservation_error": float(report.conservation_error()),
            "relative_conservation_error": float(report.relative_conservation_error()),
        })
        for cell_loss_index, stratum in enumerate(report.loss_strata):
            losses.append({
                "loss_index": int(loss_index),
                "cell_index": int(cell_index),
                "cell_loss_index": int(cell_loss_index),
                "node_id": str(stratum.node_id),
                "step": int(stratum.step),
                "loss_intensity": float(stratum.loss_intensity),
                "deposition_mode_weights_json": _stable_json(
                    dict(stratum.deposition_mode_weights)
                ),
                "expected_recycle_count": float(stratum.expected_recycle_count),
                "expected_repair_count": float(stratum.expected_repair_count),
                "expected_source_entropy": float(stratum.expected_source_entropy),
                "expected_field_crossings": float(stratum.expected_field_crossings),
                "expected_physical_crossings": float(stratum.expected_physical_crossings),
                "route_distance_from_origin_km": float(
                    stratum.route_distance_from_origin_km
                ),
                "field_mix_json": _stable_json(dict(stratum.field_mix)),
            })
            loss_index += 1
    return cells, losses


def _run_existing_v1_path(hypothesis):
    release_invariants.install()
    world = archaeology.TemporalFieldArchaeologicalWorld(
        hypothesis,
        seed=WORLD_SEED,
        target_geography_nodes=TARGET_GEOGRAPHY_NODES,
    )
    world.build(workshop_count=WORKSHOPS)
    reports, flow = intensity.propagate_world(world, max_steps=STEPS)
    return reports, flow


def test_v3_phase01_is_exact_v1_propagation_spine(tmp_path):
    hypothesis_v1 = json.loads(HYPOTHESIS.read_text(encoding="utf-8"))
    hypothesis_v3 = json.loads(HYPOTHESIS.read_text(encoding="utf-8"))

    v1_reports, v1_flow = _run_existing_v1_path(hypothesis_v1)
    expected_cells, expected_losses = _expected_v1_rows(v1_reports)

    out = tmp_path / "atolia_master_v3_spine.nc"
    summary = build_v3_master.build_master(
        hypothesis_v3,
        out_path=out,
        world_seed=WORLD_SEED,
        workshop_count=WORKSHOPS,
        intensity_steps=STEPS,
        target_geography_nodes=TARGET_GEOGRAPHY_NODES,
    )
    actual = v3_netcdf.read_spine_master(out)

    assert actual["schema"] == v3_netcdf.V3_SPINE_SCHEMA
    assert actual["phase"] == v3_netcdf.V3_PHASE
    assert actual["world_seed"] == WORLD_SEED
    assert actual["workshop_count"] == WORKSHOPS
    assert actual["intensity_steps"] == STEPS
    assert actual["target_geography_nodes"] == TARGET_GEOGRAPHY_NODES
    assert actual["intensity_model_version"] == intensity.INTENSITY_MODEL_VERSION

    # Gate G2 phase-01 equivalence: every aggregate production/report field and
    # every emitted v1 loss-stratum field must survive the NetCDF round trip.
    assert actual["cells"] == expected_cells
    assert actual["loss_strata"] == expected_losses
    assert actual["flow_summary"] == v3_netcdf.normalized_flow_summary(v1_flow)

    expected_hash = v3_netcdf.spine_hash(
        expected_cells,
        expected_losses,
        v1_flow,
    )
    assert actual["spine_sha256"] == expected_hash
    assert summary["spine_sha256"] == expected_hash
    assert summary["cells"] == len(expected_cells)
    assert summary["loss_strata"] == len(expected_losses)


def test_v3_phase01_does_not_call_v2_direct_particle_engine():
    source = inspect.getsource(build_v3_master)
    assert "build_v2_direct_world" not in source
    assert "_simulate_particle" not in source
