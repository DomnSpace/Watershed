import importlib.util
import json
import sys
from pathlib import Path

import numpy as np


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, Path(path))
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def build(seed=2301, cap=9000):
    base = load("provenance_field", "src/atolia/provenance_field.py")
    sys.modules["provenance_field"] = base
    med = load("provenance_field_mediterranean", "src/atolia/provenance_field_mediterranean.py")
    sys.modules["provenance_field_mediterranean"] = med
    obs = load("archaeology_observation_v2", "src/atolia/archaeology_observation_v2.py")
    hypothesis = json.loads(Path("hypotheses/atolia_atesis_1800_1000_v0.json").read_text())
    world = obs.ArchaeologicalObservationWorld(hypothesis, seed=seed)
    world.build(workshop_count=900)
    world.rng = np.random.default_rng(seed + 99)
    generation = world.generate_archaeological_catalogue(max_materialized=cap)
    return world, generation


def test_observation_model_separates_archaeological_stages():
    world, generation = build(2302)
    wf = generation["archaeology_waterfall"]
    required = {
        "hidden_production", "circulation_reuse", "loss_deposition",
        "archaeological_survival", "modern_discovery", "recorded_catalogue_expectation",
    }
    assert required.issubset(wf["stages"])
    assert generation["hidden_manufacture_use_events_est"] > generation["hidden_production_events_est"]
    assert generation["catalogued_objects"] <= 9000
    assert world.catalogue_truth


def test_archaeology_enriches_tail_after_circulation():
    _, generation = build(2303)
    stages = generation["archaeology_waterfall"]["stages"]
    circulation = stages["circulation_reuse"]["tail_share"]
    deposition = stages["loss_deposition"]["tail_share"]
    assert deposition > circulation


def test_materialized_truth_contains_observation_probabilities_but_player_projection_does_not():
    world, _ = build(2304)
    row = world.catalogue_truth[0]
    truth = row["truth"]
    for key in (
        "ordinary_return_probability", "exceptional_loss_probability",
        "archaeological_survival_probability", "modern_discovery_probability",
        "route_km", "route_hops", "corridor_crossings", "exceptionality",
    ):
        assert key in truth
    player = world.player_object(row)
    blob = json.dumps(player)
    for key in (
        "ordinary_return_probability", "exceptional_loss_probability",
        "archaeological_survival_probability", "modern_discovery_probability",
        "long_distance_tail", "route_km", "corridor_crossings",
    ):
        assert key not in blob


def test_harmonic_lens_is_preserved_not_reversed():
    p = load("poari_router_v2_check", "src/atolia/poari_career_router.py")
    x = [0.2, 0.5, 0.9]
    assert p.p_mean(x, p=-1) < p.p_mean(x, p=0) < p.p_mean(x, p=1) < p.p_mean(x, p=2)
