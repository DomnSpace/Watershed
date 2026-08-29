from __future__ import annotations

import math
import sys
from pathlib import Path

from netCDF4 import Dataset

ROOT = Path(__file__).resolve().parents[1]
ATOLIA = ROOT / "src" / "atolia"
if str(ATOLIA) not in sys.path:
    sys.path.insert(0, str(ATOLIA))

import intensity_circulation as intensity
import provenance_field as base
import v3_biography_netcdf
import v3_metal_biography as metal


class FakeWorld:
    def __init__(self):
        self.nodes = {
            "origin": base.Node("origin", "Origin", 11.0, 45.0, "hub"),
            "loss": base.Node("loss", "Loss", 13.0, 45.5, "river"),
        }
        self.sources = {
            "source_a": base.SourceField(
                "source_a", "A", 10.0, 46.0, 1800, 1000, 1.0, {}, {}
            ),
            "source_b": base.SourceField(
                "source_b", "B", 12.0, 46.0, 1800, 1000, 1.0, {}, {}
            ),
        }


def _fixture():
    world = FakeWorld()
    cell = intensity.ProductionCell(
        bundle_id="bundle",
        bundle_family="local_recycling",
        object_class="axe",
        date_bc=1300,
        origin="origin",
        destination="loss",
        production_intensity=1000.0,
        circulation_seed_intensity=1000.0,
        source_mix={"source_a": 0.8, "source_b": 0.2},
        recycle_mean=0.5,
    )
    stratum = intensity.LossStratum(
        production_cell=cell,
        node_id="loss",
        step=5,
        loss_intensity=123.5,
        deposition_mode_weights={"river_wetland_deposit": 1.0},
        expected_recycle_count=2.0,
        expected_repair_count=1.0,
        expected_source_entropy=1.0,
        expected_field_crossings=1.2,
        expected_physical_crossings=0.8,
        route_distance_from_origin_km=300.0,
        field_mix={"local_catchment_reuse": 1.0},
    )
    return world, stratum


def _lineage(seed=1300):
    world, stratum = _fixture()
    return metal.materialize_loss_lineage(
        world,
        stratum,
        world_seed=seed,
        production_cell_index=7,
        cell_loss_index=3,
    )


def test_full_remelt_is_physical_parent_mass_mixing():
    lineage = _lineage()
    assert lineage.remelt_count == 2
    assert lineage.repair_count == 1
    assert len(lineage.batches) == 5
    assert len(lineage.episodes) == 3
    assert [event.kind for event in lineage.events].count("remelt") == 2
    assert [event.kind for event in lineage.events].count("repair") == 1
    assert lineage.events[-1].kind == "loss"

    batch_by_id = {batch.batch_id: batch for batch in lineage.batches}
    remelt_outputs = [b for b in lineage.batches if b.role == "remelt_output"]
    assert len(remelt_outputs) == 2

    for child in remelt_outputs:
        assert len(child.parent_contributions_kg) == 2
        assert sum(child.parent_contributions_kg.values()) == child.metal_mass_kg
        assert sum(child.ancestry_mass_kg.values()) == child.metal_mass_kg
        for parent_id in child.parent_contributions_kg:
            assert parent_id in batch_by_id

    metal.validate_lineage(lineage)


def test_three_distances_are_distinct_and_no_route_nodes_are_fabricated():
    lineage = _lineage()
    assert lineage.ore_distance_km > 0.0
    assert lineage.cumulative_metal_distance_km == 300.0
    assert 0.0 <= lineage.current_object_distance_km <= 300.0
    assert lineage.current_object_distance_km < lineage.cumulative_metal_distance_km

    intermediate = [
        event
        for event in lineage.events
        if event.kind in {"repair", "remelt"}
        and 0.0 < event.route_position_km < lineage.cumulative_metal_distance_km
    ]
    assert intermediate
    assert all(event.node_id is None for event in intermediate)
    assert lineage.events[-1].node_id == "loss"


def test_source_ancestry_stays_on_existing_support_and_normalizes():
    lineage = _lineage()
    allowed = {"source_a", "source_b"}
    for batch in lineage.batches:
        assert set(batch.ancestry_mass_kg) <= allowed
        total = sum(batch.ancestry_mass_kg.values())
        assert math.isclose(total, batch.metal_mass_kg, rel_tol=1e-12, abs_tol=1e-12)

    initial_entropy = metal.source_entropy_from_mass(lineage.batches[0].ancestry_mass_kg)
    assert lineage.source_entropy >= initial_entropy


def test_same_seed_is_identical_and_different_seed_changes_biography():
    a = _lineage(1300)
    b = _lineage(1300)
    c = _lineage(1301)
    assert a == b
    assert a.particle_id != c.particle_id
    assert a.events != c.events


def test_flattened_indices_are_closed_and_parent_graph_points_backward():
    lineage = _lineage()
    tables = metal.flatten_lineages([lineage])
    assert len(tables["particles"]) == 1
    particle = tables["particles"][0]
    assert particle["production_cell_id"].startswith("pc_")
    assert particle["loss_site_id"].startswith("ls_")
    assert particle["metal_batch_id"] == lineage.final_batch_id
    assert particle["object_episode_id"] == lineage.final_object_episode_id
    batch_count = len(tables["batches"])
    episode_count = len(tables["episodes"])
    for link in tables["parents"]:
        assert 0 <= link["parent_batch_index"] < link["child_batch_index"] < batch_count
    for event in tables["events"]:
        assert 0 <= event["episode_index"] < episode_count
        assert all(0 <= i < batch_count for i in event["input_batch_indices"])
        assert event["output_batch_index"] == -1 or 0 <= event["output_batch_index"] < batch_count


def test_phase02_netcdf_round_trip_is_exact_and_preserves_phase01_marker(tmp_path):
    lineage = _lineage()
    path = tmp_path / "v3.nc"
    with Dataset(path, "w", format="NETCDF4") as ds:
        ds.schema = "atolia-v3-v1-propagation-spine-v1"
        ds.phase = "atolia-v3-01-v1-propagation-spine"
        ds.spine_sha256 = "phase01-test-spine"

    expected_tables = metal.flatten_lineages([lineage])
    expected_hash = v3_biography_netcdf.biography_hash(expected_tables)
    summary = v3_biography_netcdf.append_biography(
        path,
        lineages=[lineage],
        world_seed=1300,
        phase01_spine_sha256="phase01-test-spine",
    )
    actual = v3_biography_netcdf.read_biography(path)

    assert actual["biography_sha256"] == expected_hash
    assert summary["biography_sha256"] == expected_hash
    for name, rows in expected_tables.items():
        assert actual[name] == rows

    with Dataset(path, "r") as ds:
        assert str(ds.phase) == "atolia-v3-01-v1-propagation-spine"
        assert str(ds.spine_sha256) == "phase01-test-spine"
        assert str(ds.latest_phase) == "atolia-v3-02-metal-biography"


def test_phase02_source_does_not_depend_on_rejected_v2_engine():
    source = (ATOLIA / "v3_metal_biography.py").read_text(encoding="utf-8")
    builder = (ATOLIA / "build_v3_master.py").read_text(encoding="utf-8")
    banned = ("build_v2_direct_world", "_simulate_particle")
    for token in banned:
        assert token not in source
        assert token not in builder
