from __future__ import annotations

"""R17 builder entry that freezes the repaired Phase-07/08 hydro readout.

The canonical hydrology in the shipped runtime is an observed/mended property of
our immutable Phase-07 corpus.  Do not regenerate a fresh hydro ensemble during
R17 assembly: process/order drift can produce a new realization identifier even
when the repaired corpus is already authoritative.

This wrapper keeps the existing R17 builder unchanged except for its hydro writer.
It derives exact node context values from the *actual representative lineage rows*
in the 580 repaired compact Phase-08 fragments, validates the six documented
canonical boundary overrides, and writes that frozen readout into R17.
"""

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from netCDF4 import Dataset

import v3_build_runtime_v3 as core
import v3_phase08_runtime_fragment as phase08


def _same_float(a: Any, b: Any) -> bool:
    return float(a).hex() == float(b).hex()


def _repaired_hydro_context(
    fragments_dir: Path,
    *,
    world_build_id: str,
    world: Any,
    plan: Mapping[str, Any],
) -> tuple[dict[str, float], int, int]:
    paths = sorted(Path(fragments_dir).rglob("compact-*.json.gz"))
    if not paths:
        raise RuntimeError("no compact Phase-08 fragments available for canonical hydro readout")

    token_to_node = {
        phase08.anonymous_token(world_build_id, "node", node_id): str(node_id)
        for node_id in world.nodes
    }
    context: dict[str, float] = {}
    profile_nodes: set[str] = set()
    representative_rows = 0

    for path in paths:
        fragment = core._read_fragment(path)
        if str(fragment["world_build_id"]) != world_build_id:
            raise RuntimeError(f"hydro readout world mismatch in {path}")

        profile_columns = {
            name: i for i, name in enumerate(fragment["columns"]["profile"])
        }
        representative_columns = {
            name: i for i, name in enumerate(fragment["columns"]["representative"])
        }
        if "hydro_context_score" not in representative_columns:
            raise RuntimeError(f"compact fragment lacks exact representative hydro context: {path}")

        node_dictionary = list(fragment["dictionary"]["node"])
        profile_node: list[str] = []
        for row in fragment["profiles"]:
            token = str(node_dictionary[int(row[profile_columns["loss_node"]])])
            raw = token_to_node.get(token)
            if raw is None:
                raise RuntimeError(f"profile node token does not resolve in frozen world: {token}")
            profile_node.append(raw)
            profile_nodes.add(raw)

        reps_per_profile = [0] * len(profile_node)
        for row in fragment["representatives"]:
            pidx = int(row[representative_columns["profile"]])
            if pidx < 0 or pidx >= len(profile_node):
                raise RuntimeError(f"representative profile index outside fragment bounds: {pidx}")
            node_id = profile_node[pidx]
            value = float(row[representative_columns["hydro_context_score"]])
            reps_per_profile[pidx] += 1
            representative_rows += 1
            previous = context.get(node_id)
            if previous is None:
                context[node_id] = value
            elif not _same_float(previous, value):
                raise RuntimeError(
                    f"repaired compact corpus contains two exact hydro contexts for node {node_id}: "
                    f"{previous.hex()} vs {value.hex()}"
                )

        if any(count <= 0 for count in reps_per_profile):
            missing = sum(count <= 0 for count in reps_per_profile)
            raise RuntimeError(f"compact fragment {path.name} has {missing} profiles without an exact representative")

    # The repair plan is authoritative for the observed minority/canonical boundary.
    # The compact extraction should already contain these canonical values; require
    # agreement rather than silently replacing a disagreement.
    for row in plan["observed_boundary"]["affected_nodes"]:
        node_id = str(row["node_id"])
        canonical = float(row["canonical"])
        observed = context.get(node_id)
        if observed is not None and not _same_float(observed, canonical):
            raise RuntimeError(
                f"repaired compact hydro/context mismatch at documented boundary node {node_id}: "
                f"compact={observed.hex()} plan={canonical.hex()}"
            )
        context[node_id] = canonical

    missing_profile_nodes = sorted(profile_nodes - set(context))
    if missing_profile_nodes:
        raise RuntimeError(
            f"canonical hydro readout is missing {len(missing_profile_nodes)} profile nodes; "
            f"first={missing_profile_nodes[:8]}"
        )

    return context, len(profile_nodes), representative_rows


def _make_hydro_writer(fragments_dir: Path):
    def _write_hydro(
        ds: Dataset,
        world: Any,
        plan: Mapping[str, Any],
        certificate: Mapping[str, Any],
    ) -> dict[str, float]:
        canonical_id = str(plan["observed_variants"]["canonical_hydro_realization_id"])
        minority_id = str(plan["observed_variants"]["minority_hydro_realization_id"])
        if canonical_id != str(certificate["canonical_hydro_realization_id"]):
            raise RuntimeError("cutoff plan/certificate disagree on canonical hydro realization")

        context, profile_node_count, representative_count = _repaired_hydro_context(
            fragments_dir,
            world_build_id=str(ds.world_build_id),
            world=world,
            plan=plan,
        )
        node_ids = list(world.nodes)
        values = [float(context.get(str(node), 0.0)) for node in node_ids]
        observed_mask = [int(str(node) in context) for node in node_ids]

        g = ds.createGroup("canonical_hydro")
        g.createDimension("node", len(node_ids))
        core._strvar(g, "node_id", "node", node_ids)
        core._numvar(g, "context", "f8", ("node",), values)
        core._numvar(g, "observed_in_repaired_field", "i1", ("node",), observed_mask)
        g.source = "phase08-repaired-compact-exact-representative-readout"
        g.profile_node_count = int(profile_node_count)
        g.representative_rows_validated = int(representative_count)

        ds.canonical_hydro_realization_id = canonical_id
        ds.minority_hydro_realization_id = minority_id
        ds.fresh_build_hydro_realization_id = "not-rebuilt-r17-freezes-repaired-corpus"
        ds.canonical_hydro_source = "repaired-phase08-field-not-fresh-topology"
        return {str(node): float(value) for node, value in zip(node_ids, values)}

    return _write_hydro


def build_runtime(**kwargs: Any) -> dict[str, Any]:
    fragments_dir = Path(kwargs["fragments_dir"])
    original = core._write_hydro
    core._write_hydro = _make_hydro_writer(fragments_dir)
    try:
        return core.build_runtime(**kwargs)
    finally:
        core._write_hydro = original


def main() -> None:
    parser = argparse.ArgumentParser(description="Build R17 using repaired Phase-08 hydro readout")
    parser.add_argument("--fragments", required=True, type=Path)
    parser.add_argument("--repair-certificate", required=True, type=Path)
    parser.add_argument("--cutoff-plan", required=True, type=Path)
    parser.add_argument("--hypothesis", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--expected-shards", type=int, default=580)
    parser.add_argument("--population-cells", type=int, default=37100)
    args = parser.parse_args()
    result = build_runtime(
        fragments_dir=args.fragments,
        cutoff_plan_path=args.cutoff_plan,
        repair_certificate_path=args.repair_certificate,
        hypothesis_path=args.hypothesis,
        out_path=args.out,
        expected_shards=args.expected_shards,
        population_cells=args.population_cells,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
