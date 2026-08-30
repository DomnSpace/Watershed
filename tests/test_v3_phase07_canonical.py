from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
ATOLIA = ROOT / "src" / "atolia"
if str(ATOLIA) not in sys.path:
    sys.path.insert(0, str(ATOLIA))

import v3_biography_netcdf
import v3_netcdf
import v3_phase07_canonical as canonical
import v3_phase07_manifest as manifest


def _base_config(chunk_cells: int) -> dict:
    return {
        "product_scope": "verification-prefix",
        "world_seed": 20260824,
        "workshop_count": 3200,
        "intensity_steps": 28,
        "target_geography_nodes": 1000,
        "hypothesis_sha256": "a" * 64,
        "population_cells": 37100,
        "materialized_cells": 64,
        "chunk_cells": chunk_cells,
        "intensity_model_version": "intensity-circulation-v1",
        "biography_model_version": "atolia-v3-metal-biography-v1",
        "metallurgy_model_version": "atolia-v3-source-metallurgy-v1",
        "workshop_model_version": "atolia-v3-workshop-guild-tools-v1",
        "phase05_model_version": "atolia-v3-hydro-exchange-deposition-v1",
    }


def test_world_build_id_is_independent_of_chunk_size() -> None:
    a = _base_config(32)
    b = _base_config(2048)
    assert manifest.world_build_id(a) == manifest.world_build_id(b)


def test_chunk_hash_changes_with_scientific_phase_hash() -> None:
    row = {
        "world_build_id": "w" * 64,
        "chunk_ordinal": 0,
        "global_cell_start": 0,
        "global_cell_stop": 32,
        "cell_count": 32,
        "loss_strata": 96,
        "phase01_spine_sha256": "1" * 64,
        "phase02_biography_sha256": "2" * 64,
        "phase03_metallurgy_sha256": "3" * 64,
        "phase04_workshop_sha256": "4" * 64,
        "phase05_sha256": "5" * 64,
    }
    first = manifest.chunk_hash(row)
    row["phase05_sha256"] = "6" * 64
    assert manifest.chunk_hash(row) != first


def test_real_two_shard_prefix_preserves_global_identity_and_resumes(tmp_path: Path) -> None:
    hypothesis = json.loads((ROOT / "hypotheses" / "atolia_atesis_1800_1000_v0.json").read_text(encoding="utf-8"))
    out_dir = tmp_path / "canonical"
    first = canonical.build_canonical(
        hypothesis,
        out_dir=out_dir,
        world_seed=1300,
        workshops=320,
        steps=2,
        nodes=12,
        chunk_cells=32,
        max_cells=64,
        resume=True,
    )
    assert first["latest_phase"] == manifest.V3_PHASE07_PHASE
    assert first["canonical_full"]["product_scope"] == "verification-prefix"
    assert first["canonical_full"]["shards"] == 2
    assert all(first["roundtrip"].values())

    read = manifest.read_manifest(out_dir / "manifest.nc")
    assert read["phase07_manifest_sha256"] == first["canonical_full"]["phase07_manifest_sha256"]
    assert sum(row["cell_count"] for row in read["shards"]) == 64
    assert sum(row["member_count"] for row in read["deposition_pools"]) == read["totals"]["deposition_assignments"]

    expected_start = 0
    for shard in read["shards"]:
        path = out_dir / "shards" / shard["shard_name"]
        spine = v3_netcdf.read_spine_master(path)
        bio = v3_biography_netcdf.read_biography(path)
        indices = [row["cell_index"] for row in spine["cells"]]
        assert indices == list(range(shard["global_cell_start"], shard["global_cell_stop"]))
        assert shard["global_cell_start"] == expected_start
        expected_start = shard["global_cell_stop"]
        assert all(
            shard["global_cell_start"] <= row["production_cell_index"] < shard["global_cell_stop"]
            for row in bio["particles"]
        )
    assert expected_start == 64

    second = canonical.build_canonical(
        hypothesis,
        out_dir=out_dir,
        world_seed=1300,
        workshops=320,
        steps=2,
        nodes=12,
        chunk_cells=32,
        max_cells=64,
        resume=True,
    )
    assert second["canonical_full"]["phase07_manifest_sha256"] == first["canonical_full"]["phase07_manifest_sha256"]
    assert second["canonical_full"]["world_build_id"] == first["canonical_full"]["world_build_id"]
