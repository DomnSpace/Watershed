from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
ATOLIA = ROOT / "src" / "atolia"
if str(ATOLIA) not in sys.path:
    sys.path.insert(0, str(ATOLIA))

import v3_medium_stratified as medium


def _world_and_cells():
    nodes = {
        "A": SimpleNamespace(lon=10.0, lat=45.0),
        "B": SimpleNamespace(lon=10.4, lat=45.1),
        "C": SimpleNamespace(lon=15.0, lat=44.0),
        "D": SimpleNamespace(lon=28.0, lat=35.0),
    }
    world = SimpleNamespace(nodes=nodes)
    cells = []
    classes = ["axe", "sword", "ornament", "sickle"]
    endpoints = [("A", "B"), ("A", "C"), ("A", "D"), ("C", "D")]
    for i in range(80):
        origin, destination = endpoints[i % len(endpoints)]
        cells.append(SimpleNamespace(
            bundle_family=f"family-{i % 5}",
            object_class=classes[i % len(classes)],
            date_bc=1800 - 100 * (i % 8),
            origin=origin,
            destination=destination,
            production_intensity=10.0 + i,
            source_mix={"s1": .9, "s2": .1} if i % 3 else {"s1": .4, "s2": .35, "s3": .25},
            recycle_mean=(i % 4) * .12,
        ))
    return world, cells


def test_medium_selection_is_deterministic_and_keeps_global_indices():
    world, cells = _world_and_cells()
    frame = medium.build_cell_frame(world, cells)
    a = medium.select_medium_cohort(frame, target_cells=32, seed=1300)
    b = medium.select_medium_cohort(frame, target_cells=32, seed=1300)
    assert a == b
    assert len(a.selected) == 32
    assert len({row.global_cell_index for row in a.selected}) == 32
    assert [row.local_cell_index for row in a.selected] == list(range(32))
    assert all(0.0 < row.inclusion_probability <= 1.0 for row in a.selected)
    assert all(abs(row.reconstruction_weight * row.inclusion_probability - 1.0) < 1e-12 for row in a.selected)


def test_all_occupied_strata_receive_a_row_when_budget_allows():
    world, cells = _world_and_cells()
    frame = medium.build_cell_frame(world, cells)
    occupied = {row.stratum_id for row in frame}
    plan = medium.select_medium_cohort(frame, target_cells=len(occupied) + 8, seed=7)
    selected_strata = {row.stratum_id for row in plan.selected}
    assert selected_strata == occupied


def test_full_selection_reconstructs_exact_production_distribution():
    world, cells = _world_and_cells()
    frame = medium.build_cell_frame(world, cells)
    plan = medium.select_medium_cohort(frame, target_cells=len(frame), seed=9)
    metrics, summary = medium.production_preservation(frame, plan)
    assert summary["all_passed"]
    assert all(row["value"] == 0.0 for row in metrics)


def test_probe_is_repeatable_and_bounded():
    a = medium.select_probe_indices(100, probe_cells=17, seed=1300)
    b = medium.select_probe_indices(100, probe_cells=17, seed=1300)
    assert a == b
    assert len(a) == 17
    assert len(set(a)) == 17
    assert all(0 <= index < 100 for index in a)


def test_downstream_metrics_are_zero_for_identical_weighted_joint_rows():
    rows = [
        {"weight": 3.0, "features": {"distance_band": "0-100", "remelt_band": "0", "distance_x_remelt": "0-100|0"}},
        {"weight": 1.0, "features": {"distance_band": "700-1400", "remelt_band": "2", "distance_x_remelt": "700-1400|2"}},
    ]
    metrics, summary = medium.downstream_preservation(rows, rows)
    assert summary["all_passed"]
    assert all(row["value"] == 0.0 for row in metrics)
