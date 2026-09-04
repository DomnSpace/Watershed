from __future__ import annotations

"""R17 builder entry that freezes the repaired Phase-07/08 hydro readout.

The canonical hydrology in the shipped runtime is an observed/mended property of
our immutable Phase-07 corpus. Do not regenerate a fresh hydro ensemble during
R17 assembly: process/order drift can produce a new realization identifier even
when the repaired corpus is already authoritative.

The compact corpus can contain adjacent binary64 representations of the same
node context across independently-built shards. We do not average or isclose
those away. Instead we use repair provenance:

* documented repair-boundary nodes take the exact canonical value in the plan;
* otherwise direct RETAIN_CANONICAL_SOURCE shards define the canonical value;
* if multiple direct values exist, a unique exact binary64 mode is selected;
* projected-only fallback is allowed only when it also has a unique exact mode;
* every non-boundary observed value must be within one binary64 ULP of the
  selected canonical value, otherwise the build aborts;
* R17 stores per-node variant/sample/ULP audit columns alongside the frozen
  canonical context.

This preserves the crisp canonical field while retaining evidence of tiny
cross-shard numerical variation instead of silently smoothing it.
"""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from netCDF4 import Dataset

import v3_build_runtime_v3 as core
import v3_phase08_runtime_fragment as phase08


RETAIN = "RETAIN_CANONICAL_SOURCE"
PROJECT = "PROJECT_MINORITY_TO_CANONICAL"


def _same_float(a: Any, b: Any) -> bool:
    return float(a).hex() == float(b).hex()


def _ulp_key(value: Any) -> int:
    """Monotone binary64 key for the non-negative hydro context domain."""
    x = float(value)
    if not np.isfinite(x) or x < 0.0:
        raise RuntimeError(f"invalid hydro context for ULP comparison: {x!r}")
    return int(np.asarray([x], dtype=np.float64).view(np.uint64)[0])


def _ulp_distance(a: Any, b: Any) -> int:
    return abs(_ulp_key(a) - _ulp_key(b))


def _unique_mode(counter: Counter[str], *, label: str) -> float:
    if not counter:
        raise RuntimeError(f"cannot select hydro context mode for empty sample: {label}")
    top = max(counter.values())
    winners = sorted(key for key, count in counter.items() if count == top)
    if len(winners) != 1:
        raise RuntimeError(
            f"hydro context has no unique exact binary64 mode for {label}: "
            f"count={top} winners={winners}"
        )
    return float.fromhex(winners[0])


def _repaired_hydro_context(
    fragments_dir: Path,
    *,
    world_build_id: str,
    world: Any,
    plan: Mapping[str, Any],
) -> tuple[dict[str, float], int, int, dict[str, dict[str, int]]]:
    paths = sorted(Path(fragments_dir).rglob("compact-*.json.gz"))
    if not paths:
        raise RuntimeError("no compact Phase-08 fragments available for canonical hydro readout")

    token_to_node = {
        phase08.anonymous_token(world_build_id, "node", node_id): str(node_id)
        for node_id in world.nodes
    }
    profile_nodes: set[str] = set()
    representative_rows = 0

    all_values: dict[str, Counter[str]] = defaultdict(Counter)
    canonical_values: dict[str, Counter[str]] = defaultdict(Counter)
    projected_values: dict[str, Counter[str]] = defaultdict(Counter)

    for path in paths:
        fragment = core._read_fragment(path)
        if str(fragment["world_build_id"]) != world_build_id:
            raise RuntimeError(f"hydro readout world mismatch in {path}")

        action = str(fragment.get("recovery", {}).get("action", ""))
        if action not in {RETAIN, PROJECT}:
            raise RuntimeError(f"compact fragment has unsupported recovery action {action!r}: {path}")

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
            if not np.isfinite(value) or value < 0.0:
                raise RuntimeError(f"invalid representative hydro context at {node_id}: {value!r}")
            hx = value.hex()
            all_values[node_id][hx] += 1
            if action == RETAIN:
                canonical_values[node_id][hx] += 1
            else:
                projected_values[node_id][hx] += 1
            reps_per_profile[pidx] += 1
            representative_rows += 1

        if any(count <= 0 for count in reps_per_profile):
            missing = sum(count <= 0 for count in reps_per_profile)
            raise RuntimeError(f"compact fragment {path.name} has {missing} profiles without an exact representative")

    affected = {
        str(row["node_id"]): float(row["canonical"])
        for row in plan["observed_boundary"]["affected_nodes"]
    }

    context: dict[str, float] = {}
    audit: dict[str, dict[str, int]] = {}
    for node_id in sorted(profile_nodes):
        if node_id in affected:
            selected = affected[node_id]
            basis = 2  # exact repair-plan canonical boundary
        elif canonical_values[node_id]:
            selected = _unique_mode(canonical_values[node_id], label=f"direct canonical node {node_id}")
            basis = 1  # direct canonical-source exact mode
        else:
            selected = _unique_mode(all_values[node_id], label=f"projected-only node {node_id}")
            basis = 0  # projected-only exact mode fallback

        # Boundary nodes are allowed to contain the documented minority topology
        # values. Everywhere else, a second physical context must not be smuggled
        # through under the guise of floating point drift.
        max_ulp = max(_ulp_distance(selected, float.fromhex(hx)) for hx in all_values[node_id])
        if node_id not in affected and max_ulp > 1:
            detail = sorted((hx, count) for hx, count in all_values[node_id].items())
            raise RuntimeError(
                f"non-boundary hydro node {node_id} has >1 ULP repaired-corpus spread "
                f"around selected {selected.hex()}: max_ulp={max_ulp} variants={detail}"
            )

        # For a documented boundary, direct canonical samples must still agree
        # exactly with the repair plan or be only the same one-ULP arithmetic
        # representation. Larger disagreement means the repair/readout contract
        # is inconsistent and should stop here.
        if node_id in affected and canonical_values[node_id]:
            direct_max_ulp = max(
                _ulp_distance(selected, float.fromhex(hx))
                for hx in canonical_values[node_id]
            )
            if direct_max_ulp > 1:
                raise RuntimeError(
                    f"direct canonical hydro samples disagree with repair plan at {node_id}: "
                    f"plan={selected.hex()} max_direct_ulp={direct_max_ulp} "
                    f"variants={sorted(canonical_values[node_id].items())}"
                )

        context[node_id] = float(selected)
        audit[node_id] = {
            "variant_count": len(all_values[node_id]),
            "canonical_variant_count": len(canonical_values[node_id]),
            "direct_sample_count": sum(canonical_values[node_id].values()),
            "projected_sample_count": sum(projected_values[node_id].values()),
            "max_ulp_distance": int(max_ulp),
            "selection_basis": int(basis),
        }

    missing_profile_nodes = sorted(profile_nodes - set(context))
    if missing_profile_nodes:
        raise RuntimeError(
            f"canonical hydro readout is missing {len(missing_profile_nodes)} profile nodes; "
            f"first={missing_profile_nodes[:8]}"
        )

    return context, len(profile_nodes), representative_rows, audit


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

        context, profile_node_count, representative_count, audit = _repaired_hydro_context(
            fragments_dir,
            world_build_id=str(ds.world_build_id),
            world=world,
            plan=plan,
        )
        node_ids = list(world.nodes)
        values = [float(context.get(str(node), 0.0)) for node in node_ids]
        observed_mask = [int(str(node) in context) for node in node_ids]
        variant_count = [int(audit.get(str(node), {}).get("variant_count", 0)) for node in node_ids]
        canonical_variant_count = [int(audit.get(str(node), {}).get("canonical_variant_count", 0)) for node in node_ids]
        direct_count = [int(audit.get(str(node), {}).get("direct_sample_count", 0)) for node in node_ids]
        projected_count = [int(audit.get(str(node), {}).get("projected_sample_count", 0)) for node in node_ids]
        max_ulp = [int(audit.get(str(node), {}).get("max_ulp_distance", 0)) for node in node_ids]
        selection_basis = [int(audit.get(str(node), {}).get("selection_basis", -1)) for node in node_ids]

        g = ds.createGroup("canonical_hydro")
        g.createDimension("node", len(node_ids))
        core._strvar(g, "node_id", "node", node_ids)
        core._numvar(g, "context", "f8", ("node",), values)
        core._numvar(g, "observed_in_repaired_field", "i1", ("node",), observed_mask)
        core._numvar(g, "exact_variant_count", "i2", ("node",), variant_count)
        core._numvar(g, "direct_canonical_variant_count", "i2", ("node",), canonical_variant_count)
        core._numvar(g, "direct_canonical_sample_count", "i8", ("node",), direct_count)
        core._numvar(g, "projected_sample_count", "i8", ("node",), projected_count)
        core._numvar(g, "max_observed_ulp_distance", "i8", ("node",), max_ulp)
        core._numvar(g, "selection_basis", "i1", ("node",), selection_basis)
        g.source = "phase08-repaired-compact-provenance-resolved-readout"
        g.selection_basis_codes = "0=projected-only-exact-mode;1=direct-canonical-exact-mode;2=repair-plan-boundary"
        g.non_boundary_numeric_spread_policy = "maximum-one-binary64-ULP-no-averaging"
        g.profile_node_count = int(profile_node_count)
        g.representative_rows_validated = int(representative_count)
        g.nodes_with_numeric_variants = int(sum(value > 1 for value in variant_count))
        g.max_non_boundary_ulp_distance = int(max(
            [audit[node]["max_ulp_distance"] for node in audit if node not in affected] or [0]
        )) if False else 0

        # Compute the audit maximum without relying on wrapper-local affected state.
        boundary_nodes = {str(row["node_id"]) for row in plan["observed_boundary"]["affected_nodes"]}
        g.max_non_boundary_ulp_distance = int(max(
            [row["max_ulp_distance"] for node, row in audit.items() if node not in boundary_nodes] or [0]
        ))

        ds.canonical_hydro_realization_id = canonical_id
        ds.minority_hydro_realization_id = minority_id
        ds.fresh_build_hydro_realization_id = "not-rebuilt-r17-freezes-repaired-corpus"
        ds.canonical_hydro_source = "repaired-phase08-field-provenance-resolved-not-fresh-topology"
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
