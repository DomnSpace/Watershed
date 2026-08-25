from __future__ import annotations

from dataclasses import dataclass

import numpy as np

import provenance_field as provenance
import release_candidate_invariants as release


@dataclass
class FakeBundle:
    id: str = "B-test"
    family: str = "regional_circulation"
    origin: str = "a"
    destination: str = "b"
    source_mix: dict[str, float] = None
    recycle_mean: float = 0.2
    flux_tonnes: dict[int, float] = None

    def __post_init__(self):
        if self.source_mix is None:
            self.source_mix = {"source_a": 1.0}
        if self.flux_tonnes is None:
            self.flux_tonnes = {1200: 10.0}


class FakeWorld:
    def __init__(self):
        self.bundles = [FakeBundle()]
        self.time_slices = [1200]

    def _class_weights(self, date_bc, bundle):
        # Count shares, already normalized by the active world.
        return ["dagger", "axe"], np.asarray([0.25, 0.75], dtype=float)


def test_generalized_mean_preserves_minus1_0_1_2_order():
    values = [.18, .42, .91]
    weights = [.2, .3, .5]
    hm = release.generalized_mean(values, weights, -1.0)
    gm = release.generalized_mean(values, weights, 0.0)
    am = release.generalized_mean(values, weights, 1.0)
    qm = release.generalized_mean(values, weights, 2.0)
    assert 0.0 < hm < gm < am < qm <= 1.0


def test_harmonic_mean_retains_weak_link_drag():
    balanced = release.generalized_mean([.55, .55], [.5, .5], -1.0)
    weak = release.generalized_mean([.95, .15], [.5, .5], -1.0)
    assert balanced > weak
    assert weak < .30


def test_production_transform_conserves_bundle_metal_mass():
    world = FakeWorld()
    cells = release.mass_conserving_production_cells(world)
    represented = sum(
        c.production_intensity * float(provenance.OBJECT_CLASSES[c.object_class]["mean_kg"])
        for c in cells
    )
    expected = 10.0 * 1000.0 * 0.48
    assert abs(represented - expected) < 1e-8
    assert abs(release.production_mass_error(world)) < 1e-8


def test_production_event_shares_follow_authoritative_count_weights():
    world = FakeWorld()
    cells = release.mass_conserving_production_cells(world)
    total = sum(c.production_intensity for c in cells)
    shares = {c.object_class: c.production_intensity / total for c in cells}
    assert abs(shares["dagger"] - .25) < 1e-12
    assert abs(shares["axe"] - .75) < 1e-12
