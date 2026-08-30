from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
ATOLIA = ROOT / "src" / "atolia"
if str(ATOLIA) not in sys.path:
    sys.path.insert(0, str(ATOLIA))

import v3_phase07_assemble as assemble
import v3_phase07_manifest as manifest
import v3_phase07_shard as shard


def test_independent_workers_assemble_without_rebuilding_world(tmp_path: Path) -> None:
    hypothesis = json.loads(
        (ROOT / "hypotheses" / "atolia_atesis_1800_1000_v0.json").read_text(encoding="utf-8")
    )
    shard_dir = tmp_path / "shards"
    common = dict(
        hypothesis=hypothesis,
        out_dir=shard_dir,
        chunk_cells=16,
        world_seed=1300,
        workshops=320,
        steps=2,
        nodes=12,
    )
    first = shard.build_one_shard(start=0, stop=16, **common)
    real_population = int(first["population_cells"])
    second = shard.build_one_shard(
        start=16,
        stop=32,
        expected_population=real_population,
        **common,
    )
    assert first["world_build_id"] == second["world_build_id"]
    assert first["shard"]["global_cell_stop"] == second["shard"]["global_cell_start"]

    for result in (first, second):
        path = Path(result["path"])
        assert path.is_file()
        assert result["shard"]["chunk_sha256"]

    # world_build_id intentionally excludes population/chunk storage coordinates,
    # so these independently produced first-two shards can be assembled as a
    # 32-cell noncanonical test product without constructing a world in this step.
    result = assemble.assemble_shards(
        hypothesis,
        shard_dir=shard_dir,
        out_path=tmp_path / "manifest.nc",
        population_cells=32,
        chunk_cells=16,
        world_seed=1300,
        workshops=320,
        steps=2,
        nodes=12,
    )
    assert result["runner"]["assembly_only"] is True
    assert result["runner"]["shards"] == 2
    assert result["roundtrip"]["global_cell_coverage_closed"] is True
    read = manifest.read_manifest(tmp_path / "manifest.nc")
    assert len(read["shards"]) == 2
    assert read["config"]["materialized_cells"] == 32


def test_manifest_world_identity_ignores_chunk_size() -> None:
    base = {
        "product_scope": "canonical-full",
        "world_seed": 7,
        "workshop_count": 3,
        "intensity_steps": 2,
        "target_geography_nodes": 10,
        "hypothesis_sha256": "abc",
        "population_cells": 100,
        "materialized_cells": 100,
        "intensity_model_version": "i",
        "biography_model_version": "b",
        "metallurgy_model_version": "m",
        "workshop_model_version": "w",
        "phase05_model_version": "e",
    }
    a = dict(base, chunk_cells=16)
    b = dict(base, chunk_cells=32)
    assert manifest.world_build_id(a) == manifest.world_build_id(b)
