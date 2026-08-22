import importlib.util
import json
from pathlib import Path


def load_module():
    path = Path("src/atolia/provenance_field.py")
    spec = importlib.util.spec_from_file_location("atolia_provenance", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def build_world(seed=1300, workshops=700):
    module = load_module()
    hypothesis = json.loads(Path("hypotheses/atolia_atesis_1800_1000_v0.json").read_text())
    world = module.ProvenanceWorld(hypothesis, seed=seed)
    world.build(workshop_count=workshops)
    generation = world.generate_archaeological_catalogue(max_materialized=12000)
    selected = world.select_curriculum(300, levels=30)
    return module, world, generation, selected


def test_hidden_mass_balance_and_sample_size():
    _, world, generation, selected = build_world()
    report = world.validation_report(selected, generation)
    assert report["checkpoint_mass_balance"]["absolute_error_tonnes"] < 1e-6
    assert report["selected_objects"] == 300
    assert len({row["curriculum_level"] for row in selected}) == 30
    assert all(sum(row["curriculum_level"] == level for row in selected) == 10 for level in range(1, 31))


def test_player_export_does_not_leak_hidden_network_truth():
    _, world, _, selected = build_world(seed=1301)
    forbidden = {
        "target_tonnes",
        "bundle_id",
        "bundle_family",
        "source_mix",
        "workshop_id",
        "lineage_id",
        "route",
        "recycle_fraction",
    }
    player = [world.player_object(row) for row in selected]
    blob = json.dumps(player)
    for key in forbidden:
        assert f'"{key}"' not in blob


def test_catalogue_originates_from_large_hidden_population():
    _, _, generation, selected = build_world(seed=1302)
    assert generation["hidden_manufacture_use_events_est"] > 1_000_000
    assert generation["catalogued_objects"] >= 300
    assert len(selected) == 300


def test_curriculum_starts_simple_and_finishes_harder_on_average():
    _, _, _, selected = build_world(seed=1303)
    level1 = [row for row in selected if row["curriculum_level"] == 1]
    level30 = [row for row in selected if row["curriculum_level"] == 30]
    assert all(row["class"] in {"awl", "bead", "pin"} for row in level1)
    mean1 = sum(row["truth"]["complexity"] for row in level1) / len(level1)
    mean30 = sum(row["truth"]["complexity"] for row in level30) / len(level30)
    assert mean30 > mean1
