from __future__ import annotations

"""R17 builder entry that freezes the repaired Phase-07/08 readout.

The shipped runtime is a frozen readout of the repaired corpus.  It must not
regenerate scientific state at assembly time and then merely hope that today's
process reproduces the historical build bit-for-bit.

Two repaired boundaries are handled here:

* canonical hydrology is selected from the observed Phase-07 realization
  provenance and the repaired Phase-08 representatives;
* the 37,100 production cells are hydrated directly from the exact compact
  Phase-08 cell rows and source weights.  The freshly-built static world is used
  only to resolve anonymous node/bundle/source tokens and provide the interpreter
  graph; it is not allowed to redraw the production population.

For hydrology there are two different things that must not be conflated:

* *topology identity* is the observed Phase-07 hydro realization identity and is
  resolved by the repair certificate / cutoff plan;
* *numeric representation* is the binary64 node context computed as a mean of
  realized-edge navigabilities. Independently-built shards can contain several
  exact binary64 representations for the same node inside one topology.

R17 therefore resolves hydro as follows, without averaging and without isclose:

* documented repair-boundary nodes take the exact canonical value in the plan;
* otherwise direct RETAIN_CANONICAL_SOURCE shards define the canonical value;
* if multiple exact direct values exist, a unique exact binary64 mode is selected;
* projected-only fallback is allowed only when it also has a unique exact mode;
* all alternative exact values are retained as per-node audit counts / ULP spread;
* a real topology disagreement is still a hard error because every fragment must
  carry one of the repair-plan actions tied to the observed canonical/minority pair.

This keeps one crisp canonical field while preserving the numerical forensics
that produced it.
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


def _inverse_tokens(world_build_id: str, kind: str, raw_ids: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw_id in raw_ids:
        raw = str(raw_id)
        token = phase08.anonymous_token(world_build_id, kind, raw)
        previous = out.get(token)
        if previous is not None and previous != raw:
            raise RuntimeError(
                f"anonymous {kind} token collision while hydrating repaired R17 cells: "
                f"{token} -> {previous!r}/{raw!r}"
            )
        out[token] = raw
    return out


def _repaired_production_cells(
    fragments_dir: Path,
    *,
    world_build_id: str,
    world: Any,
    expected_shards: int,
    population_cells: int,
) -> list[Any]:
    """Hydrate the exact Phase-08 production-cell population.

    Compact Phase-08 deliberately stores anonymous bundle/node/source tokens but
    keeps the cell scalar values and source weights as binary64 JSON numbers.  We
    resolve those tokens against the static world and construct ProductionCell
    objects from the repaired corpus itself.  No call to intensity.production_cells
    is allowed on this path.
    """
    paths = list(Path(fragments_dir).rglob("compact-*.json.gz"))
    by_ordinal: dict[int, Path] = {}
    for path in paths:
        ordinal = int(path.name.removeprefix("compact-").removesuffix(".json.gz"))
        if ordinal in by_ordinal:
            raise RuntimeError(f"duplicate compact ordinal while hydrating cells: {ordinal}")
        by_ordinal[ordinal] = path
    if sorted(by_ordinal) != list(range(expected_shards)):
        raise RuntimeError(
            f"repaired production-cell hydration expected ordinals 0..{expected_shards - 1}; "
            f"found {len(by_ordinal)} fragments"
        )

    token_to_bundle = _inverse_tokens(
        world_build_id, "bundle", [str(bundle.id) for bundle in world.bundles]
    )
    token_to_node = _inverse_tokens(
        world_build_id, "node", [str(node_id) for node_id in world.nodes]
    )
    token_to_source = _inverse_tokens(
        world_build_id, "source", [str(source_id) for source_id in world.sources]
    )

    cells: list[Any | None] = [None] * int(population_cells)
    for ordinal in range(expected_shards):
        fragment = core._read_fragment(by_ordinal[ordinal])
        if str(fragment["world_build_id"]) != world_build_id:
            raise RuntimeError(f"production-cell world mismatch at compact ordinal {ordinal}")
        start = int(fragment["global_cell_start"])
        stop = int(fragment["global_cell_stop"])
        if start != ordinal * 64 or stop != min(population_cells, start + 64):
            raise RuntimeError(
                f"unexpected production-cell interval {start}:{stop} at compact ordinal {ordinal}"
            )

        d = fragment["dictionary"]
        ccols = {name: i for i, name in enumerate(fragment["columns"]["cell"])}
        scols = {name: i for i, name in enumerate(fragment["columns"]["cell_source"])}
        if len(fragment["cells"]) != stop - start:
            raise RuntimeError(f"compact cell count mismatch at ordinal {ordinal}")

        source_mix_by_local: dict[int, dict[str, float]] = defaultdict(dict)
        for source_row in fragment["cell_sources"]:
            local = int(source_row[scols["cell"]])
            if local < 0 or local >= stop - start:
                raise RuntimeError(
                    f"cell-source row references local cell {local} outside ordinal {ordinal}"
                )
            token = str(d["source"][int(source_row[scols["source"]])])
            raw_source = token_to_source.get(token)
            if raw_source is None:
                raise RuntimeError(
                    f"repaired cell source token does not resolve in frozen world: {token}"
                )
            if raw_source in source_mix_by_local[local]:
                raise RuntimeError(
                    f"duplicate repaired source {raw_source} for ordinal {ordinal} local cell {local}"
                )
            source_mix_by_local[local][raw_source] = float(source_row[scols["weight"]])

        for local, row in enumerate(fragment["cells"]):
            global_cell = int(row[ccols["global_cell_index"]])
            if global_cell != start + local:
                raise RuntimeError(
                    f"compact production-cell ordering mismatch at ordinal {ordinal}: "
                    f"local={local} global={global_cell} expected={start + local}"
                )

            bundle_token = str(d["bundle"][int(row[ccols["bundle"]])])
            origin_token = str(d["node"][int(row[ccols["origin_node"]])])
            destination_token = str(d["node"][int(row[ccols["destination_node"]])])
            bundle_id = token_to_bundle.get(bundle_token)
            origin = token_to_node.get(origin_token)
            destination = token_to_node.get(destination_token)
            if bundle_id is None:
                raise RuntimeError(f"repaired bundle token does not resolve in frozen world: {bundle_token}")
            if origin is None or destination is None:
                raise RuntimeError(
                    f"repaired node token does not resolve in frozen world for cell {global_cell}: "
                    f"{origin_token}/{destination_token}"
                )

            cell = core.intensity.ProductionCell(
                bundle_id=bundle_id,
                bundle_family=str(d["family"][int(row[ccols["family"]])]),
                object_class=str(d["object_class"][int(row[ccols["object_class"]])]),
                date_bc=int(row[ccols["date_bc"]]),
                origin=origin,
                destination=destination,
                production_intensity=float(row[ccols["production_intensity"]]),
                circulation_seed_intensity=float(row[ccols["circulation_seed_intensity"]]),
                source_mix=dict(source_mix_by_local.get(local, {})),
                recycle_mean=float(row[ccols["recycle_mean"]]),
            )
            if cells[global_cell] is not None:
                raise RuntimeError(f"duplicate repaired production cell {global_cell}")

            hydrated_hash = core.runtime_v3.cell_identity_hash(
                world_build_id=world_build_id,
                global_cell_index=global_cell,
                bundle_id=cell.bundle_id,
                bundle_family=cell.bundle_family,
                object_class=cell.object_class,
                date_bc=cell.date_bc,
                origin=cell.origin,
                destination=cell.destination,
                production_intensity=cell.production_intensity,
                circulation_seed_intensity=cell.circulation_seed_intensity,
                recycle_mean=cell.recycle_mean,
                source_mix=cell.source_mix,
            )
            observed_hash = core._fragment_cell_digest(fragment, local)
            if hydrated_hash != observed_hash:
                raise RuntimeError(
                    f"repaired production cell {global_cell} failed token hydration roundtrip"
                )
            cells[global_cell] = cell

    missing = [index for index, cell in enumerate(cells) if cell is None]
    if missing:
        raise RuntimeError(
            f"repaired production-cell field is incomplete: {len(missing)} missing; first={missing[:8]}"
        )
    return [cell for cell in cells if cell is not None]


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

        # Numerical spread is audit evidence, not topology identity. The two
        # observed hydro topologies were already separated upstream by the
        # realization id and repair action. Do not average these variants and do
        # not invent a tolerance; freeze the exact provenance-selected value.
        max_ulp = max(_ulp_distance(selected, float.fromhex(hx)) for hx in all_values[node_id])
        direct_max_ulp = max(
            [_ulp_distance(selected, float.fromhex(hx)) for hx in canonical_values[node_id]] or [0]
        )
        projected_max_ulp = max(
            [_ulp_distance(selected, float.fromhex(hx)) for hx in projected_values[node_id]] or [0]
        )

        context[node_id] = float(selected)
        audit[node_id] = {
            "variant_count": len(all_values[node_id]),
            "canonical_variant_count": len(canonical_values[node_id]),
            "projected_variant_count": len(projected_values[node_id]),
            "direct_sample_count": sum(canonical_values[node_id].values()),
            "projected_sample_count": sum(projected_values[node_id].values()),
            "selected_sample_count": int(all_values[node_id][selected.hex()]),
            "max_ulp_distance": int(max_ulp),
            "max_direct_ulp_distance": int(direct_max_ulp),
            "max_projected_ulp_distance": int(projected_max_ulp),
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
        projected_variant_count = [int(audit.get(str(node), {}).get("projected_variant_count", 0)) for node in node_ids]
        direct_count = [int(audit.get(str(node), {}).get("direct_sample_count", 0)) for node in node_ids]
        projected_count = [int(audit.get(str(node), {}).get("projected_sample_count", 0)) for node in node_ids]
        selected_count = [int(audit.get(str(node), {}).get("selected_sample_count", 0)) for node in node_ids]
        max_ulp = [int(audit.get(str(node), {}).get("max_ulp_distance", 0)) for node in node_ids]
        max_direct_ulp = [int(audit.get(str(node), {}).get("max_direct_ulp_distance", 0)) for node in node_ids]
        max_projected_ulp = [int(audit.get(str(node), {}).get("max_projected_ulp_distance", 0)) for node in node_ids]
        selection_basis = [int(audit.get(str(node), {}).get("selection_basis", -1)) for node in node_ids]

        g = ds.createGroup("canonical_hydro")
        g.createDimension("node", len(node_ids))
        core._strvar(g, "node_id", "node", node_ids)
        core._numvar(g, "context", "f8", ("node",), values)
        core._numvar(g, "observed_in_repaired_field", "i1", ("node",), observed_mask)
        core._numvar(g, "exact_variant_count", "i2", ("node",), variant_count)
        core._numvar(g, "direct_canonical_variant_count", "i2", ("node",), canonical_variant_count)
        core._numvar(g, "projected_variant_count", "i2", ("node",), projected_variant_count)
        core._numvar(g, "direct_canonical_sample_count", "i8", ("node",), direct_count)
        core._numvar(g, "projected_sample_count", "i8", ("node",), projected_count)
        core._numvar(g, "selected_exact_sample_count", "i8", ("node",), selected_count)
        core._numvar(g, "max_observed_ulp_distance", "i8", ("node",), max_ulp)
        core._numvar(g, "max_direct_ulp_distance", "i8", ("node",), max_direct_ulp)
        core._numvar(g, "max_projected_ulp_distance", "i8", ("node",), max_projected_ulp)
        core._numvar(g, "selection_basis", "i1", ("node",), selection_basis)
        g.source = "phase08-repaired-compact-topology-provenance-resolved-readout"
        g.selection_basis_codes = "0=projected-only-exact-mode;1=direct-canonical-exact-mode;2=repair-plan-boundary"
        g.numeric_spread_policy = "topology-by-phase07-realization-id;exact-mode-no-averaging-no-isclose;variants-audited"
        g.profile_node_count = int(profile_node_count)
        g.representative_rows_validated = int(representative_count)
        g.nodes_with_numeric_variants = int(sum(value > 1 for value in variant_count))
        g.max_observed_ulp_distance = int(max(max_ulp or [0]))
        g.max_direct_ulp_distance = int(max(max_direct_ulp or [0]))
        g.max_projected_ulp_distance = int(max(max_projected_ulp or [0]))

        ds.canonical_hydro_realization_id = canonical_id
        ds.minority_hydro_realization_id = minority_id
        ds.fresh_build_hydro_realization_id = "not-rebuilt-r17-freezes-repaired-corpus"
        ds.canonical_hydro_source = "repaired-phase08-field-topology-provenance-resolved-not-fresh-topology"
        return {str(node): float(value) for node, value in zip(node_ids, values)}

    return _write_hydro


def build_runtime(**kwargs: Any) -> dict[str, Any]:
    fragments_dir = Path(kwargs["fragments_dir"])
    expected_shards = int(kwargs.get("expected_shards", 580))
    population_cells = int(kwargs.get("population_cells", 37100))
    original_hydro = core._write_hydro
    original_production_cells = core.intensity.production_cells
    core._write_hydro = _make_hydro_writer(fragments_dir)

    def _frozen_cells(world: Any) -> list[Any]:
        # world_build_id is stable from the repaired first fragment and is also
        # checked independently by core.build_runtime before this function runs.
        first_path = next(iter(sorted(fragments_dir.rglob("compact-*.json.gz"))))
        first = core._read_fragment(first_path)
        return _repaired_production_cells(
            fragments_dir,
            world_build_id=str(first["world_build_id"]),
            world=world,
            expected_shards=expected_shards,
            population_cells=population_cells,
        )

    core.intensity.production_cells = _frozen_cells
    try:
        return core.build_runtime(**kwargs)
    finally:
        core._write_hydro = original_hydro
        core.intensity.production_cells = original_production_cells


def main() -> None:
    parser = argparse.ArgumentParser(description="Build R17 using repaired Phase-07/08 frozen readout")
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
