# Atolia ECMWF v2 — metal-lineage big model

Status: implementation target on `atolia-metal-lineage-v1`.

## Purpose

Build one better developer substrate directly from the physical circulation simulation into NetCDF4, without the v1 `2.16 GB gzip JSON -> NetCDF` intermediate. The aim is not to preserve every explicit object genealogy inside the full 20M+ state field. The aim is to preserve sufficient latent state so the selected 300 artefacts can later materialize physically coherent ore -> object -> scrap/broker -> remelt -> object lineages.

The distinction is fundamental:

- **metal circulation** persists through remelting;
- **current-object circulation** resets at remelting;
- chemical/source ancestry survives remelting much better than microstructure/tooling memory;
- guild/workshop episodes can change after remelting or repair;
- final artefact class is only the last episode of the metal biography.

## v1 state retained

For every loss state/profile retain:

- expected recycle/remelt count;
- expected repair count;
- expected source entropy;
- expected field crossings;
- expected physical crossings;
- archaeological observation/deposition fields;
- production-cell source mix, object class, date, origin/destination and flux.

## v2 lineage coordinates

Add the following scalar coordinates to exact states and profile moments:

1. `ore_distance_km`
   - weighted geographic source-field -> initial production-node distance;
   - does not change after production.

2. `cumulative_metal_distance_km`
   - increments on every physical transfer;
   - never resets at repair or remelt.

3. `current_object_distance_km`
   - increments while the current artefact episode survives;
   - resets to zero on a true remelt/recasting event.

4. `expected_remelt_count`
   - distinct from repair;
   - each remelt destroys current object identity and starts a new manufacturing episode.

5. `expected_workshop_transition_count`
   - expected number of distinct post-source manufacturing episodes;
   - increments on remelt/recasting and on major workshop-changing repair where applicable.

6. `technical_memory_fraction`
   - 1.0 at manufacture;
   - mild attenuation under use/repair;
   - strong attenuation under remelt;
   - represents survival of prior microstructure/tooling information, not chemistry.

7. `broker_cycle_expectation`
   - expected number of scrap-stock/broker residence episodes associated with recycling;
   - allows metal to circulate locally before becoming a new object.

8. `current_object_age_steps`
   - abstract transfer/use opportunities since last remelt;
   - resets at remelt.

The existing `expected_source_entropy` continues to represent source-mixture complexity. v2 must not fake a full exact source-vector history when only aggregate mixing is known.

## Compact categorical lineage summaries

Do **not** branch each of 23M+ states across all 17 object classes and 12 guilds. That would multiply the state field unnecessarily.

Instead profile aggregation should preserve sparse exposure summaries:

- `profile_guild_exposure_ptr/id/weight`: top/nonzero expected guild exposure accumulated at manufacturing-capable nodes;
- `profile_prior_class_ptr/id/weight`: coarse expected prior-object-class family exposure from remelting transitions;
- optional `profile_broker_region_ptr/id/weight`: regions in which scrap/broker cycling likely occurred.

These are profile-level CSR products, not exact-state dense matrices.

The selected-object lineage sampler then draws explicit episodes conditional on these sufficient statistics.

## Transfer and event semantics

For a move along an edge of length `d`:

```
cumulative_metal_distance_km += d
current_object_distance_km += d
```

For a repair:

```
repair_count += 1
technical_memory_fraction *= repair_memory_survival
# current object identity and distance remain intact
```

For a remelt/recycle:

```
remelt_count += 1
workshop_transition_count += 1
broker_cycle_expectation += broker_probability(node, date, class)
technical_memory_fraction *= remelt_memory_survival
current_object_distance_km = 0
# cumulative metal distance is unchanged
```

A later explicit 300-object materialization may change class, workshop and primary guild here. The full field only carries the sufficient transition state.

## Metallurgical-memory interpretation

The model deliberately separates evidence channels:

- source proportions / Pb isotopes / trace chemistry: persistent but progressively mixed;
- bulk alloy: evolves through mixture/addition/loss processes;
- microstructure, dendrites, cold work, hardness: dominated by latest manufacture;
- repair interfaces/tooling: can preserve a later local intervention;
- morphology: survives repair/reworking more readily than full remelt;
- guild lineage: a sequence of technical episodes, not one final label.

Thus a remelt at Damascus may erase nearly all earlier microstructural evidence without erasing the cumulative metal itinerary.

## Distance reporting

Every selected artefact must ultimately expose to developer truth:

```
ore_distance_km
cumulative_metal_distance_km
current_object_distance_km
```

and the invariant

```
cumulative_metal_distance_km >= current_object_distance_km >= 0
```

The first term may include source -> first production. If reported separately, define:

```
total_metal_journey_km = ore_distance_km + cumulative_metal_distance_km
```

This is the quantity expected to produce many 500–1000+ km metal biographies even when the final object itself travelled only tens or hundreds of kilometres.

## Direct NetCDF build

v2 must not emit the giant campaign JSON.

Target pipeline:

```
world.build()
  -> production_cells()
  -> propagate one production cell
  -> append exact loss states directly to NetCDF master
  -> update profile accumulators online
  -> discard that cell's Python loss objects
  -> next cell
  -> finalize profile indexes/CSR
  -> derive compact runtime NetCDF
```

This keeps peak memory proportional to one production cell plus profile accumulators rather than the full 23M-state object graph.

Schemas:

- developer master: `atolia.ecmwf-master.v2-metal-lineage`
- shipping runtime: `atolia.ecmwf-runtime.v2-metal-lineage`

Suggested files:

- `cache/atolia_master_v2.nc`
- `cache/atolia_runtime_v2.nc`
- `cache/atolia_vocabulary_v2.json`

## Precision/storage

Master:

- exact state scalar lineage coordinates: float64;
- categorical ids: compact integer types where safe;
- chunked zlib/shuffle compression;
- no repeated strings.

Runtime:

- loss/profile intensities: float64 where conservation depends on them;
- lineage profile means/variances may use float32 after round-trip error audit;
- sparse guild/class/broker summaries via CSR;
- no exact `state_*` arrays.

The goal is a modest runtime increase from v1, not a multi-gigabyte shipping file.

## Career contract

POARI continues to rank archaeological inquiry/actions, never hidden artefacts.

The v2 field may make rich biographies physically available. It must not let late career regimes directly select an object because its hidden guild lineage, metal distance or remelt count would be narratively useful.

Within a chosen site/context:

```
P(profile | chosen site) ∝ archaeological intensity × observation logic
```

not hidden explanatory usefulness.

Observed measurements may alter later site/action choice.

## Validation gates before replacing v1

1. Existing mass/endpoint conservation remains within numerical tolerance.
2. `cumulative_metal_distance >= current_object_distance` for all states/profiles.
3. remelt increments do not create/destroy circulating intensity.
4. repair does not reset current-object distance.
5. remelt does reset current-object distance and attenuate technical memory.
6. profile aggregation reproduces exact-state weighted means on random sampled profiles.
7. same world+career key remains deterministic.
8. same hidden world with different career key diverges in selected 300.
9. all 300 materialized objects carry full alloy/microstructure/manufacture/corrosion/provenance plus explicit metal lineage.
10. audit the distribution of `total_metal_journey_km`; require that long cumulative biographies can occur without forcing final-object long-distance travel.
11. no POARI hidden-truth selection leak.
12. runtime contains no exact-state arrays.

## Migration rule

Do not overwrite v1 files. Build v2 beside them. Keep v1 runtime usable until v2 structural validation and at least A/A/B career tests succeed.
