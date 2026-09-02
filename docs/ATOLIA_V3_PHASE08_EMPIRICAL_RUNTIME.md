# Atolia v3 phase 08 — empirical runtime compression

Phase 08 is the boundary between the recovered canonical developer truth and the
player-generation substrate. It does **not** add another archaeological mechanism
and it does not choose the player's 300 objects.

The source of truth remains the immutable Phase-07 shard corpus from Actions run
`33305458675`, interpreted through the successful Phase-07 hydro mend from run
`33623991317` and the exact replay capsules from run `33621402837`.

## Non-negotiable input rule

Phase 08 reads physical Phase-07 NetCDF shards read-only. It never rewrites a
Phase-01..05 hash and never treats repaired compact fragments as replacements for
physical shards.

For each shard the extractor must validate:

1. the Phase-07 chunk marker and world-build identity;
2. the Phase-01 spine hash;
3. the Phase-02 biography hash;
4. the Phase-03 metallurgy hash;
5. the Phase-04 workshop hash;
6. the immutable Phase-05 hash;
7. the corresponding Phase-07 repair-certificate entry.

A minority shard is then projected logically into the chosen canonical hydro
realization. For the nine affected ordinals (`507, 508, 515, 516, 564, 565, 568,
569, 577`) the exact replay capsule is required because the repair certificate
records provenance and counts while the capsule records the row-level external
exchange ADD / UPDATE / REMOVE result and the exact affected pool context.

## Empirical profile unit

The first Phase-08 representation is one weighted joint empirical profile per
positive v1 loss stratum / Phase-02 metal lineage. The join is not statistical
reconstruction: it follows the deterministic identity chain already present in
the shard:

```text
(global production cell, cell loss index)
    -> Phase-01 loss stratum
    -> Phase-02 weighted particle / final metal batch
    -> Phase-03 final chemistry and sparse source ancestry
    -> Phase-04 operations and technical capability summary
    -> Phase-05 deposition / archaeology / sparse external tail
```

This preserves joint dependence that would be destroyed by independently
histogramming chemistry, route history, deposition, and observation.

Each profile retains the empirical weights needed downstream for deterministic
sampling, including represented lineage weight, loss intensity, survival,
discovery and recorded weight. Rare external-exchange outcomes are retained
exactly rather than absorbed into moments.

## Identity policy

Phase-08 fragments are still developer intermediates, but they stop exporting
raw developer entity IDs in profile rows. Node, bundle, source and deposition-pool
identities are replaced by stable world-scoped tokens. Player-meaningful generic
categories such as object class, bundle family, deposition mode, operation type
and external-component class may remain categorical.

The tokenization is an anti-spoiler boundary, not a cryptographic secrecy claim.
The final browser product must still be audited independently before it is placed
inside Dr. Corrosion.

## Compression shape

The shard fragment is intentionally a transparent JSON checkpoint before final
binary packing. It contains:

- weighted joint profile rows;
- sparse source ancestry for each final batch;
- sparse final chemistry vectors and Pb isotope ratios;
- operation-type counts plus capability / skill / fit summaries;
- canonicalized deposition and archaeological observation fields;
- exact sparse external-exchange tails;
- source chunk and phase hashes plus mend/capsule provenance;
- a deterministic fragment hash.

The global reducer may later dictionary-encode categories, construct CSR/alias
indexes and pack numeric columns. Those storage transforms must reproduce the
same profile population and total empirical weights.

## Distributed execution

Do not fan all 580 physical NetCDF shards into one runner.

Phase 08 follows the successful Phase-07 rescue pattern:

1. unit gate;
2. three-shard canary (including at least one repaired shard before full fan-out);
3. bounded matrix workers, each downloading exactly one immutable source shard;
4. each worker emits one compact empirical runtime fragment;
5. a reducer downloads only those compact fragments and constructs the final
   empirical runtime plus deterministic indexes.

The physical shard is deleted only from the ephemeral runner after extraction.
The source Actions artifacts remain immutable.

## Boundary to Dr. Corrosion

The current Dr. Corrosion `0.1.6` path remains quarantined. Phase 08 must first
produce and validate a spoiler-safe runtime that no longer requires shipping the
Watershed source tree, hypothesis files, or loading NetCDF4 before the game entry
point.

POARI remains downstream: it routes inquiry over allowed empirical evidence. It
must not read hidden Phase-07 topology, guild truth, repair decisions or source
shard membership when choosing player objects or answers.
