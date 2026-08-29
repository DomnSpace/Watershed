from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

ROOT = Path(__file__).resolve().parents[1]
ATOLIA = ROOT / "src" / "atolia"
if str(ATOLIA) not in sys.path:
    sys.path.insert(0, str(ATOLIA))

import intensity_circulation as intensity
import provenance_field as base
import v2_workshop_tools
import v3_metal_biography as metal
import v3_source_metallurgy as metallurgy
import v3_workshop_ecology as workshop
import v3_workshop_netcdf


class FakeWorld:
    def __init__(self):
        self.nodes = {
            "origin": base.Node("origin", "Origin", 11.0, 45.0, "hub"),
            "loss": base.Node("loss", "Loss", 13.0, 45.5, "river"),
        }
        isotope = {"Pb206_204": 18.2, "Pb207_204": 15.65, "Pb208_204": 38.3}
        self.sources = {
            "source_a": base.SourceField(
                "source_a", "A", 10.0, 46.0, 1800, 1000, 1.0,
                {"Sb_ppm": 400, "Ag_ppm": 100, "Ni_ppm": 700, "Co_ppm": 80, "Bi_ppm": 30},
                isotope,
            ),
            "source_b": base.SourceField(
                "source_b", "B", 12.0, 46.0, 1800, 1000, 1.0,
                {"Sb_ppm": 800, "Ag_ppm": 200, "Ni_ppm": 300, "Co_ppm": 50, "Bi_ppm": 70},
                {"Pb206_204": 18.5, "Pb207_204": 15.70, "Pb208_204": 38.7},
            ),
        }
        self.workshops = [
            base.Workshop(
                "W-0001", "origin", 11.0, 45.0, 1400, 1200, 6, "L-001",
                np.asarray([.28, .12, .18, .16, .14, .12]), 5.0,
            ),
            base.Workshop(
                "W-0002", "loss", 13.0, 45.5, 1400, 1200, 4, "L-002",
                np.asarray([.12, .14, .12, .18, .20, .24]), 3.0,
            ),
        ]
        self.workshops_by_node = defaultdict(list, {"origin": [0], "loss": [1]})
        self.workshop_guild = {"W-0001": "G-01", "W-0002": "G-07"}
        self.guild_strength = {"W-0001": .8, "W-0002": .7}
        self.guilds = {}
        anchors = ["origin", "loss"]
        for i in range(12):
            gid = f"G-{i+1:02d}"
            proto = self.workshops[i % 2].technical_vector.copy()
            self.guilds[gid] = {
                "prototype": proto,
                "anchor_node": anchors[i % 2],
                "mobility_scale": 300.0 + i * 20.0,
                "core_seed_workshops": [],
            }

    def _network_distance(self, start: str, goal: str) -> float:
        return 0.0 if start == goal else 120.0


def _fixture(seed: int = 1300):
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
    lineage = metal.materialize_loss_lineage(
        world,
        stratum,
        world_seed=seed,
        production_cell_index=7,
        cell_loss_index=3,
    )
    chemistry = metallurgy.materialize_metallurgy(world, [lineage])
    return world, lineage, chemistry


def test_phase04_reuses_v1_workshop_dates_and_builds_real_tool_ecology():
    world, lineage, chemistry = _fixture()
    before = [(w.id, w.start_bc, w.end_bc, w.node_id) for w in world.workshops]
    layer = workshop.materialize_workshop_layer(
        world, [lineage], chemistry, world_seed=1300
    )
    after = [(w.id, w.start_bc, w.end_bc, w.node_id) for w in world.workshops]

    assert before == after
    assert len(layer.workshop_rows) == 2
    assert len(layer.guild_rows) == 12
    assert len(layer.membership_rows) == 24
    assert len(layer.archetype_rows) == len(v2_workshop_tools.TOOL_ARCHETYPES)
    assert layer.tool_rows
    assert any(row["nickname"] for row in layer.tool_rows)


def test_known_origin_gets_local_workshop_but_route_interior_stays_unknown():
    world, lineage, chemistry = _fixture()
    layer = workshop.materialize_workshop_layer(
        world, [lineage], chemistry, world_seed=1300
    )

    manufacture = [op for op in layer.operations if op.event_kind == "manufacture"]
    assert manufacture
    assert all(op.node_id == "origin" for op in manufacture)
    assert all(op.workshop_id == "W-0001" for op in manufacture)
    assert all(op.assignment_basis == "same_node_active_workshop" for op in manufacture)

    interior = [
        op for op in layer.operations
        if op.event_kind in {"repair", "remelt"}
    ]
    assert interior
    assert all(op.node_id is None for op in interior)
    assert all(op.workshop_id is None for op in interior)
    assert all(op.tool_ids == () for op in interior)
    assert all(op.capability is None for op in interior)
    assert all(
        op.assignment_basis == "unlocalized_phase02_route_interior"
        for op in interior
    )


def test_tool_sets_and_weak_link_capability_are_physical_not_binary_unlocks():
    world, lineage, chemistry = _fixture()
    layer = workshop.materialize_workshop_layer(
        world, [lineage], chemistry, world_seed=1300
    )
    localized = [op for op in layer.operations if op.workshop_id is not None]
    assert localized
    assert any(op.tool_ids for op in localized)
    assert all(op.capability is not None for op in localized)
    assert all(0.0 <= float(op.capability) <= 1.5 for op in localized)

    assert v2_workshop_tools.weak_link_capability([1.2, 1.2, 1.2]) > 1.0


def test_flattened_sparse_links_close_and_tool_use_is_derived_from_operations():
    world, lineage, chemistry = _fixture()
    layer = workshop.materialize_workshop_layer(
        world, [lineage], chemistry, world_seed=1300
    )
    tables = workshop.flatten_workshop_layer(layer)

    workshop_count = len(tables["workshops"])
    tool_count = len(tables["tools"])
    operation_count = len(tables["operations"])
    assert operation_count == len(layer.operations)

    for op in tables["operations"]:
        if op["localized"]:
            assert 0 <= op["workshop_index"] < workshop_count
            assert op["workshop_id"] is not None
        else:
            assert op["workshop_index"] == -1
            assert op["workshop_id"] is None

    for link in tables["operation_tools"]:
        assert 0 <= link["operation_index"] < operation_count
        assert 0 <= link["tool_index"] < tool_count

    linked_tools = {row["tool_index"] for row in tables["operation_tools"]}
    for use in tables["tool_use"]:
        if use["tool_index"] in linked_tools:
            assert use["localized_operation_count"] > 0
            assert use["represented_operation_weight"] > 0.0
            assert use["represented_mass_kg"] > 0.0


def test_phase04_netcdf_roundtrip_is_exact_and_links_phase03_hash(tmp_path):
    world, lineage, chemistry = _fixture()
    layer = workshop.materialize_workshop_layer(
        world, [lineage], chemistry, world_seed=1300
    )
    tables = workshop.flatten_workshop_layer(layer)
    expected_hash = v3_workshop_netcdf.workshop_hash(tables)

    path = tmp_path / "v3.nc"
    with Dataset(path, "w", format="NETCDF4") as ds:
        ds.schema = "atolia-v3-v1-propagation-spine-v1"
        ds.phase = "atolia-v3-01-v1-propagation-spine"
        ds.spine_sha256 = "phase01-test-spine"
        ds.phase02_biography_sha256 = "phase02-test-bio"
        ds.phase03_metallurgy_sha256 = "phase03-test-metal"

    summary = v3_workshop_netcdf.append_workshop_layer(
        path,
        layer=layer,
        world_seed=1300,
        phase01_spine_sha256="phase01-test-spine",
        phase02_biography_sha256="phase02-test-bio",
        phase03_metallurgy_sha256="phase03-test-metal",
    )
    actual = v3_workshop_netcdf.read_workshop_layer(path)

    assert summary["workshop_sha256"] == expected_hash
    assert actual["workshop_sha256"] == expected_hash
    assert actual["phase03_metallurgy_sha256"] == "phase03-test-metal"
    for name, expected in tables.items():
        assert actual[name] == expected


def test_phase04_source_refuses_old_mutating_and_fake_history_paths():
    source = (ATOLIA / "v3_workshop_ecology.py").read_text(encoding="utf-8")
    assert "seed_all_workshop_ecologies(" not in source
    assert "world._active_workshop(" not in source
    assert "build_v2_direct_world" not in source
    assert "_simulate_particle" not in source
