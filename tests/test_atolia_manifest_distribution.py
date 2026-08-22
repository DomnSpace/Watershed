import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path


def load(name, path):
    p = Path(path)
    spec = importlib.util.spec_from_file_location(name, p)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def build(seed=1321):
    load("provenance_field", "src/atolia/provenance_field.py")
    load("provenance_field_mediterranean", "src/atolia/provenance_field_mediterranean.py")
    load("artifact_manifest", "src/atolia/artifact_manifest.py")
    load("artifact_manifest_temporal", "src/atolia/artifact_manifest_temporal.py")
    builder = load("build_manifest_dataset", "src/atolia/build_manifest_dataset.py")
    manifest = sys.modules["artifact_manifest"]
    temporal = sys.modules["artifact_manifest_temporal"]
    med = sys.modules["provenance_field_mediterranean"]
    slots = [temporal.improved_slot(s) for s in manifest.parse_manifest(Path("catalogues/archaeometallurgy_300_v0.txt"))]
    hypothesis = json.loads(Path("hypotheses/atolia_atesis_1800_1000_v0.json").read_text())
    world = med.MediterraneanProvenanceWorld(hypothesis, seed=seed)
    world.build(workshop_count=800)
    generation = world.generate_archaeological_catalogue(max_materialized=12000)
    compiler = builder.DistributionalManifestCompiler(world, seed=seed)
    records = compiler.compile(slots)
    return builder, slots, world, generation, records


def test_distributional_compiler_preserves_all_manifest_titles():
    _, slots, _, _, records = build()
    assert len(records) == 300
    assert [r["display_name"] for r in records] == [s.title for s in slots]
    assert [r["manifest_index"] for r in records] == list(range(1, 301))


def test_direct_network_sample_remains_core_dominant_but_has_named_tails():
    _, _, _, _, records = build(seed=1322)
    direct = [r for r in records if r["truth"].get("manifest_binding") == "direct_copper_network"]
    regions = Counter(r["truth"].get("macro_region", "other") for r in direct)
    assert regions["atolia_core"] > max((v for k, v in regions.items() if k != "atolia_core"), default=0)
    # Explicitly named provenance examples must survive the core-dominant prior.
    named = {r["display_name"]: r for r in records}
    assert named["Cypriot-type oxhide copper ingot"]["truth"]["macro_region"] == "cyprus"
    assert named["British Late Bronze Age socketed axe with trace-element fingerprint"]["truth"]["macro_region"] == "severn_britain"


def test_direct_sample_uses_multiple_bundles_without_flattening_them():
    _, _, _, _, records = build(seed=1323)
    direct = [r for r in records if r["truth"].get("manifest_binding") == "direct_copper_network"]
    counts = Counter(r["truth"].get("bundle_id") for r in direct)
    assert len(counts) >= 8
    if counts:
        values = sorted(counts.values(), reverse=True)
        assert values[0] > values[-1]  # not a forced equal-per-bundle museum sample


def test_non_direct_periods_never_receive_true_jetbundle_membership():
    _, _, _, _, records = build(seed=1324)
    for row in records:
        if row["truth"].get("manifest_binding") != "direct_copper_network":
            assert "bundle_id" not in row["truth"]
            assert "route" not in row["truth"]
            assert row["truth"].get("direct_atesis_flux_relation") is False
