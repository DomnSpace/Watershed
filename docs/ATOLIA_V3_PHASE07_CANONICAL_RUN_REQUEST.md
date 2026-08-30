# Atolia v3 phase-07 canonical run request

This commit requests the first canonical-full execution of the gated phase-07 sharded builder.

Scientific configuration:

- hypothesis: `hypotheses/atolia_atesis_1800_1000_v0.json`
- world seed: `20260824`
- workshops: `3200`
- intensity steps: `28`
- geography target: `1000` nodes
- production cells: complete population, no `--max-cells`

Storage configuration:

- shard size: `512` contiguous global production cells
- output root: `/tmp/atolia_v3_canonical_full`
- immutable validated-shard resume contract: enabled
- canonical root: `manifest.nc`

The storage shard size is operational and is excluded from `world_build_id`. The manifest SHA identifies this concrete ordered storage realization. No phase-06 selection is used to determine the phase-07 hidden world.
