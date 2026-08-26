from __future__ import annotations

import math
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import v2_config as cfg
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
