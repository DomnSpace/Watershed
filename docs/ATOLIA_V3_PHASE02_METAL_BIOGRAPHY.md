# Atolia v3 phase 02 — metal biography contract

Branch: `atolia-v3-02-metal-biography`

Phase 01 is frozen by G2. Its canonical world construction and
`intensity_circulation` propagation are not modified.

## Representation

Phase 02 is conditional on the phase-01 loss substrate:

```text
v1 ProductionCell
  -> v1 CellFlowReport
    -> v1 LossStratum
      -> one weighted phase-02 metal lineage
```

The representative weight is exactly `LossStratum.loss_intensity`. This is not a
second circulation simulator and the weighted representatives are not new primary
production.

Each lineage receives stable IDs for:

- `particle_id`
- metal batches
- object episodes
- repair/remelt/loss events

The phase-02 master appends:

```text
/particles
/metal/batches
/metal/ancestry
/metal/parents
/objects
/events
```

The phase-01 root `phase` and `spine_sha256` remain unchanged. The root gains
`latest_phase`, phase-02 schema/model metadata and a deterministic biography hash.

## Remelt boundary

A full remelt is a real parent-mass transformation.

For a child batch of mass `M`:

```text
old contribution      = r M
recycle-pool addition = (1-r) M
child mass             = r M + (1-r) M = M
```

`r` is a deterministic bounded partition assumption (`0.62 <= r < 0.90`) used
only to separate surviving old-lineage metal from contemporaneous recycle-pool
addition. It is **not** an elemental loss coefficient.

The old batch remains as a historical state. The contribution table records how
much of it enters the child; the unretained remainder exits this tracked
conditional lineage. Phase 02 therefore guarantees local parent/child mass closure
without pretending that conditional representatives form a global simultaneous
metal stock.

No element-specific loss, fractionation or Pb-isotope process model is introduced
here. Those belong to phase 03.

## Source ancestry

Initial ancestry is the production cell's existing `source_mix` expressed as
source mass. Recycle-pool additions may be nudged toward the v1
`expected_source_entropy`, but only over source IDs already present in that
production cell. Phase 02 never invents a geological source.

Every batch stores sparse source ancestry mass and every ancestry row satisfies:

```text
sum(source_mass_kg) == batch.metal_mass_kg
sum(source_fraction) == 1
```

A remelt child recursively carries the retained fraction of the old batch ancestry
plus the addition ancestry.

## Three distances

The three distances are deliberately independent:

- `ore_distance_km`: source-weighted geodesic distance from source fields to the
  production origin.
- `cumulative_metal_distance_km`: the v1
  `LossStratum.route_distance_from_origin_km`.
- `current_object_distance_km`: distance travelled after the last full remelt.

A full remelt resets only current-object distance. It does not reset cumulative
metal distance.

The phase-01 stratum stores travelled distance but not every intermediate named
route node. Therefore phase-02 repair/remelt events receive a deterministic route
position in km. Intermediate `node_id` is `None` unless it is a genuinely known
endpoint. Workshop/node binding belongs to phase 04; no place name is fabricated.

## Counts

Continuous v1 expectations `expected_recycle_count` and
`expected_repair_count` are converted to deterministic integer event counts by
seeded stochastic rounding. This preserves the expectation across deterministic
ensembles without treating a fractional event as a physical event.

## Invariants / G3 gate

The focused phase-02 tests require:

- same seed and same loss stratum -> identical complete lineage;
- different seed -> different deterministic lineage realization;
- positive finite represented weights and batch masses;
- parent graph topologically ordered and acyclic;
- every remelt child has exact parent-mass closure;
- every batch ancestry closes to batch mass;
- source support never expands beyond the production cell source support;
- `0 <= current_object_distance_km <= cumulative_metal_distance_km`;
- all event positions nonnegative, finite and monotone;
- repair/remelt event counts equal the materialized counts;
- final event is the actual v1 loss node;
- NetCDF phase-02 append/read reconstructs every row exactly and preserves the
  phase-01 `phase` and `spine_sha256`.

## Deferred deliberately

Phase 02 does not implement:

- source geochemical covariance, elemental chemistry or Pb inventories (phase 03);
- workshop/guild/tool assignment or object-class change at remelt (phase 04);
- hydrological realizations, external exchange components or deposition pools
  (phase 05);
- medium/canonical representative compression (phases 06–08);
- player/POARI sampling changes (phase 09).

POARI remains outside hidden lineage materialization:

> POARI routes archaeological inquiry, not hidden artefact selection.
