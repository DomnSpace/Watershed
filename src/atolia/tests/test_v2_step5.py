from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace
import sys

import numpy as np

HERE = Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import provenance_field as base
import v2_config as cfg
import v2_workshop_tools as workshop_tools
from v2_netcdf import WeightedProfile
from v2_workshop_tools import generalized_mean, weak_link_capability


def test_harmonic_generalized_mean_is_not_arithmetic() -> None:
    values = [1.0, 2.0, 4.0]
    expected = 3.0 / (1.0 / 1.0 + 1.0 / 2.0 + 1.0 / 4.0)
    got = generalized_mean(values, -1.0)
    assert math.isclose(got, expected, rel_tol=1e-12, abs_tol=1e-12)
    assert not math.isclose(got, sum(values) / len(values), rel_tol=1e-6)


def test_weak_link_capability_penalizes_one_bad_component() -> None:
    strong = weak_link_capability([.9, .9, .9, .9, .9, .9])
    weak = weak_link_capability([.9, .9, .9, .9, .9, .05])
    assert strong > .85
    assert weak < .25
    assert weak < strong * .30


def test_recycling_prior_implies_five_expected_object_lives() -> None:
    config = cfg.V2WorldConfig(pristine_recovery_probability=.60, recycled_recovery_probability=.85)
    assert math.isclose(config.expected_object_lives_per_metal_lineage(), 5.0, rel_tol=1e-12)


def test_v2_chronology_has_positive_mass_classes_at_world_start() -> None:
    active = {
        name: spec
        for name, spec in base.OBJECT_CLASSES.items()
        if int(spec["end"]) <= cfg.DEFAULT_CONFIG.world_start_bc <= int(spec["start"])
    }
    assert active
    assert "ingot" in active
    assert "scrap" in active
    assert all(float(spec["mean_kg"]) > 0.0 for spec in active.values())


def test_v2_workshop_spans_cover_pre_1800_part_of_world() -> None:
    workshops = [
        SimpleNamespace(id=f"W-{i:04d}", start_bc=1800, end_bc=1700)
        for i in range(128)
    ]
    world = SimpleNamespace(workshops=workshops)
    workshop_tools._install_v2_workshop_spans(world, 1300)
    assert all(cfg.DEFAULT_CONFIG.world_end_bc <= w.end_bc < w.start_bc <= cfg.DEFAULT_CONFIG.world_start_bc for w in workshops)
    assert any(w.start_bc > 1800 for w in workshops)
    assert any(w.end_bc < 1200 for w in workshops)


def test_weighted_profile_preserves_joint_covariance() -> None:
    profile = WeightedProfile(("x", "y"), ("x", "y"))
    for x, w in [(1.0, 1.0), (2.0, 2.0), (4.0, 1.5), (7.0, .5)]:
        profile.add({"x": x, "y": 2.0 * x}, w)
    cov = profile.covariance()
    assert cov.shape == (2, 2)
    assert np.all(np.isfinite(cov))
    assert cov[0, 0] > 0
    assert math.isclose(cov[0, 1], 2.0 * cov[0, 0], rel_tol=1e-12, abs_tol=1e-12)
    assert math.isclose(cov[1, 1], 4.0 * cov[0, 0], rel_tol=1e-12, abs_tol=1e-12)


def test_distance_covariance_names_remain_joint() -> None:
    assert "cumulative_metal_distance_km" in cfg.COVARIANCE_MOMENTS
    assert "current_object_distance_km" in cfg.COVARIANCE_MOMENTS
    assert "remelt_count" in cfg.COVARIANCE_MOMENTS
    assert "manufacture_quality" in cfg.COVARIANCE_MOMENTS
