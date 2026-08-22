import importlib.util
import json
import sys
from pathlib import Path


def load(name, path):
    p = Path(path)
    spec = importlib.util.spec_from_file_location(name, p)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def build(seed=1311, workshops=900, cap=14000):
    # Load in dependency order so local absolute imports resolve in test collection.
    load("provenance_field", "src/atolia/provenance_field.py")
    load("provenance_field_mediterranean", "src/atolia/provenance_field_mediterranean.py")
    load("artifact_manifest", "src/atolia/artifact_manifest.py")
    temporal = load("artifact_manifest_temporal", "src/atolia/artifact_manifest_temporal.py")
    manifest = sys.modules["artifact_manifest"]
    med = sys.modules["provenance_field_mediterranean"]
    hypothesis = json.loads(Path("hypotheses/atolia_atesis_1800_1000_v0.json").read_text())
    slots = [temporal.improved_slot(slot) for slot in manifest.parse_manifest(Path("catalogues/archaeometallurgy_300_v0.txt"))]
    world = med.MediterraneanProvenanceWorld(hypothesis, seed=seed)
    world.build(workshop_count=workshops)
    generation = world.generate_archaeological_catalogue(max_materialized=cap)
    compiler = temporal.TemporalManifestCompiler(world, seed=seed)
    records = compiler.compile(slots)
    return temporal, slots, world, generation, records


def test_canonical_manifest_has_300_ordered_slots_and_30_levels():
    _, slots, _, _, records = build()
    assert len(slots) == 300
    assert len(records) == 300
    assert [slot.index for slot in slots] == list(range(1, 301))
    assert {slot.level for slot in slots} == set(range(1, 31))
    for slot, row in zip(slots, records):
        assert row["manifest_index"] == slot.index
        assert row["display_name"] == slot.title
        assert row["curriculum_level"] == slot.level


def test_temporal_binding_is_not_falsified():
    temporal, slots, _, _, records = build(seed=1312)
    relations = {row["truth"]["manifest_binding"] for row in records}
    assert "pre_network_precursor" in relations
    assert "direct_copper_network" in relations
    assert "post_network_descendant" in relations or "coeval_parallel_craft" in relations
    for slot, row in zip(slots, records):
        expected = temporal.relation_to_network(slot)
        assert row["truth"]["manifest_binding"] == expected
        if expected != "direct_copper_network":
            assert row["truth"].get("direct_atesis_flux_relation") is False
            assert row["truth"].get("bronze_network_coupling") == 0.0
            assert "bundle_id" not in row["truth"]
            assert "route" not in row["truth"]


def test_named_peripheral_objects_bind_to_requested_regions_when_available():
    _, slots, _, _, records = build(seed=1313)
    by_title = {row["display_name"]: row for row in records}
    checks = {
        "Cypriot-type oxhide copper ingot": "cyprus",
        "Iberian-type copper ingot fragment": "western_mediterranean",
        "Sardinian Bronze Age hoard axe": "western_mediterranean",
        "British Late Bronze Age socketed axe with trace-element fingerprint": "severn_britain",
        "Central European Ösenringbarren": "rhine",
        "Anatolian copper-alloy ingot fragment": "hatti_anatolia",
    }
    for title, region in checks.items():
        assert by_title[title]["truth"]["macro_region"] == region


def test_player_projection_hides_ground_truth():
    temporal, _, _, _, records = build(seed=1314)
    player = [temporal.player_record(row) for row in records]
    blob = json.dumps(player)
    forbidden = [
        "target_tonnes", "bundle_id", "bundle_family", "source_mix", "workshop_id",
        "lineage_id", "guild_id", "guild_strength", "route", "recycle_fraction",
        "bronze_network_coupling", "heritage_strength", "proto_guild_affinity",
    ]
    for key in forbidden:
        assert f'"{key}"' not in blob


def test_manifest_compiler_is_not_just_renaming_one_distribution():
    _, _, _, generation, records = build(seed=1315)
    assert generation["hidden_manufacture_use_events_est"] > 1_000_000
    assert generation["catalogued_objects"] >= 300
    regions = {row["truth"].get("macro_region") for row in records}
    bindings = {row["truth"]["manifest_binding"] for row in records}
    guilds = {row["truth"].get("guild_id") for row in records if row["truth"].get("guild_id")}
    assert "atolia_core" in regions
    assert len(regions) >= 5
    assert len(bindings) >= 3
    assert len(guilds) >= 4
