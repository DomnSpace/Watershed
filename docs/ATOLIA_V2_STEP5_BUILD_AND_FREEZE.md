# Atolia v2 Step 5 — build, validate, calibrate, freeze

This is the execution runbook for the first direct-NetCDF v2 implementation on `atolia-v2-step4-9-workshop-tools`.

## Products

```text
cache/atolia_master_v2.nc   developer master; contains exact terminal/loss packet rows
cache/atolia_runtime_v2.nc  shipping/runtime product; exact /states group omitted
```

Schemas:

```text
atolia.ecmwf-master.v2-metal-lineage
atolia.ecmwf-runtime.v2-metal-lineage
```

There is no campaign-substrate JSON between simulation and NetCDF.

## 1. Benchmark the executable physics

Run the scaled micro-world first:

```powershell
python src/atolia/build_v2_direct_world.py `
  --mode benchmark `
  --hypothesis hypotheses/atolia_v2_2000_1000_structural.json
```

Benchmark mode intentionally allows the deterministic v1-style source means/Pb-concentration fallback and the graph-derived neutral hydro ensemble. It reports those fallbacks in root metadata and the validator emits warnings.

It uses the same NetCDF schema and event engine as full mode. Only production-cell count and aggregate particles per cell are reduced.

Validate:

```powershell
python src/atolia/validate_v2_direct_world.py
```

The benchmark is a **scaled micro-world**: primary Cu/Sn targets are multiplied by the fraction of structural production-cell mass retained in the benchmark subset. It must never be reported as a literal 1 Mt world.

## 2. Calibrate the 50M Atesis-crossing episode ledger

The benchmark/full accounting root attribute reports:

```text
atesis_eligible_object_episodes
scaled_atesis_episode_target
recommended_objectization_scale_for_freeze
```

The first implementation does not force the 50M count by violating mass conservation. It estimates how the current carrier/hydro/recycling realization turns explicit objectized primary metal into Atesis-crossing object episodes.

Before the canonical full build, run medium pilots and freeze the objectization prior so:

```text
E[N_Atesis-crossing object episodes] ~= 50,000,000
```

while Cu/Sn ledgers remain conserved.

Do not tune career sampling to hit this target.

## 3. Freeze scientific external inputs

Full mode deliberately refuses two provisional inputs.

### Geochemistry

Provide:

```text
--geochemistry <source-geochemistry.json>
```

Expected shape:

```json
{
  "sources": {
    "source_id": {
      "pb_ppm": 550.0,
      "pb_isotopes": {
        "Pb206_204": 18.2,
        "Pb207_204": 15.6,
        "Pb208_204": 38.2
      },
      "element_ppm": {
        "Ag": 120.0,
        "As": 900.0,
        "Fe": 700.0
      }
    }
  }
}
```

The final scientific product should be generated from the Step-3 source-distribution/covariance ingestion, not hand-written example numbers. The direct builder concentration-weights Pb isotope inventories; it does not average source ratios by total bronze mass.

### Palaeohydrology

Provide:

```text
--hydro-evidence <converted-palaeohydrology.json>
```

Expected feature rows:

```json
{
  "features": [
    {
      "a": "node_a",
      "b": "node_b",
      "provenance": "observed",
      "mechanism": "mapped_palaeochannel",
      "probability": 1.0,
      "navigability": 0.62,
      "observed": true,
      "mode": "river",
      "atesis_crossing": false
    }
  ]
}
```

A GIS ingestion/preprocessing pass should generate these node-linked carrier features from the Step-4.5 evidence/ensemble products. Full mode will not silently substitute the provisional graph ensemble.

## 4. Full 1000-year build

Use the v2 structural horizon explicitly:

```powershell
python src/atolia/build_v2_direct_world.py `
  --mode full `
  --hypothesis hypotheses/atolia_v2_2000_1000_structural.json `
  --geochemistry cache/atolia_v2_source_geochemistry.json `
  --hydro-evidence cache/atolia_v2_hydro_evidence.json
```

The full run uses all structural production cells and the configured aggregate particles per cell. It is intended to run for hours/overnight, not interactively.

Do **not** add the override flags to the canonical run. They exist only for engineering diagnosis:

```text
--allow-legacy-geochemistry
--allow-provisional-hydro
```

## 5. Full validation

```powershell
python src/atolia/validate_v2_direct_world.py --full-expectations
```

Release validation checks at minimum:

- v2 master/runtime schemas;
- runtime has no exact `/states` rows;
- cumulative metal distance >= current-object distance >= 0;
- technical-memory bounds;
- exact tracked-element mass closure under the current inventory-conserving remelt implementation;
- valid source CSR;
- joint profile covariance exists;
- 1 Mt Cu full ledger;
- Atesis-associated primary Cu near 200 kt;
- >=900-year sampled structural horizon;
- non-one-hot workshop guild affinities;
- evolved tool lineages exist;
- hydro product contains base observed carrier rows;
- full mode did not use provisional geochemistry/hydrology.

## 6. What is already physical in Step-5 a2

The executable engine currently includes:

```text
1 Mt / 200 kt / 30 kt separate accounting targets
60% pristine -> 85% recycled recovery rule
remelt creates a new object episode
cumulative-metal distance persists through remelt
current-object distance resets through remelt
repair retains current object identity
carrier-specific lifetime random walks
water-mode escalation with network embedding
war/conflict pressure
ownership transfer
rare external-network contact
late terminal aggregation IDs for hoard/grave/ritual/wreck/abandonment contexts
Pb isotope inventory mixing by Pb-bearing mass
workshop tool ecologies
operation capability derived through harmonic weak-link person/tool/material/support/thermal/measurement intersection
manufacture and repair quality feeding later physical state
joint runtime covariance for correlated lineage coordinates
```

## 7. Deliberately conservative a2 process choice

The executable remelt loop currently conserves tracked elemental/isotope inventories exactly rather than inventing uncertain element-specific Bronze Age remelt-loss/fractionation coefficients.

That means:

```text
full remelt -> strong technical/microstructural memory loss
            -> object identity/distance reset
            -> chemistry/isotope inventory conserved in a2
```

Step-3 calibrated process-transfer distributions can later replace this identity transfer law without changing the NetCDF schema.

This is preferable to baking unsupported Sn/As/Pb loss percentages into the canonical overnight world.

## 8. Current boundary of implementation

The Step-5 a2 writer stores the workshop/tool world and feeds workshop operation capability into manufacture/repair/remelt outcomes. Manufacture/repair events encode the acting workshop in the event vocabulary (`manufacture@W...`, etc.) in this first executable cut.

Before final installer freeze, normalize those event-workshop relations into dedicated integer pointer columns if the resulting event vocabulary is materially large. The physics does not depend on the string representation.

Likewise, full GIS ingestion and the Step-3 empirical covariance source product remain external-input preparation jobs. Full mode is intentionally gated on them instead of pretending they already exist.

## 9. Freeze rule

Do not overwrite v1 master/runtime products.

A v2 master becomes canonical only after:

```text
benchmark structural validation
-> medium objectization calibration
-> scientific source/hydro input freeze
-> one full overnight build
-> full structural validation
-> A/A/B deterministic career tests
-> 300-object hidden-truth audit
```

Only then should acquisition/player packaging be switched from `atolia_runtime_v1.nc` to `atolia_runtime_v2.nc`.
