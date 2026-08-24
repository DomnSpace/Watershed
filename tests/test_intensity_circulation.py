from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ATOLIA = ROOT / "src" / "atolia"
if str(ATOLIA) not in sys.path:
    sys.path.insert(0, str(ATOLIA))

import intensity_circulation as ic
import rare_event_materializer as rem


def test_competing_hazards_are_normalized():
    p = ic.competing_probabilities({"return": .1, "recycle": .2, "loss": .03, "retire": .04})
    assert sum(p.values()) == pytest.approx(1.0, abs=1e-12)
    assert 0 < p["continue"] < 1
    assert p["recycle"] > p["loss"]


def test_hazard_limit_for_zero_rates():
    p = ic.competing_probabilities({"return": 0.0, "loss": 0.0})
    assert p["continue"] == 1.0
    assert p["return"] == 0.0
    assert p["loss"] == 0.0


def test_candidate_allocation_preserves_exact_budget_for_positive_strata():
    cell = ic.ProductionCell("b", "local_recycling", "awl", 1300, "a", "b", 1e6, 1e6, {"x": 1.0}, .5)
    strata = [ic.LossStratum(cell, f"n{i}", i, float(i + 1) * 100,
              {"wetland": .5, "settlement": .5}, .2, .1, .1, .1, .1, 10.0 * i,
              {"local_catchment_reuse": 1.0}) for i in range(5)]
    report = ic.CellFlowReport(cell, loss_strata=strata)
    alloc = rem.allocate_candidate_budget([report], target_candidates=101)
    assert sum(n for _, _, n in alloc) == 101


def test_importance_weights_reconstruct_expected_candidate_intensity():
    cell = ic.ProductionCell("b", "prestige_long_distance", "sword", 1200, "a", "b", 1e6, 1e6, {"x": .8, "y": .2}, .3)
    s = ic.LossStratum(cell, "n", 4, 1000.0, {"wetland": .7, "field_loss": .3}, .5, .2, .3, .4, .2, 800.0,
                       {"rhine_north_sea": .5, "danube_sava_morava": .5})
    report = ic.CellFlowReport(cell, loss_strata=[s])
    alloc = rem.allocate_candidate_budget([report], target_candidates=17)
    expected = rem.expected_candidate_intensity(s)
    assert alloc[0][1] == pytest.approx(expected)
    assert alloc[0][2] == 17


def test_local_loss_prior_is_not_artificially_zero():
    cell = ic.ProductionCell("b", "local_recycling", "awl", 1300, "a", "b", 1000, 1000, {"x": 1.0}, .6)
    s = ic.LossStratum(cell, "n", 1, 100.0, {"settlement": 1.0}, .8, .1, 0, 0, 0, 5.0,
                       {"local_catchment_reuse": 1.0})
    assert rem.materialization_probability(s) > 0
