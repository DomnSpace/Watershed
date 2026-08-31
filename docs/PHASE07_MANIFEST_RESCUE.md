# Atolia v3 Phase-07 manifest rescue

Source product is frozen to GitHub Actions run `33305458675` at commit
`29ac8cb5ea80f7d63631b153c27fce30efcb0bac`.

The rescue is deliberately non-destructive:

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
