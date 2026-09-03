# Atolia v3 Phase-08 — exact Phase-01 generative rescue

The 580-way Dr. Corrosion empirical extraction succeeded at the expensive shard-worker boundary, but the final reducer was cancelled.  A precision audit then compared an actual immutable Phase-07 source carrier (ordinal 579) with its actual Phase-08 compact fragment.

## Audit result

For ordinal 579:

- Phase-07 loss rows: 15,635
- old-runtime `(production cell, loss node)` profiles: 896
- Phase-08 compact profiles: 896
- missing profile keys: 0
- bitwise differences in profile loss, step range, and all six old-runtime mean/variance pairs: 0
- bitwise differences in the three retained production-cell floats and every source-mixture weight: 0

The compact projection therefore did not numerically smear the retained Phase-01 coordinates.  JSON float roundtrip is not the problem.

The audit did identify a real information boundary: the compact schema omitted the exact Phase-01 `deposition_mode_weights_json` and `field_mix_json`.  Those fields are required to reproduce the recovered compact v1 runtime contract exactly.  In particular, the old runtime derives profile observation rate, archaeological intensity, context completeness and hoard prior from the exact Phase-01 deposition vector; downstream Phase-05 recorded-mode fractions are not algebraically equivalent.

The compact fragment's conservation assertions also currently use `math.isclose(..., rel_tol=2e-13, abs_tol=1e-14)`.  That gate is too permissive to serve as the scientific identity criterion even though the inspected real shard happened to match bit-for-bit.

## Rescue boundary

`v3_phase08_phase01_rescue.py` preserves the complete Phase-01 spine from each immutable Phase-07 carrier:

- every cell row, including exact source-mixture JSON and full flow values;
- every loss-stratum row, including exact deposition-mode and transport-field JSON;
- the exact ordered loss population and all six generative coordinates;
- the Phase-01 flow summary and identifying metadata.

Each sidecar must recompute the original `phase01_spine_sha256` exactly after deterministic JSON/gzip roundtrip.  This is stronger than a numeric tolerance and preserves the complete hashed Phase-01 equivalence checkpoint.

The rescue is intentionally Phase-01-only.  It does not read or recompute Phase-02 metallurgy, Phase-03 chemistry, Phase-04 workshop state or Phase-05 hydro/archaeology.  The successful Phase-07 hydro mend remains represented by the already-produced repaired empirical fragments and replay provenance; Phase-01 itself is unaffected by that Phase-05 overlay.

## Distributed run

The full rescue uses the same bounded three-wave shape as the successful extraction, with at most six source-carrier downloads active at once.  Every worker deletes its runner-local giant NetCDF before upload and retains only its exact Phase-01 sidecar plus summary for 90 days.

There is deliberately no 580-fragment reducer in this expiry-critical pass.  Once all 580 exact sidecars exist, a later reducer can build and audit the crisp R17 generative NetCDF without reopening the expiring Phase-07 carriers.
