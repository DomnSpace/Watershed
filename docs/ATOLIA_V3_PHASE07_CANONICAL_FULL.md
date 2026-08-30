# Atolia v3 phase 07 — canonical full world

Phase 07 adds **no new archaeological mechanism**. It changes the execution and storage shape so the already-gated v1 propagation plus v3 phases 02–05 can be run over the complete production-cell population without constructing the complete hidden object graph in memory at once.

## Canonical settings

The canonical defaults are inherited from the recovered campaign-substrate contract:

- world seed: `20260824`
- workshops: `3200`
- intensity propagation steps: `28`
- physical geography target: `1000` nodes
- hypothesis: `hypotheses/atolia_atesis_1800_1000_v0.json`

A run is labelled `canonical-full` only when it uses those settings **and** materializes every production cell. `--max-cells` always creates a `verification-prefix`; altered settings over the complete population create `full-world-noncanonical-config`.

## Why the canonical master is sharded

The scientific world is not sharded; its storage is.

The builder creates one world, enumerates its complete ordered production-cell population once, and processes contiguous cell ranges. Each NetCDF shard contains the ordinary phase-01 through phase-05 tables for only that bounded range. The root `manifest.nc` is the canonical master identity and ordered shard index.

This avoids a distribution → Gaussian → pseudo-object compression step and avoids requiring all phase-02 batches, phase-03 chemistry, phase-04 operations, and phase-05 archaeology rows to coexist in RAM.

## Scientific identity versus storage identity

Two identities are deliberately distinct.

`world_build_id`
: SHA-256 of the hypothesis and canonical model configuration. Shard size is excluded. Rechunking the same world does not create a different Bronze Age world.

`phase07_manifest_sha256`
: SHA-256 of the exact ordered shard set, global deposition-pool table, global tool-use table, and aggregate flow summary. This identifies a concrete storage realization of the world.

Every shard also receives `chunk_sha256`, linking its global cell range to its phase-01, phase-02, phase-03, phase-04 and phase-05 hashes.

## Global production-cell identity

Older phase writers enumerate rows local to the provided report list. That is not sufficient for a sharded full build.

Phase 07 therefore writes the phase-01 `cell_index` and `loss_strata.cell_index` as the **global production-cell index** before any downstream phase is appended. Phase-02 lineages are materialized with the same global index. A lineage therefore keeps the same particle/batch/object IDs regardless of which storage shard contains it.

## Globally shared state

Two phase-04/05 summaries are only partial inside a shard and are merged by the canonical manifest:

- deposition pools are globally keyed by the existing stable `(node, date, mode)` pool ID; member counts and represented weights are summed across all shards;
- persistent-tool use is globally keyed by `tool_id`; localized operation counts, represented operation weights and represented mass are summed across shards.

The static workshop/tool catalogue and the hydro evidence/ensemble/realization are reproduced by each shard's ordinary phase writer. Phase 07 requires an identical static-workshop signature and identical hydro-realization signature across every shard. Any mismatch aborts the build.

The manifest's global pool and tool-use tables are authoritative for cross-shard summaries. Individual operation, lineage, chemistry, exchange and archaeology rows remain in the shards.

## Resume semantics

A completed shard is immutable and reusable only if all of these validate:

1. world build ID and requested global cell interval match;
2. phase-01 spine read/hash passes;
3. phase-02 biography read/hash passes;
4. phase-03 metallurgy read/hash passes;
5. phase-04 workshop read/hash passes;
6. phase-05 environment/deposition read/hash passes;
7. the phase-07 chunk hash recomputes exactly.

A failed or missing shard is rebuilt independently. The final manifest is regenerated from the validated shard set.

The phase-01 shard itself keeps full-precision flow values. The manifest uses the common `canonical-float-10sig-v1` projection for derived cross-shard totals, so a fresh pass and a resumed pass cannot differ only because one total was summed from in-memory floats and the other from persisted marker JSON.

## Phase-06 relationship

Phase 06 remains the representativeness gate. It demonstrated that the 2,048-cell stratified cohort preserved the production population and an independent downstream probe within its declared thresholds.

Phase 07 does **not** re-sample that cohort and does not use it as hidden truth. It materializes the complete production-cell population. Phase-06 selection metadata therefore has no role in deciding which phase-07 objects exist.

## Output

Default native invocation:

```bash
python src/atolia/v3_phase07_canonical.py
```

produces:

```text
cache/atolia_v3_canonical_full/
  manifest.nc
  shards/
    atolia_v3_canonical_000000_000512.nc
    atolia_v3_canonical_000512_001024.nc
    ...
```

A small mechanical verification may use, for example:

```bash
python src/atolia/v3_phase07_canonical.py \
  --world-seed 1300 --workshops 320 --steps 2 --nodes 12 \
  --chunk-cells 64 --max-cells 192 \
  --out-dir /tmp/atolia_v3_phase07_verify
```

Such a product is explicitly `verification-prefix`, never canonical full.

## Boundary to phase 08

Phase 07 is still developer hidden truth. It does not expose the player research state and does not perform runtime empirical compression.

Phase 08 must consume the canonical manifest/shards and build the anonymous empirical runtime representation: weighted joint representatives, exact rare tails, categorical joint tables, sparse source ancestry and deterministic alias sampling. POARI remains downstream of the allowed player-visible evidence and must not use the hidden shard selection or truth tables to choose answers.
