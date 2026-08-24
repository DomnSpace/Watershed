from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ATOLIA = ROOT / "src" / "atolia"
if str(ATOLIA) not in sys.path:
    sys.path.insert(0, str(ATOLIA))

import archaeology_dense_world as dense_world
import provenance_field as base
import provenance_field_mediterranean as med


HYPOTHESIS = ROOT / "hypotheses" / "atolia_atesis_1800_1000_v0.json"


def build_world(workshops: int = 160):
    hypothesis = json.loads(HYPOTHESIS.read_text(encoding="utf-8"))
    world = dense_world.DenseArchaeologicalObservationWorld(hypothesis, seed=1300)
    world.build(workshop_count=workshops)
    return world


def test_dense_world_has_exactly_1000_nodes_and_preserves_gateways():
    world = build_world()
    assert len(world.nodes) == 1000
    required = {
        "upper_atesis", "rovereto_gate", "verona_plain_gate", "frattesina",
        "rhone_delta", "upper_rhine", "severn_estuary", "great_orme_source",
        "sardinia", "sicily", "crete", "cyprus", "hatti_west", "lower_danube",
    }
    assert required <= set(world.nodes)
    assert world.nodes["hatti_west"].label == "Arzawa / western Anatolian interface"


def test_dense_world_is_connected_and_has_no_duplicate_ids():
    world = build_world()
    report = world.geography_report["connectivity"]
    assert report["connected"]
    assert report["reachable"] == 1000
    assert report["canonical_missing"] == []
    assert report["isolated_nodes"] == []
    assert len(world.nodes) == len(set(world.nodes))


def test_dense_edges_are_localized_and_cost_is_preserved():
    world = build_world()
    report = world.geography_report
    assert report["final_edges"] > report["original_edges"]
    assert report["median_segment_km"] < 80.0
    assert report["p95_segment_km"] < 180.0
    for stat in report["edge_stats"]:
        assert abs(float(stat["cost_error"])) < 0.03


def test_existing_bundle_endpoints_and_routes_survive_densification():
    world = build_world()
    for bundle in world.bundles:
        assert bundle.origin in world.nodes
        assert bundle.destination in world.nodes
        assert bundle.route[0] == bundle.origin
        assert bundle.route[-1] == bundle.destination
        assert len(bundle.route) >= 2
        for a, b in zip(bundle.route[:-1], bundle.route[1:]):
            assert any(
                (edge.a == a and edge.b == b)
                or (not edge.directed and edge.a == b and edge.b == a)
                for edge in world.edges
            )


def test_dense_nodes_receive_corridor_regions():
    world = build_world()
    dense_ids = [node_id for node_id in world.nodes if node_id.startswith("dg_")]
    assert len(dense_ids) > 900
    assert all(node_id in med.REGION_BY_NODE for node_id in dense_ids)
    assert len(set(med.REGION_BY_NODE[node_id] for node_id in dense_ids)) >= 8
