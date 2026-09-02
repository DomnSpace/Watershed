# Atolia v3 Phase-08 — Dr. Corrosion extraction

This branch is the extraction continuation of the successful Phase-07 hydro mend.
The mend is complete; this phase turns the repaired canonical scientific corpus
into the compact empirical substrate used to crystallize a deterministic private
300-object Dr. Corrosion safe.

## Canary decision

Two real immutable Phase-07 shards passed the compact extraction path end to end.

### Ordinary canonical shard 2

- source NetCDF: 1,229,549,415 bytes
- compact sampler fragment: 4,990,179 bytes
- compression: 246.39x
- production cells: 64
- physical lineages: 32,999
- empirical `(production cell, loss node)` profiles: 2,922
- retained real joint lineage representatives: 5,711
- exact sparse external tails: 493
- represented / loss weight: 59,388.100608242166
- recorded archaeological weight: 489.28161706896634

### Capsule-repaired shard 507

- source NetCDF: 1,654,225,705 bytes
- compact sampler fragment: 5,317,249 bytes
- compression: 311.11x
- production cells: 64
- physical lineages: 58,289
- empirical profiles: 3,360
- retained real joint lineage representatives: 6,665
- exact sparse external tails: 2,611
- represented / loss weight: 12,232.880537575846
- recorded archaeological weight: 90.13518090178182
- Phase-07 replay capsule applied and verified before compaction

Both canaries validated the immutable Phase-01..05 hashes, repair-certificate
lineage, weight conservation, deterministic compact roundtrip, developer-ID
anonymization and exact external-tail population. The repaired canary proves that
the successful mend survives the actual extraction path rather than merely the
manifest layer.

## Full extraction

The full workflow covers all Phase-07 ordinals `0..579` in three bounded matrices.
Only the nine repair-sensitive shards consume replay capsules. Each worker:

1. downloads one immutable Phase-07 NetCDF shard;
2. validates every frozen Phase-01..05 hash against the Phase-07 chunk marker;
3. applies the Phase-07 mend in memory where required;
4. emits one compact empirical sampler fragment;
5. verifies counts, weights and repair provenance;
6. deletes the runner-local giant source copy;
7. uploads only the temporary compact fragment.

After all 580 workers succeed, the reducer validates contiguous world coverage,
builds the recorded-weight alias index and writes the browser-native stdlib
sampler archive (`zipfile` + `gzip` + `json`). No NumPy, netCDF4 or Watershed
source tree is required by that reduced runtime boundary.

The 580 compact worker fragments are temporary recovery/extraction products. The
reduced sampler archive is the durable Phase-08 handoff; Dr. Corrosion will then
use its install/safe-specific deterministic key to crystallize and seal exactly
300 private objects.
