from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from netCDF4 import Dataset

import intensity_circulation as intensity
import v3_hydro_exchange_deposition as phase05
import v3_phase05_netcdf as nc


def _world():
    nodes = {
        "A": SimpleNamespace(id="A", kind="river", lon=11.0, lat=45.0),
        "B": SimpleNamespace(id="B", kind="hub", lon=11.35, lat=45.0),
        "C": SimpleNamespace(id="C", kind="coast", lon=11.70, lat=45.0),
        "D": SimpleNamespace(id="D", kind="settlement", lon=12.4, lat=45.0),
    }
    edges = [
        SimpleNamespace(a="A", b="B", mode="river", directed=False),
        SimpleNamespace(a="C", b="D", mode="land", directed=False),
    ]
    return SimpleNamespace(nodes=nodes, edges=edges)


def _cell(bundle_id="cyprus_tail"):
    return intensity.ProductionCell(
        bundle_id=bundle_id,
        bundle_family="prestige_tail",
        object_class="sword",
        date_bc=1300,
        origin="A",
        destination="C",
        production_intensity=100.0,
        circulation_seed_intensity=100.0,
        source_mix={"cyprus_source": 1.0},
        recycle_mean=.3,
    )


def _reports(count: int = 2):
    cell = _cell()
    report = intensity.CellFlowReport(production_cell=cell)
    for i in range(count):
        report.loss_strata.append(intensity.LossStratum(
            production_cell=cell,
            node_id="B",
            step=i + 1,
            loss_intensity=20.0 + i,
            deposition_mode_weights={"river_wetland_deposit": 1.0},
            expected_recycle_count=.7,
            expected_repair_count=.4,
            expected_source_entropy=.2,
            expected_field_crossings=.5,
            expected_physical_crossings=1.0,
            route_distance_from_origin_km=240.0 + i * 10.0,
            field_mix={"river": .7, "land": .3},
        ))
    return [report]


def _lineage(index: int, *, weight: float = 20.0):
    return SimpleNamespace(
        particle_id=f"p{index}",
        represented_weight=weight,
        production_cell_index=0,
        cell_loss_index=index,
        loss_site_id=f"loss{index}",
        object_class="sword",
        remelt_count=1,
        repair_count=2,
        cumulative_metal_distance_km=260.0,
        loss_node_id="B",
        date_bc=1300,
    )


def test_hydro_evidence_ensemble_realization_are_separate_and_deterministic():
    world = _world()
    supplied = [{
        "evidence_id": "external-channel-1",
        "a": "B",
        "b": "C",
        "mode": "palaeochannel_candidate",
        "confidence": .8,
        "navigability": .6,
        "provenance": "fixture-survey",
        "empirical": True,
    }]
    status, evidence, ensemble = phase05.build_hydro_ensemble(world, supplied_evidence=supplied)
    assert status == phase05.HYDRO_EVIDENCE_STATUS_SUPPLIED
    assert any(row.evidence_kind == "model_graph_edge" and not row.empirical for row in evidence)
    assert any(row.evidence_id == "external-channel-1" and row.empirical for row in evidence)
    candidate = next(row for row in ensemble if {row.a, row.b} == {"B", "C"})
    assert candidate.empirical_evidence_count == 1
    assert "external-channel-1" in candidate.evidence_ids
    r1 = phase05.realize_hydro(ensemble, world_seed=1300)
    r2 = phase05.realize_hydro(ensemble, world_seed=1300)
    assert r1 == r2
    structural = next(row for row in r1 if {row.a, row.b} == {"A", "B"})
    assert structural.structural and structural.realized and structural.probability == 1.0


def test_deposition_uses_v1_mode_weights_and_builds_shared_pool():
    reports = _reports(2)
    lineages = [_lineage(0), _lineage(1)]
    _, _, ensemble = phase05.build_hydro_ensemble(_world())
    realization = phase05.realize_hydro(ensemble, world_seed=1300)
    assignments, pools = phase05.materialize_deposition(reports, lineages, realization, world_seed=1300)
    assert len(assignments) == 2
    assert {row.mode for row in assignments} == {"river_wetland_deposit"}
    assert all(row.mode_probability == 1.0 for row in assignments)
    assert len(pools) == 1
    assert pools[0].member_count == 2
    assert pools[0].represented_weight == 40.0
    assert {row.deposition_pool_id for row in assignments} == {pools[0].deposition_pool_id}


def test_observation_waterfall_is_conditional_and_monotone():
    reports = _reports(2)
    lineages = [_lineage(0), _lineage(1)]
    layer = phase05.materialize_phase05(_world(), reports, lineages, world_seed=1300)
    assert len(layer.archaeology) == 2
    for row in layer.archaeology:
        assert 0.0 < row.p_survival <= 1.0
        assert 0.0 < row.p_discovery <= 1.0
        assert 0.0 < row.p_record <= 1.0
        assert row.recorded_weight <= row.discovery_weight <= row.survival_weight <= row.represented_loss_weight


def test_external_exchange_is_sparse_deterministic_and_mass_neutral():
    reports = _reports(1)
    lineages = []
    for i in range(400):
        row = _lineage(0, weight=1.0)
        row = SimpleNamespace(**{**row.__dict__, "particle_id": f"px{i}"})
        lineages.append(row)
    _, _, ensemble = phase05.build_hydro_ensemble(_world())
    realization = phase05.realize_hydro(ensemble, world_seed=1300)
    context = phase05._hydro_context(realization)
    a = phase05.materialize_external_exchange(reports, lineages, context, world_seed=1300)
    b = phase05.materialize_external_exchange(reports, lineages, context, world_seed=1300)
    assert a == b
    assert 0 < len(a) < len(lineages) // 5
    assert all(row.external_component_id == "external_eastern_med" for row in a)
    assert all(0.0 < row.contact_intensity < .13 for row in a)


def test_phase05_netcdf_roundtrip_and_hash_links(tmp_path: Path):
    reports = _reports(2)
    lineages = [_lineage(0), _lineage(1)]
    layer = phase05.materialize_phase05(_world(), reports, lineages, world_seed=1300)
    path = tmp_path / "phase05.nc"
    with Dataset(path, "w", format="NETCDF4") as ds:
        ds.phase04_workshop_sha256 = "w4"
    summary = nc.append_phase05(
        path,
        layer=layer,
        world_seed=1300,
        phase01_spine_sha256="s1",
        phase02_biography_sha256="b2",
        phase03_metallurgy_sha256="m3",
        phase04_workshop_sha256="w4",
    )
    read = nc.read_phase05(path)
    assert read["phase05_sha256"] == summary["phase05_sha256"]
    assert read["phase04_workshop_sha256"] == "w4"
    assert len(read["deposition_assignments"]) == len(lineages)
    assert len(read["archaeology"]) == len(lineages)
    assert read["deposition_assignments"][0]["mode_weights"] == {"river_wetland_deposit": 1.0}
    assert read["hydro_evidence_status"] == phase05.HYDRO_EVIDENCE_STATUS_STRUCTURAL_ONLY


def test_phase05_source_does_not_import_rejected_v2_particle_engine():
    root = Path(__file__).resolve().parents[1]
    text = "\n".join([
        (root / "src/atolia/v3_hydro_exchange_deposition.py").read_text(encoding="utf-8"),
        (root / "src/atolia/v3_phase05_netcdf.py").read_text(encoding="utf-8"),
    ])
    assert "build_v2_direct_world" not in text
    assert "_simulate_particle" not in text
