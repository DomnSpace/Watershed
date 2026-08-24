from __future__ import annotations

import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import artifact_mobility as mobility
import archaeology_field_world as field_world
import transport_fields as fields


HYPOTHESIS = Path("hypotheses/atolia_atesis_1800_1000_v0.json")


def _world():
    hypothesis = json.loads(HYPOTHESIS.read_text(encoding="utf-8"))
    w = field_world.FieldArchaeologicalObservationWorld(hypothesis, seed=77123)
    w.build(workshop_count=120)
    return w


def test_object_field_mixes_are_normalized_and_distinct():
    sword = fields.object_field_mix("sword", "prestige_long_distance", .5)
    scrap = fields.object_field_mix("scrap", "local_recycling", .5)
    assert abs(sum(sword.values()) - 1.0) < 1e-9
    assert abs(sum(scrap.values()) - 1.0) < 1e-9
    assert sword["danube_sava_morava"] > scrap["danube_sava_morava"]
    assert sword["rhine_north_sea"] > scrap["rhine_north_sea"]
    assert scrap["local_catchment_reuse"] > sword["local_catchment_reuse"]


def test_field_world_preserves_1000_node_carrier_contract():
    w = _world()
    assert len(w.nodes) == 1000
    assert w.geography_report["connectivity"]["connected"]
    assert "physical_geography_version" in w.geography_report


def test_same_bundle_different_object_classes_can_see_different_fields():
    w = _world()
    bundle = next(b for b in w.bundles if b.family in {"prestige_long_distance", "lower_danube_tail", "rhone_atolia_tail"})
    sword = w.mobility_route(bundle, "sword", 1300)
    scrap = w.mobility_route(bundle, "scrap", 1300)
    assert sword.field_mix != scrap.field_mix
    assert sword.nodes[0] == bundle.origin and sword.nodes[-1] == bundle.destination
    assert scrap.nodes[0] == bundle.origin and scrap.nodes[-1] == bundle.destination


def test_field_crossing_metric_is_nonnegative():
    w = _world()
    bundle = next(b for b in w.bundles if len(b.route) > 2)
    route = w.mobility_route(bundle, "sword", 1300)
    assert route.field_crossings >= 0.0
    assert route.physical_crossings >= 0
    assert route.hops == len(route.nodes) - 1
