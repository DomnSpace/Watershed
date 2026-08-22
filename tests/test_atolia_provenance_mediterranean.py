import importlib.util
import json
from pathlib import Path


def load_base():
    path = Path("src/atolia/provenance_field.py")
    spec = importlib.util.spec_from_file_location("provenance_field", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_extended():
    base = load_base()
    import sys
    sys.modules["provenance_field"] = base
    path = Path("src/atolia/provenance_field_mediterranean.py")
    spec = importlib.util.spec_from_file_location("provenance_field_mediterranean", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def build_world(seed=1300, workshops=1000):
    module = load_extended()
    hypothesis = json.loads(Path("hypotheses/atolia_atesis_1800_1000_v0.json").read_text())
    world = module.MediterraneanProvenanceWorld(hypothesis, seed=seed)
    world.build(workshop_count=workshops)
    generation = world.generate_archaeological_catalogue(max_materialized=16000)
    selected = world.select_curriculum(300, levels=30)
    return module, world, generation, selected


def test_extended_geography_is_present():
    _, world, _, _ = build_world(seed=1310)
    required = {
        "cyprus", "crete", "aegean_north", "hatti_west", "lower_danube",
        "severn_estuary", "rhone_delta", "upper_rhine", "lower_rhine",
    }
    assert required.issubset(world.nodes)


def test_hidden_checkpoint_mass_balance_is_preserved():
    _, world, generation, selected = build_world(seed=1311)
    report = world.validation_report(selected, generation)
    assert report["checkpoint_mass_balance"]["absolute_error_tonnes"] < 1e-6


def test_peripheral_world_stays_low_incidence_in_300_sample():
    _, world, generation, selected = build_world(seed=1312)
    report = world.validation_report(selected, generation)
    share = report["extended_network"]["peripheral_sample_share"]
    assert 0.03 <= share <= 0.18
    assert report["extended_network"]["tail_to_checkpoint_ratio_truth"] < 0.25


def test_twelve_guilds_exist_and_recur_beyond_core():
    _, world, _, selected = build_world(seed=1313, workshops=1400)
    guild_truth = world.guild_truth()["guilds"]
    assert len(guild_truth) == 12
    assert all(g["total_workshops"] >= 3 for g in guild_truth)
    # Recurrence outside Atolia should exist, but not every guild needs a far-flung branch in every seed.
    assert sum(g["peripheral_workshops"] > 0 for g in guild_truth) >= 6
    represented = {row["truth"].get("guild_id") for row in selected if row["truth"].get("guild_id")}
    assert len(represented) >= 10


def test_guild_and_tail_truth_never_leak_into_player_objects():
    _, world, _, selected = build_world(seed=1314)
    player = [world.player_object(row) for row in selected]
    blob = json.dumps(player)
    for forbidden in (
        "guild_id", "guild_strength", "macro_region", "long_distance_tail",
        "bundle_id", "source_mix", "workshop_id", "lineage_id", "route",
    ):
        assert f'"{forbidden}"' not in blob


def test_level_one_remains_innocent_after_geographic_extension():
    _, _, _, selected = build_world(seed=1315)
    level1 = [row for row in selected if row["curriculum_level"] == 1]
    assert len(level1) == 10
    assert all(row["class"] in {"awl", "bead", "pin"} for row in level1)
