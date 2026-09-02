from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
ATOLIA = ROOT / "src" / "atolia"
if str(ATOLIA) not in sys.path:
    sys.path.insert(0, str(ATOLIA))

import v3_phase07_assemble_fragments as assemble_fragments
import v3_phase07_canonical as canonical
import v3_phase07_fragment as fragment_io
import v3_phase07_manifest as manifest
import v3_phase07_repair as repair
import v3_phase07_replay_capsule as replay_capsule


NODE = "node-affected"
POOL = "pool-shared"
CANONICAL_RID = "hyr-canonical"
MINORITY_RID = "hyr-minority"


def _record(world_id: str, ordinal: int, *, external: int) -> dict:
    start = ordinal
    stop = ordinal + 1
    row = {
        "world_build_id": world_id,
        "shard_name": f"atolia_v3_canonical_{start:06d}_{stop:06d}.nc",
        "chunk_ordinal": ordinal,
        "global_cell_start": start,
        "global_cell_stop": stop,
        "cell_count": 1,
        "loss_strata": 1,
        "particles": 1,
        "batches": 1,
        "operations": 1,
        "external_exchange_tails": external,
        "deposition_assignments": 1,
        "archaeology_rows": 1,
        "phase01_spine_sha256": f"{ordinal + 1:064x}",
        "phase02_biography_sha256": f"{ordinal + 2:064x}",
        "phase03_metallurgy_sha256": f"{ordinal + 3:064x}",
        "phase04_workshop_sha256": f"{ordinal + 4:064x}",
        "phase05_sha256": f"{ordinal + 5:064x}",
    }
    row["chunk_sha256"] = manifest.chunk_hash(row)
    return row


def _write_fragment(
    path: Path,
    *,
    world_id: str,
    ordinal: int,
    rid: str,
    signature: str,
    context: float,
    external: int,
) -> dict:
    record = _record(world_id, ordinal, external=external)
    payload = {
        "schema": fragment_io.FRAGMENT_SCHEMA,
        "hash_policy": fragment_io.FRAGMENT_HASH_POLICY,
        "world_build_id": world_id,
        "chunk_ordinal": ordinal,
        "global_cell_start": ordinal,
        "global_cell_stop": ordinal + 1,
        "shard_name": record["shard_name"],
        "record": record,
        "flow_summary": {
            "produced": 0.0,
            "circulation_seed": 0.0,
            "transfer_flux": 0.0,
            "return_flux": 0.0,
            "recycle_flux": 0.0,
            "loss_flux": 0.0,
            "retire_flux": 0.0,
            "residual_active": 0.0,
        },
        "static_workshop_signature": "workshop-signature",
        "hydro_realization_signature": signature,
        "deposition_pools": [{
            "deposition_pool_id": POOL,
            "node_id": NODE,
            "date_bc": 1200,
            "mode": "settling",
            "member_count": 1,
            "represented_weight": 1.0,
            "hydro_realization_id": rid,
            "hydro_context_score": context,
        }],
        "tool_use": [],
        "source": {"run_id": "source-run"},
    }
    payload["fragment_sha256"] = fragment_io._fragment_hash(payload)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return fragment_io.read_fragment(path)


def test_repair_projects_minority_fragment_and_embeds_manifest_lineage(tmp_path: Path) -> None:
    hypothesis = json.loads(
        (ROOT / "hypotheses" / "atolia_atesis_1800_1000_v0.json").read_text(encoding="utf-8")
    )
    config = canonical._config(
        hypothesis,
        world_seed=1300,
        workshops=320,
        steps=2,
        nodes=12,
        population_cells=2,
        materialized_cells=2,
        chunk_cells=1,
    )
    world_id = manifest.world_build_id(config)
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    minority = _write_fragment(
        source_dir / "atolia_v3_canonical_000000_000001.fragment.json",
        world_id=world_id,
        ordinal=0,
        rid=MINORITY_RID,
        signature="minority-signature",
        context=0.4,
        external=0,
    )
    _write_fragment(
        source_dir / "atolia_v3_canonical_000001_000002.fragment.json",
        world_id=world_id,
        ordinal=1,
        rid=CANONICAL_RID,
        signature="canonical-signature",
        context=0.8,
        external=1,
    )

    plan = {
        "schema": "test-plan",
        "world_build_id": world_id,
        "observed_variants": {
            "canonical_hydro_realization_id": CANONICAL_RID,
            "minority_hydro_realization_id": MINORITY_RID,
            "fragment_counts": {CANONICAL_RID: 1, MINORITY_RID: 1},
        },
        "observed_boundary": {
            "affected_nodes": [{"node_id": NODE, "minority": 0.4, "canonical": 0.8}],
        },
        "selective_replay": {
            "affected_minority_shard_ordinals": [0],
            "affected_minority_pool_rows": 1,
        },
    }
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    old_pool = dict(minority["deposition_pools"][0])
    canonical_pool = dict(old_pool)
    canonical_pool["hydro_realization_id"] = CANONICAL_RID
    canonical_pool["hydro_context_score"] = 0.8
    capsule = {
        "schema": replay_capsule.SCHEMA,
        "world_build_id": world_id,
        "chunk_ordinal": 0,
        "global_cell_start": 0,
        "global_cell_stop": 1,
        "source_shard": minority["shard_name"],
        "source_chunk_sha256": minority["record"]["chunk_sha256"],
        "source_phase05_sha256": minority["record"]["phase05_sha256"],
        "source_hydro_realization_id": MINORITY_RID,
        "canonical_hydro_realization_id": CANONICAL_RID,
        "affected_particle_count": 1,
        "affected_pool_count": 1,
        "external_actions": {"ADD": 1},
        "external_exchange_count_old": 0,
        "external_exchange_count_delta": 1,
        "external_exchange_count_canonical": 1,
        "minority_context_reconciliation_policy": (
            replay_capsule.MINORITY_CONTEXT_RECONCILIATION_POLICY
        ),
        "replay_rows": [{
            "loss_node_id": NODE,
            "old_hydro_realization_id": MINORITY_RID,
            "canonical_hydro_realization_id": CANONICAL_RID,
            "external_action": "ADD",
            "old_external_row": None,
            "canonical_external_row": {"exchange_id": "exchange-added"},
        }],
        "pool_replacements": [{
            "deposition_pool_id": POOL,
            "old": old_pool,
            "canonical": canonical_pool,
        }],
    }
    capsule_dir = tmp_path / "capsules"
    capsule_dir.mkdir()
    (capsule_dir / "replay-0.json").write_text(
        json.dumps(capsule, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    repaired_dir = tmp_path / "repaired"
    certificate_path = tmp_path / "repair-certificate.json"
    certificate = repair.repair_fragments(
        fragment_dir=source_dir,
        capsule_dir=capsule_dir,
        plan_path=plan_path,
        out_dir=repaired_dir,
        certificate_path=certificate_path,
        population_cells=2,
        chunk_cells=1,
        source_fragment_run_id="fragment-run",
        source_shard_run_id="shard-run",
        cutoff_plan_run_id="plan-run",
        replay_run_id="replay-run",
        mend_code_sha="mend-sha",
    )
    assert certificate["counts"]["repaired_minority_fragments"] == 1
    assert certificate["counts"]["external_exchange_count_delta"] == 1
    repaired = fragment_io.read_fragment(
        repaired_dir / "atolia_v3_canonical_000000_000001.fragment.json"
    )
    assert repaired["record"]["external_exchange_tails"] == 0
    assert repaired["recovery"]["canonical_external_exchange_tails"] == 1
    assert repaired["hydro_realization_signature"] == "canonical-signature"
    assert repaired["deposition_pools"][0] == canonical_pool

    manifest_path = tmp_path / "manifest.nc"
    result = assemble_fragments.assemble_fragments(
        hypothesis,
        fragment_dir=repaired_dir,
        out_path=manifest_path,
        population_cells=2,
        chunk_cells=1,
        world_seed=1300,
        workshops=320,
        steps=2,
        nodes=12,
    )
    assert result["roundtrip"]["recovery_overlay_hash_equal"] is True
    read = manifest.read_manifest(manifest_path)
    assert read["totals"]["external_exchange_tails"] == 2
    assert read["totals"]["hydro_realization_signature"] == "canonical-signature"
    assert read["deposition_pools"][0]["hydro_realization_id"] == CANONICAL_RID
    assert read["deposition_pools"][0]["member_count"] == 2
    assert read["recovery"]["overlay_count"] == 1
    assert read["recovery"]["overlays"][0]["external_exchange_count_delta"] == 1
