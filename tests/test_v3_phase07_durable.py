from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
ATOLIA = ROOT / "src" / "atolia"
if str(ATOLIA) not in sys.path:
    sys.path.insert(0, str(ATOLIA))

import v3_phase07_assemble as assemble
import v3_phase07_assemble_fragments as assemble_fragments
import v3_phase07_fragment as fragment_io
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
        fragment_path = Path(result["fragment"]["path"])
        assert path.is_file()
        assert fragment_path.is_file()
        assert result["shard"]["chunk_sha256"]
        checked_fragment = fragment_io.read_fragment(fragment_path)
        assert checked_fragment["record"]["chunk_sha256"] == result["shard"]["chunk_sha256"]

    # world_build_id intentionally excludes population/chunk storage coordinates,
    # so these independently produced first-two shards can be assembled as a
    # 32-cell noncanonical test product without constructing a world in this step.
    raw_result = assemble.assemble_shards(
        hypothesis,
        shard_dir=shard_dir,
        out_path=tmp_path / "manifest-direct.nc",
        population_cells=32,
        chunk_cells=16,
        world_seed=1300,
        workshops=320,
        steps=2,
        nodes=12,
    )
    fragment_result = assemble_fragments.assemble_fragments(
        hypothesis,
        fragment_dir=shard_dir,
        out_path=tmp_path / "manifest-fragments.nc",
        population_cells=32,
        chunk_cells=16,
        world_seed=1300,
        workshops=320,
        steps=2,
        nodes=12,
    )
    assert raw_result["runner"]["assembly_only"] is True
    assert raw_result["runner"]["shards"] == 2
    assert raw_result["roundtrip"]["global_cell_coverage_closed"] is True
    assert fragment_result["runner"]["assembly_only"] is True
    assert fragment_result["runner"]["source_kind"] == "lossless-manifest-fragments"
    assert (
        raw_result["canonical_full"]["phase07_manifest_sha256"]
        == fragment_result["canonical_full"]["phase07_manifest_sha256"]
    )
    read = manifest.read_manifest(tmp_path / "manifest-fragments.nc")
    assert len(read["shards"]) == 2
    assert read["config"]["materialized_cells"] == 32


def test_fragment_hash_rejects_tampering(tmp_path: Path) -> None:
    path = tmp_path / "fragment.json"
    payload = {
        "schema": fragment_io.FRAGMENT_SCHEMA,
        "hash_policy": fragment_io.FRAGMENT_HASH_POLICY,
        "world_build_id": "world",
        "chunk_ordinal": 0,
        "global_cell_start": 0,
        "global_cell_stop": 1,
        "shard_name": "x.nc",
        "record": {
            "world_build_id": "world",
            "shard_name": "x.nc",
            "chunk_ordinal": 0,
            "global_cell_start": 0,
            "global_cell_stop": 1,
            "cell_count": 1,
            "loss_strata": 0,
            "particles": 0,
            "batches": 0,
            "operations": 0,
            "external_exchange_tails": 0,
            "deposition_assignments": 0,
            "archaeology_rows": 0,
            "phase01_spine_sha256": "1",
            "phase02_biography_sha256": "2",
            "phase03_metallurgy_sha256": "3",
            "phase04_workshop_sha256": "4",
            "phase05_sha256": "5",
        },
        "flow_summary": {},
        "static_workshop_signature": "w",
        "hydro_realization_signature": "h",
        "deposition_pools": [],
        "tool_use": [],
        "source": {},
    }
    payload["record"]["chunk_sha256"] = manifest.chunk_hash(payload["record"])
    payload["fragment_sha256"] = fragment_io._fragment_hash(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")
    fragment_io.read_fragment(path)

    payload["global_cell_stop"] = 2
    path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        fragment_io.read_fragment(path)
    except RuntimeError as exc:
        assert "fragment hash mismatch" in str(exc)
    else:
        raise AssertionError("tampered fragment unexpectedly validated")


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


def test_fragment_preflight_rejects_incomplete_set(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="expected 2 fragments, found 0"):
        assemble_fragments.preflight_fragments(
            tmp_path,
            population_cells=2,
            chunk_cells=1,
        )


def test_pool_collision_diagnostic_reports_exact_pair(capsys: pytest.CaptureFixture[str]) -> None:
    aggregate: dict[str, dict[str, object]] = {}
    origins: dict[str, tuple[dict[str, object], dict[str, object]]] = {}
    first_fragment = {
        "chunk_ordinal": 12,
        "global_cell_start": 768,
        "global_cell_stop": 832,
    }
    second_fragment = {
        "chunk_ordinal": 13,
        "global_cell_start": 832,
        "global_cell_stop": 896,
    }
    first = {
        "deposition_pool_id": "pool-collision",
        "node_id": "node-a",
        "date_bc": 1200,
        "mode": "settling",
        "member_count": 2,
        "represented_weight": 3.5,
        "hydro_realization_id": "hydro-1",
        "hydro_context_score": 0.25,
    }
    second = dict(first, node_id="node-b", member_count=1, represented_weight=2.0)

    assemble_fragments._merge_pool_with_diagnostics(
        aggregate,
        origins,
        first,
        path=Path("atolia_v3_canonical_000768_000832.fragment.json"),
        frag=first_fragment,
    )
    with pytest.raises(RuntimeError, match="differing fields: node_id"):
        assemble_fragments._merge_pool_with_diagnostics(
            aggregate,
            origins,
            second,
            path=Path("atolia_v3_canonical_000832_000896.fragment.json"),
            frag=second_fragment,
        )

    stderr = capsys.readouterr().err
    assert "PHASE07_DEPOSITION_POOL_COLLISION" in stderr
    assert '"node_id": "node-a"' in stderr
    assert '"node_id": "node-b"' in stderr
    assert '"chunk_ordinal": 12' in stderr
    assert '"chunk_ordinal": 13' in stderr
    assert "atolia_v3_canonical_000768_000832.fragment.json" in stderr
    assert "atolia_v3_canonical_000832_000896.fragment.json" in stderr
