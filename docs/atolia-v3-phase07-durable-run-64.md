# Atolia v3 phase-07 durable 64-cell run

This marker records the second canonical full execution request after the initial 192-cell matrix was manually stopped before any shard artifact completed.

Execution contract:

- canonical population: 37,100 production cells
- canonical world seed: 20260824
- workshops: 3,200
- intensity steps: 28
- target geography nodes: 1,000
- durable shard size: 64 cells
- total immutable shards: 580
- canary: ordinals 0..2 (3 real canonical shards)
- nested wave 0: 192 shards
- nested wave 1: 192 shards
- nested wave 2: 193 shards
- maximum parallel workers within a wave: 8
- each successful shard uploads immediately and is retained for 7 days
- later waves continue after an isolated earlier-wave failure; the canonical manifest is assembled only after all waves are green
- worker summaries include explicit static-world, materialization, roundtrip and total timings
