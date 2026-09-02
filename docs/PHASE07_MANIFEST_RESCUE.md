# Atolia v3 Phase-07 manifest rescue and canonical hydro mend

Source product is frozen to GitHub Actions run `33305458675` at commit
`29ac8cb5ea80f7d63631b153c27fce30efcb0bac`.

The initial rescue is deliberately non-destructive:

- source shard artifacts are downloaded read-only, one artifact per runner;
- no artifact deletion API is used;
- no source shard is overwritten or renamed;
- only the ephemeral runner-local downloaded copy is removed after extraction;
- each source shard must pass the existing phase-07 `_read_existing_shard`
  roundtrip/hash validation before a compact fragment is emitted;
- the compact fragment preserves the full float values required by the existing
  global deposition-pool, tool-use, and flow reductions;
- the final root manifest is assembled only from all 580 validated fragments.

The three-shard canary passed before this full extraction was enabled.  Source
run artifact count remained 581 after the canary, confirming that extraction did
not consume the preserved source artifacts.

For future canonical builds, each shard worker now emits and uploads its compact
manifest fragment immediately after shard validation, so root-manifest assembly
never again requires a hundreds-of-gigabytes fan-in.

## Recovered split and canonical rule

The 580 validated fragments reproduce two observed hydro realizations from the
same world-build identity:

- `hyr_214521a9c3c67f4414d1`: 411 fragments;
- `hyr_520b34bc6dd71cffaa98`: 169 fragments.

The 32-replica forensics run `33468978864` reproduced those two topologies only
(21 versus 11); it did not produce a third state. The cutoff plan from run
`33555735512` therefore selects the observed 411-fragment realization as the
recovery canonical state. This is a recovery rule for the already-computed
corpus, not a claim that the majority topology is scientifically superior.

The two topologies differ at seven selected edges and six node contexts. Only
nine minority shards contain deposition rows at those nodes: ordinals 507, 508,
515, 516, 564, 565, 568, 569, and 577. The other 160 minority fragments need an
identity projection only.

## Exact replay result

Run `33621402837` reopened the nine immutable source NetCDF artifacts read-only,
validated their original phase hashes, and reused each particle's deterministic
external-exchange draw under the canonical node context. The nine capsules cover
21,737 affected particles and all 1,136 affected minority pool rows. They record:

- 20,793 unchanged absent exchanges;
- 922 retained exchanges with updated contact probability;
- 5 exact additions;
- 17 exact removals;
- 22 threshold flips and a net external-exchange count delta of -12.

The maximum source-versus-plan context difference was
`1.0441980613506985e-11`. Every source value and its representative plan value
agree under the frozen Phase-05 10-significant-digit hash projection, and the
old external probabilities roundtrip with zero error.

## Mend representation

`v3_phase07_repair.py` does not rewrite a physical shard or its Phase-05 hash.
It creates a logical compact-fragment projection instead:

- all 169 minority fragments receive the canonical hydro realization identity;
- the 1,136 affected pool rows receive the capsule-validated canonical context;
- the nine affected shard counts receive their exact capsule-backed deltas;
- every source chunk hash, Phase-05 hash, and source fragment hash is retained in
  the repair overlay;
- the standard logical manifest hash and a separate recovery-overlay hash are
  both roundtrip-validated.

The final workflow uploads the 169 repaired minority fragments, the coherent
580-shard canonical root, the cutoff plan, replay summary, repair certificate,
and verification record. Phase 08 must consume the immutable source shards plus
this explicit overlay; the repaired fragments are not substitutes for the
physical NetCDF carriers.
