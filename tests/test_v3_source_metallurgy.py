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
import v3_metallurgy_netcdf
import v3_source_metallurgy as metallurgy


class FakeWorld:
    def __init__(self):
        self.nodes = {
            "origin": base.Node("origin", "Origin", 11.0, 45.0, "hub"),
            "loss": base.Node("loss", "Loss", 13.0, 45.5, "river"),
        }
        self.sources = {
            "trentino_east": base.SourceField(
                "trentino_east",
                "Eastern Trentino copper",
                11.35,
                46.12,
                1700,
                900,
                1.0,
                {
                    "Sb_ppm": 820.0,
                    "Ag_ppm": 180.0,
                    "Ni_ppm": 1100.0,
                    "Co_ppm": 95.0,
                    "Bi_ppm": 55.0,
                },
                {"Pb206_204": 18.17, "Pb207_204": 15.66, "Pb208_204": 38.35},
            ),
            "upper_atesis": base.SourceField(
                "upper_atesis",
                "Upper Atesis / central Alpine copper",
                10.70,
                46.72,
                1900,
                1000,
                0.45,
                {
                    "Sb_ppm": 430.0,
                    "Ag_ppm": 95.0,
                    "Ni_ppm": 720.0,
                    "Co_ppm": 70.0,
                    "Bi_ppm": 32.0,
                },
                {"Pb206_204": 18.25, "Pb207_204": 15.68, "Pb208_204": 38.48},
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
        source_mix={"trentino_east": 0.8, "upper_atesis": 0.2},
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
        world_seed=1300,
        production_cell_index=7,
        cell_loss_index=3,
    )
    return world, lineage


def test_pb_inventory_roundtrip_uses_atomic_inventory_not_ratio_average():
    ratios = {"Pb206_204": 18.17, "Pb207_204": 15.66, "Pb208_204": 38.35}
    inventory = metallurgy.pb_inventory_from_ratios(0.0025, ratios)
    assert math.isclose(sum(inventory.values()), 0.0025, rel_tol=1e-14)
    actual = metallurgy.pb_ratios_from_inventory(inventory)
    for key, expected in ratios.items():
        assert math.isclose(actual[key], expected, rel_tol=1e-14, abs_tol=1e-14)


def test_pb_ghost_fraction_is_weighted_by_pb_atoms_not_bulk_metal():
    low = metallurgy.pb_inventory_from_ratios(
        0.00009,
        {"Pb206_204": 18.0, "Pb207_204": 15.6, "Pb208_204": 38.0},
    )
    high = metallurgy.pb_inventory_from_ratios(
        0.001,
        {"Pb206_204": 20.0, "Pb207_204": 15.9, "Pb208_204": 40.0},
    )
    mixed = {iso: low[iso] + high[iso] for iso in metallurgy.PB_ISOTOPES}
    ratios = metallurgy.pb_ratios_from_inventory(mixed)
    # The small high-Pb component dominates the isotope view because the Pb
    # inventory, not the bulk-metal fraction, is the mixing weight.
    assert ratios["Pb206_204"] > 19.7


def test_phase02_parent_graph_drives_exact_element_and_pb_mixing():
    world, lineage = _fixture()
    chem = metallurgy.materialize_metallurgy_lineage(world, lineage)
    assert [b.batch_id for b in chem.batches] == [b.batch_id for b in lineage.batches]

    phase2 = {b.batch_id: b for b in lineage.batches}
    phase3 = {b.batch_id: b for b in chem.batches}
    for child2 in lineage.batches:
        child3 = phase3[child2.batch_id]
        metallurgy.validate_batch_chemistry(child3)
        if not child2.parent_contributions_kg:
            continue

        for element in metallurgy.ELEMENTS:
            expected = 0.0
            for parent_id, contribution in child2.parent_contributions_kg.items():
                parent2 = phase2[parent_id]
                parent3 = phase3[parent_id]
                expected += (
                    contribution
                    / parent2.metal_mass_kg
                    * parent3.element_mass_kg[element]
                )
            assert math.isclose(
                child3.element_mass_kg[element], expected, rel_tol=1e-12, abs_tol=1e-14
            )

        for isotope in metallurgy.PB_ISOTOPES:
            expected = 0.0
            for parent_id, contribution in child2.parent_contributions_kg.items():
                parent2 = phase2[parent_id]
                parent3 = phase3[parent_id]
                expected += (
                    contribution
                    / parent2.metal_mass_kg
                    * parent3.pb_isotope_mass_kg[isotope]
                )
            assert math.isclose(
                child3.pb_isotope_mass_kg[isotope], expected, rel_tol=1e-12, abs_tol=1e-14
            )


def test_source_calibration_is_frozen_and_explicitly_provisional():
    world, _ = _fixture()
    first = metallurgy.source_chemistry_table(world)
    second = metallurgy.source_chemistry_table(world)
    assert first == second
    assert first["trentino_east"].pb_ppm == metallurgy.FROZEN_PB_PPM_PRIOR["trentino_east"]
    assert all(
        row.calibration_status == metallurgy.SOURCE_CALIBRATION_STATUS
        for row in first.values()
    )
    assert "no-empirical-covariance" in metallurgy.SOURCE_CALIBRATION_STATUS


def test_phase03_netcdf_roundtrip_links_exact_phase02_batch_ids(tmp_path):
    world, lineage = _fixture()
    path = tmp_path / "v3.nc"
    with Dataset(path, "w", format="NETCDF4") as ds:
        ds.schema = "atolia-v3-v1-propagation-spine-v1"
        ds.phase = "atolia-v3-01-v1-propagation-spine"
        ds.spine_sha256 = "phase01-test-spine"

    bio_summary = v3_biography_netcdf.append_biography(
        path,
        lineages=[lineage],
        world_seed=1300,
        phase01_spine_sha256="phase01-test-spine",
    )
    chemistry = metallurgy.materialize_metallurgy(world, [lineage])
    summary = v3_metallurgy_netcdf.append_metallurgy(
        path,
        world=world,
        lineages=[lineage],
        chemistry=chemistry,
        world_seed=1300,
        phase01_spine_sha256="phase01-test-spine",
        phase02_biography_sha256=bio_summary["biography_sha256"],
    )
    actual = v3_metallurgy_netcdf.read_metallurgy(path)

    assert actual["metallurgy_sha256"] == summary["metallurgy_sha256"]
    assert actual["phase01_spine_sha256"] == "phase01-test-spine"
    assert actual["phase02_biography_sha256"] == bio_summary["biography_sha256"]
    assert actual["source_calibration_status"] == metallurgy.SOURCE_CALIBRATION_STATUS

    phase2_batch_ids = [b.batch_id for b in lineage.batches]
    phase3_batch_ids = [r["batch_id"] for r in actual["chemistry_batches"]]
    assert phase3_batch_ids == phase2_batch_ids
    assert len(actual["elements"]) == len(phase2_batch_ids) * len(metallurgy.ELEMENTS)
    assert len(actual["pb_isotopes"]) == len(phase2_batch_ids) * len(metallurgy.PB_ISOTOPES)

    with Dataset(path, "r") as ds:
        assert str(ds.phase) == "atolia-v3-01-v1-propagation-spine"
        assert str(ds.latest_phase) == v3_metallurgy_netcdf.V3_METALLURGY_PHASE
        assert str(ds.phase03_biography_sha256) == str(ds.phase02_biography_sha256)
        assert {"sources", "metallurgy"}.issubset(ds.groups)


def test_phase03_code_does_not_depend_on_rejected_v2_particle_engine():
    source = (ATOLIA / "v3_source_metallurgy.py").read_text(encoding="utf-8")
    nc_source = (ATOLIA / "v3_metallurgy_netcdf.py").read_text(encoding="utf-8")
    builder = (ATOLIA / "build_v3_master.py").read_text(encoding="utf-8")
    for token in ("build_v2_direct_world", "_simulate_particle"):
        assert token not in source
        assert token not in nc_source
        assert token not in builder
