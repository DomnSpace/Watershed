import importlib.util
import json
from pathlib import Path


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def modules():
    root = Path("src/atolia")
    sampler = load("procedural_sampler_test", root / "procedural_sampler.py")
    contract = load("curriculum_contract_test", root / "curriculum_contract_v1.py")
    return sampler, contract


def build(seed=20261300, workshops=650, cap=9000):
    sampler, contract = modules()
    hypothesis = Path("hypotheses/atolia_atesis_1800_1000_v0.json")
    h = json.loads(hypothesis.read_text())
    seeds = sampler.SeedBundle.from_master(seed)
    world = sampler.med.MediterraneanProvenanceWorld(h, seed=seeds.world_seed)
    world.build(workshop_count=workshops)
    world.rng = sampler.np.random.default_rng(seeds.archaeology_seed)
    generation = world.generate_archaeological_catalogue(max_materialized=cap)
    career = sampler.ProceduralCareerSampler(world, seeds, contract.build_contract())
    career.prepare_candidates()
    player = career.sample()
    analyses = career.player_analyses()
    truth = career.debug_truth()
    return sampler, career, generation, player, analyses, truth


def test_contract_is_exactly_30_by_10():
    _, contract = modules()
    slots = contract.build_contract()
    assert len(slots) == 300
    assert {slot.level for slot in slots} == set(range(1, 31))
    assert all(sum(slot.level == level for slot in slots) == 10 for level in range(1, 31))


def test_same_master_seed_is_reproducible():
    _, career_a, _, player_a, analyses_a, _ = build(seed=77777)
    _, career_b, _, player_b, analyses_b, _ = build(seed=77777)
    ids_a = [row["object_id"] for row in player_a]
    ids_b = [row["object_id"] for row in player_b]
    assert ids_a == ids_b
    assert analyses_a == analyses_b
    assert career_a.seeds == career_b.seeds


def test_different_master_seed_changes_career():
    _, _, _, player_a, _, _ = build(seed=12001)
    _, _, _, player_b, _, _ = build(seed=12002)
    ids_a = [row["object_id"] for row in player_a]
    ids_b = [row["object_id"] for row in player_b]
    assert ids_a != ids_b
    assert sum(a != b for a, b in zip(ids_a, ids_b)) > 30


def test_level_one_stays_low_spoiler_and_mundane():
    _, career, _, player, _, _ = build(seed=20261301)
    level1_candidates = [career.selected_by_slot[i] for i in range(1, 11)]
    assert max(candidate.spoiler for candidate in level1_candidates) <= 0.35
    assert all(row["level"] == 1 for row in player[:10])
    assert all("guild" not in json.dumps(row).lower() for row in player[:10])
    assert all("jetbundle" not in json.dumps(row).lower() for row in player[:10])


def test_player_exports_do_not_leak_ground_truth():
    _, _, _, player, analyses, _ = build(seed=20261302)
    blob = json.dumps({"objects": player, "analyses": analyses})
    forbidden = [
        "target_tonnes", "bundle_id", "bundle_family", "source_mix", "guild_id",
        "guild_events", "guild_affinity_vector", "workshop_id", "lineage_id", "route",
        "recycle_fraction", "spoiler_score", "network_information",
    ]
    for key in forbidden:
        assert f'"{key}"' not in blob


def test_background_cases_are_present_but_not_everything():
    _, career, _, _, _, _ = build(seed=20261303)
    n = sum(candidate.background for candidate in career.selected)
    assert 10 <= n <= 220


def test_guild_events_are_multi_operation_and_twelve_dimensional():
    sampler, career, _, _, _, truth = build(seed=20261304)
    assert all(set(row["truth"]["guild_event_vector"]) == set(sampler.guild_model.GUILD_PROFILES) for row in truth)
    assert any(len(row["truth"]["guild_events"]) >= 3 for row in truth)
    represented = {
        guild_id for row in truth
        for guild_id, value in row["truth"]["guild_event_vector"].items()
        if value >= .25
    }
    assert len(represented) >= 7


def test_measurements_are_stable_not_rerolled():
    _, career, _, _, analyses_a, _ = build(seed=20261305)
    analyses_b = career.player_analyses()
    assert analyses_a == analyses_b


def test_catalogue_still_originates_from_large_hidden_population():
    _, _, generation, _, _, _ = build(seed=20261306)
    assert generation["hidden_manufacture_use_events_est"] > 1_000_000
    assert generation["catalogued_objects"] >= 300


def test_career_keeps_more_than_one_bundle_and_source():
    _, career, _, _, _, _ = build(seed=20261307)
    bundles = {candidate.bundle_id for candidate in career.selected if candidate.bundle_id}
    sources = {candidate.dominant_source for candidate in career.selected}
    assert len(bundles) >= 8
    assert len(sources) >= 3


def test_late_levels_carry_more_network_information_than_early_levels_on_average():
    _, career, _, _, _, _ = build(seed=20261308)
    early = [career.selected_by_slot[i].network_information for i in range(1, 51)]
    late = [career.selected_by_slot[i].network_information for i in range(251, 301)]
    assert sum(late) / len(late) > sum(early) / len(early)
